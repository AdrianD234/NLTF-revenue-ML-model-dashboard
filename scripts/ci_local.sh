#!/usr/bin/env bash
# Run a CI tier locally in the clean-room container. POSIX counterpart to
# scripts/ci_local.ps1; the two keep the same contract:
#
#   * never runs against the active checkout - a disposable detached worktree
#     at an exact commit is created, mounted, and deleted
#   * byte-exactness is verified, not assumed
#   * outputs land under artifacts/ci_local/<sha>/
#   * concurrent runs are refused, not interleaved
#   * the tier's real exit code is returned
#   * no host Python is required
#
# Usage:
#   scripts/ci_local.sh --tier fast
#   scripts/ci_local.sh --tier affected --base origin/main
#   scripts/ci_local.sh --tier full
#   scripts/ci_local.sh --tier profile
#   scripts/ci_local.sh --tier replay --engine ar1

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TIER="fast"
BASE="origin/main"
REF="HEAD"
ENGINE=""
REBUILD=0
KEEP_WORKTREE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --tier)   TIER="$2"; shift 2 ;;
    --base)   BASE="$2"; shift 2 ;;
    --ref)    REF="$2"; shift 2 ;;
    --engine) ENGINE="$2"; shift 2 ;;
    --rebuild) REBUILD=1; shift ;;
    --keep-worktree) KEEP_WORKTREE=1; shift ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

section() { printf '\n=== %s ===\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }

# --- 1. Docker ---------------------------------------------------------------
section "Checking Docker"
command -v docker >/dev/null 2>&1 || fail "$(cat <<'EOF'
Docker is not on PATH.

The container is the only local environment that matches CI (Python 3.11), so
governed questions cannot be settled without it.

Install Docker ENGINE - not Docker Desktop, which carries a commercial
licensing requirement for government entities and larger organisations:

    bash ci/install_docker_engine_wsl.sh

See ci/README.md.
EOF
)"
docker version --format '{{.Server.Os}}' >/dev/null 2>&1 \
  || fail "$(cat <<'EOF'
Docker is installed but the daemon is not responding.

    sudo systemctl status docker      # if systemd is running in this distro
    sudo service docker start         # otherwise
EOF
)"
server_os="$(docker version --format '{{.Server.Os}}' 2>/dev/null)"
[ "$server_os" = "linux" ] || fail "Docker is in ${server_os}-container mode; this image needs Linux containers."
echo "Docker OK (linux containers)"

# --- 2. Source SHA -----------------------------------------------------------
section "Resolving source"
SHA="$(git -C "$REPO_ROOT" rev-parse "$REF" 2>/dev/null)" || fail "Cannot resolve ref '$REF'."
SHORT_SHA="${SHA:0:12}"
echo "Testing commit $SHA"
if [ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]; then
  echo "NOTE: your checkout has uncommitted changes. They are NOT included;" >&2
  echo "      this run tests committed state ${SHORT_SHA}." >&2
fi

# --- 3. Concurrency lock -----------------------------------------------------
LOCK="$REPO_ROOT/artifacts/ci_local/.lock"
mkdir -p "$(dirname "$LOCK")"
if [ -e "$LOCK" ]; then
  fail "Another local CI run holds the lock:
$(cat "$LOCK")
Wait for it, or remove $LOCK if that run is definitely dead."
fi
printf 'tier=%s sha=%s pid=%s started=%s\n' \
  "$TIER" "$SHORT_SHA" "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$LOCK"

