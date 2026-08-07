#!/usr/bin/env bash
# Preflight for the final local acceptance run.
#
# Every one of these has already gone wrong once during this project, which is
# why each is checked rather than assumed:
#
#   * a benchmark started while another pytest was live (invalidated the timing)
#   * a long run started against a SHA that was then superseded
#   * a run started from a dirty clone
#   * a background run died with the shell that launched it
#
# Exits non-zero on the first problem. Nothing here starts a container or a test.

set -uo pipefail

WANT_SHA="${1:?usage: phase_d_preflight.sh <expected-sha>}"
REPO="$HOME/nltf-ci/repo"

fail() { printf '\nPREFLIGHT FAILED: %s\n' "$*" >&2; exit 1; }
ok() { printf '  ok   %s\n' "$*"; }

echo "=== Phase D preflight ==="

# 1. No pytest controller anywhere.
running="$(pgrep -c -f '[p]ytest' 2>/dev/null || echo 0)"
[ "$running" -eq 0 ] || fail "$running pytest process(es) already running"
ok "no pytest process"

# 2. No CI container.
containers="$(docker ps -q --filter ancestor=nltf-ci:local | wc -l)"
[ "$containers" -eq 0 ] || fail "$containers nltf-ci container(s) still running"
ok "no CI container running"

# 3. No stale disposable clone or lock left by a killed run.
stale="$(ls -d /tmp/nltf-ci-* 2>/dev/null | wc -l)"
[ "$stale" -eq 0 ] || fail "$stale stale disposable clone(s) under /tmp"
ok "no stale disposable clones"
[ ! -e "$REPO/artifacts/ci_local/.lock" ] || fail "a local CI lock is still held"
ok "no CI lock held"

# 4. The clone is at the SHA we intend to test.
head="$(git -C "$REPO" rev-parse HEAD)"
case "$head" in
  "$WANT_SHA"*) ok "clone HEAD is $WANT_SHA" ;;
  *) fail "clone HEAD is ${head:0:12}, expected $WANT_SHA" ;;
esac

# 5. Byte-exact against that commit.
drift="$(git -C "$REPO" status --porcelain)"
[ -z "$drift" ] || fail "clone is dirty:
$drift"
ok "clone is clean"

# 6. Every governed pack current on the unmodified branch.
if ! docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
      -v "$REPO:/work" -w /work --entrypoint python nltf-ci:local \
      scripts/plan_governed_pack_rebuilds.py --fail-on-stale > /tmp/preflight_packs.log 2>&1; then
  cat /tmp/preflight_packs.log >&2
  fail "governed packs are not all current on the unmodified branch"
fi
grep -E '^\s+(REBUILD)?\s*\w+\s+(ok|not affected)' /tmp/preflight_packs.log | sed 's/^/  /'
ok "all five governed packs report current"

# 7. Somewhere to write, and enough room.
mkdir -p "$REPO/artifacts/ci_optimisation/phase2" || fail "cannot create the evidence directory"
free_gb="$(df -BG --output=avail /tmp | tail -1 | tr -dc '0-9')"
[ "${free_gb:-0}" -ge 5 ] || fail "only ${free_gb}G free on /tmp; the clone needs headroom"
ok "evidence directory writable, ${free_gb}G free on /tmp"

echo
echo "PREFLIGHT PASSED — safe to start the final sequence on $WANT_SHA"
