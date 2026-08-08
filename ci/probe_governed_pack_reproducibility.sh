#!/usr/bin/env bash
# Governed-pack reproducibility probe: one pack, one fresh disposable clone,
# two authoritative builds, value-level comparison, planner status.
#
# Generalises ci/probe_uncertainty_rebuild_reproducibility.sh to every
# governed pack, per docs/FOLLOW_UP_PED_R2_DRIFT.md question 5.
#
# Usage:
#   bash ci/probe_governed_pack_reproducibility.sh <pack> <sha> <out-dir> \
#       [harness-path]
#
#   pack      replay_cache | quarterly_display | uncertainty | policy_runtime
#   sha       commit to probe (must be reachable from $HOME/nltf-ci/repo)
#   out-dir   host directory to receive the evidence files
#   harness   path to ci/pack_reproducibility_harness.py (defaults to the
#             copy sitting next to this script)
#
# The probe never touches the committed repo: it clones, builds inside the
# nltf-ci:local Python 3.11 container, compares, and removes the clone.
set -euo pipefail

PACK="${1:?pack name required}"
SHA="${2:?sha required}"
OUT="${3:?out dir required}"
HARNESS="${4:-$(cd "$(dirname "$0")" && pwd)/pack_reproducibility_harness.py}"

REPO="$HOME/nltf-ci/repo"
WORK="/tmp/nltf-packprobe-${PACK}-$$"
CLONE="$WORK/clone"
SNAP="$WORK/snapshots"

case "$PACK" in
  replay_cache)
    PACK_DIR="data/revenue_outlook_replay_cache"
    BUILD_CMD=(scripts/build_revenue_outlook_replay_cache.py --all)
    ;;
  quarterly_display)
    PACK_DIR="data/revenue_outlook_quarterly_display"
    BUILD_CMD=(scripts/build_revenue_outlook_quarterly_display_pack.py)
    ;;
  uncertainty)
    PACK_DIR="data/revenue_outlook_uncertainty"
    BUILD_CMD=(scripts/build_revenue_outlook_uncertainty_pack.py)
    ;;
  policy_runtime)
    PACK_DIR="data/revenue_outlook_policy_runtime"
    BUILD_CMD=(scripts/build_revenue_outlook_policy_runtime.py --all)
    ;;
  *)
    echo "unknown pack: $PACK" >&2
    exit 2
    ;;
esac

mkdir -p "$OUT" "$SNAP"
trap 'rm -rf "$WORK"' EXIT

echo "== probe $PACK at $SHA =="
git clone --quiet --local "$REPO" "$CLONE"
test ! -e "$CLONE/.git/objects/info/alternates" || { echo "alternates present" >&2; exit 3; }
git -C "$CLONE" checkout --quiet --detach "$SHA"
if [ -n "$(git -C "$CLONE" status --porcelain)" ]; then
  echo "clone is not clean after checkout" >&2
  git -C "$CLONE" status --porcelain >&2
  exit 3
fi

in_docker() {
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$CLONE:/work" -v "$WORK:/probe" \
    -v "$HARNESS:/harness/pack_reproducibility_harness.py:ro" \
    -w /work --entrypoint python nltf-ci:local "$@"
}

echo "-- planner status on the committed state"
in_docker scripts/plan_governed_pack_rebuilds.py --format json \
  > "$OUT/status_committed.json"

echo "-- snapshot committed pack"
cp -a "$CLONE/$PACK_DIR" "$SNAP/committed"
in_docker /harness/pack_reproducibility_harness.py inventory \
  --pack-dir "/probe/snapshots/committed" --out "/probe/inventory_committed.json"

echo "-- build 1"
build1_rc=0
in_docker "${BUILD_CMD[@]}" > "$OUT/build1.log" 2>&1 || build1_rc=$?
echo "$build1_rc" > "$OUT/build1_exit"
if [ "$build1_rc" -ne 0 ]; then
  echo "build 1 exited $build1_rc" >&2
  tail -40 "$OUT/build1.log" >&2
  exit 4
fi
git -C "$CLONE" status --porcelain > "$OUT/build1_git_status.txt"

echo "-- compare committed vs build 1"
in_docker /harness/pack_reproducibility_harness.py compare \
  --left "/probe/snapshots/committed" --right "/work/$PACK_DIR" \
  --label "${PACK}:committed_vs_build1" \
  --out "/probe/committed_vs_build1.json" \
  --diff-parquet "/probe/committed_vs_build1_diffs.parquet"

echo "-- snapshot build 1 and build again"
cp -a "$CLONE/$PACK_DIR" "$SNAP/build1"
build2_rc=0
in_docker "${BUILD_CMD[@]}" > "$OUT/build2.log" 2>&1 || build2_rc=$?
echo "$build2_rc" > "$OUT/build2_exit"
if [ "$build2_rc" -ne 0 ]; then
  echo "build 2 exited $build2_rc" >&2
  tail -40 "$OUT/build2.log" >&2
  exit 4
fi

echo "-- compare build 1 vs build 2 (idempotency)"
in_docker /harness/pack_reproducibility_harness.py compare \
  --left "/probe/snapshots/build1" --right "/work/$PACK_DIR" \
  --label "${PACK}:build1_vs_build2" \
  --out "/probe/build1_vs_build2.json" \
  --diff-parquet "/probe/build1_vs_build2_diffs.parquet"

echo "-- planner status after the rebuilds"
in_docker scripts/plan_governed_pack_rebuilds.py --format json \
  > "$OUT/status_after.json"

for name in inventory_committed.json committed_vs_build1.json \
    committed_vs_build1_diffs.parquet build1_vs_build2.json \
    build1_vs_build2_diffs.parquet; do
  if [ -f "$WORK/$name" ]; then
    cp "$WORK/$name" "$OUT/$name"
  fi
done

echo "== probe $PACK complete; evidence in $OUT =="