# The disposable worktree must live on the Linux filesystem, never under
# /mnt/c. Under WSL2, /mnt/c is a 9p mount: bind-mounting a tree of this size
# from it into a container is slow enough to distort a timed run, which would
# make every benchmark this project produces suspect. TMPDIR is normally /tmp
# on ext4, but check rather than assume - a TMPDIR pointing at a Windows drive
# would silently reintroduce the problem.
WORKTREE_BASE="${TMPDIR:-/tmp}"
case "$WORKTREE_BASE" in
  /mnt/*)
    echo "NOTE: TMPDIR ($WORKTREE_BASE) is a Windows mount; using /tmp instead so" >&2
    echo "      the timed run is not distorted by 9p filesystem overhead." >&2
    WORKTREE_BASE=/tmp
    ;;
esac
WORKTREE="${WORKTREE_BASE}/nltf-ci-${SHORT_SHA}-$$"

case "$REPO_ROOT" in
  /mnt/*)
    echo "WARNING: this checkout is on a Windows mount ($REPO_ROOT)." >&2
    echo "         Git metadata reads will cross the 9p boundary and timings will be" >&2
    echo "         pessimistic. For benchmark-grade runs, clone into the Linux" >&2
    echo "         filesystem first - see ci/README.md." >&2
    ;;
esac

OUT_DIR="$REPO_ROOT/artifacts/ci_local/$SHORT_SHA"
EXIT_CODE=1

cleanup() {
  if [ "$KEEP_WORKTREE" -eq 0 ] && [ -d "$WORKTREE" ]; then
    git -C "$REPO_ROOT" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || rm -rf "$WORKTREE"
    git -C "$REPO_ROOT" worktree prune >/dev/null 2>&1 || true
  fi
  rm -f "$LOCK"
}
trap cleanup EXIT

# --- 4. Disposable, byte-exact source copy -----------------------------------
section "Creating disposable worktree"
git -C "$REPO_ROOT" worktree add --detach --quiet "$WORKTREE" "$SHA" \
  || fail "Could not create the disposable worktree."
echo "Worktree: $WORKTREE"

drift="$(git -C "$WORKTREE" status --porcelain)"
if [ -n "$drift" ]; then
  fail "The freshly created worktree is already dirty, so checkout is not
byte-exact (most likely a .gitattributes line-ending rule changed):

$drift

Refusing to run: a numerical result from a tree that does not match the commit
is not evidence."
fi
echo "Worktree is byte-exact against the commit."

mkdir -p "$OUT_DIR"

# --- 5. Image ----------------------------------------------------------------
section "Building the CI image"
build_args=(build -f "$REPO_ROOT/ci/Dockerfile" -t nltf-ci:local "$REPO_ROOT")
[ "$REBUILD" -eq 1 ] && build_args+=(--no-cache)
DOCKER_BUILDKIT=1 docker "${build_args[@]}" || fail "Image build failed."

# --- 6. Container identity ---------------------------------------------------
# Run as the invoking user, not root. The container writes into the bind-mounted
# worktree - compileall alone drops a .pyc beside every module - and root-owned
# files in a directory this script must later delete leave it unable to clean up
# after itself. Worse, they would leave the governed-tree gate reporting changes
# nobody can revert.
#
# HOME is redirected because the invoking UID has no passwd entry inside the
# image, so $HOME would otherwise resolve to / and be unwritable.
DOCKER_IDENTITY=(--user "$(id -u):$(id -g)" -e HOME=/tmp)

# --- 6b. Tier selection ------------------------------------------------------
tier_args=()
if [ "$TIER" = "affected" ]; then
  section "Planning affected tests"
  if plan_json="$(docker run --rm "${DOCKER_IDENTITY[@]}" \
        -v "${WORKTREE}:/work" \
        -v "${REPO_ROOT}/.git:/repo/.git:ro" \
        -w /work --entrypoint python nltf-ci:local \
        scripts/ci_plan.py --base "$BASE" --head "$SHA" --format json)"; then
    printf '%s' "$plan_json" > "$OUT_DIR/ci_plan.json"
    if printf '%s' "$plan_json" | grep -q '"requires_full_assurance": true'; then
      echo "Plan requires full assurance; running the full tier."
      TIER="full"
    else
      # Read the selection back with the container's Python: no host Python.
      mapfile -t tier_args < <(printf '%s' "$plan_json" | docker run --rm -i "${DOCKER_IDENTITY[@]}" \
        --entrypoint python nltf-ci:local -c \
        'import json,sys; [print(p) for p in json.load(sys.stdin)["required_test_paths"]]')
      if [ "${#tier_args[@]}" -eq 0 ]; then
        echo "Plan selected no tests. Nothing to run."
        EXIT_CODE=0
        exit 0
      fi
      echo "selected ${#tier_args[@]} test path(s)"
    fi
  else
    echo "Planner failed; escalating this run to the full tier."
    TIER="full"
  fi
elif [ "$TIER" = "replay" ] && [ -n "$ENGINE" ]; then
  tier_args=(--engine "$ENGINE")
fi

# --- 7. Run ------------------------------------------------------------------
section "Running tier: $TIER"
started=$(date +%s)
docker run --rm "${DOCKER_IDENTITY[@]}" \
  -e CI_SOURCE_SHA="$SHA" \
  -e CI_OUT_DIR=/out \
  -v "${WORKTREE}:/work" \
  -v "${OUT_DIR}:/out" \
  nltf-ci:local "$TIER" "${tier_args[@]}"
EXIT_CODE=$?
elapsed=$(( $(date +%s) - started ))

# --- 8. Mutation check -------------------------------------------------------
section "Checking the run did not mutate tracked files"
mutated="$(git -C "$WORKTREE" status --porcelain -- ':!artifacts' ':!data')"
if [ -n "$mutated" ]; then
  echo "WARNING: the run modified tracked files:"
  echo "$mutated"
  printf '%s\n' "$mutated" > "$OUT_DIR/tracked_mutations.txt"
else
  echo "No tracked file outside artifacts/ and data/ was modified."
fi

cat > "$OUT_DIR/result_${TIER}.json" <<EOF
{
  "tier": "$TIER",
  "source_sha": "$SHA",
  "base": "$BASE",
  "exit_code": $EXIT_CODE,
  "elapsed_seconds": $elapsed,
  "tracked_mutated": $([ -n "$mutated" ] && echo true || echo false),
  "output_dir": "$OUT_DIR"
}
EOF

printf "\nTier '%s' finished in %dm%02ds with exit code %d\n" \
  "$TIER" "$((elapsed / 60))" "$((elapsed % 60))" "$EXIT_CODE"
echo "Artefacts: $OUT_DIR"

exit "$EXIT_CODE"
