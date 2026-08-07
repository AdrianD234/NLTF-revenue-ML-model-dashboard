#!/usr/bin/env bash
# Does rebuilding the uncertainty pack IN THE CONTAINER reproduce the committed
# pack, on an otherwise unmodified tree?
#
# The calculation-lane proof ended with exactly two failures, both comparing
# uncertainty band values at rtol=0, atol=1e-9:
#
#   test_delayed_state_reproduces_the_committed_offline_uncertainty_pack
#   test_the_uncertainty_band_rows_are_numerically_unchanged
#
# Two explanations, with very different consequences:
#
#   a) the probe's edit to rate_paths.py moved the band centre - implausible,
#      it appended a comment;
#   b) rebuilding the pack in Linux/Python 3.11 does not reproduce a pack that
#      was committed from a different environment.
#
# (b) would be a real constraint on the workflow: it would mean a governed pack
# rebuild moves published values purely by changing where it runs.
#
# This isolates it. No probe edit, no other pack, unmodified base commit -
# rebuild the uncertainty pack alone and diff it against the committed one.
#
# Runs in a disposable clone; the branch is never touched.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EV="$REPO_ROOT/artifacts/ci_optimisation/phase_a"
mkdir -p "$EV"

BASE_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
PROBE="/tmp/nltf-uncprobe-$$"

cleanup() { local s=$?; rm -rf "$PROBE"; exit "$s"; }
trap cleanup EXIT

echo "=== disposable clone at $BASE_SHA (UNMODIFIED) ==="
git clone --quiet --local "$REPO_ROOT" "$PROBE"
git -C "$PROBE" checkout --quiet --detach "$BASE_SHA"
[ -z "$(git -C "$PROBE" status --porcelain)" ] || { echo "clone dirty"; exit 2; }

TARGET="data/revenue_outlook_uncertainty/uncertainty_band_rows.parquet"
cp "$PROBE/$TARGET" /tmp/unc_committed.parquet

echo
echo "=== rebuilding the uncertainty pack in the container ==="
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PROBE:/work" -w /work --entrypoint python nltf-ci:local \
  scripts/build_revenue_outlook_uncertainty_pack.py > "$EV/unc_rebuild.log" 2>&1
code=$?
tail -3 "$EV/unc_rebuild.log"
echo "rebuild exit=$code"
[ "$code" -eq 0 ] || exit "$code"

echo
echo "=== did the file change at all? ==="
git -C "$PROBE" status --porcelain -- data/revenue_outlook_uncertainty || true

echo
echo "=== numeric comparison ==="
cp "$PROBE/$TARGET" /tmp/unc_rebuilt.parquet
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v /tmp:/data --entrypoint python nltf-ci:local -c '
import pandas as pd, numpy as np
a = pd.read_parquet("/data/unc_committed.parquet")
b = pd.read_parquet("/data/unc_rebuilt.parquet")
print(f"rows committed={len(a)} rebuilt={len(b)}")
if len(a) != len(b) or list(a.columns) != list(b.columns):
    print("STRUCTURAL DIFFERENCE"); raise SystemExit(0)
keys = ["series_id", "FY"]
a = a.sort_values(keys).reset_index(drop=True)
b = b.sort_values(keys).reset_index(drop=True)
worst_overall = 0.0
for col in ("central", "lower80", "lower50", "upper50", "upper80"):
    if col not in a.columns:
        continue
    x, y = a[col].to_numpy(float), b[col].to_numpy(float)
    diff = np.abs(x - y)
    n = int((diff > 1e-9).sum())
    worst = float(np.nanmax(diff)) if len(diff) else 0.0
    scale = float(np.nanmax(np.abs(x))) if len(x) else 1.0
    rel = worst / scale if scale else 0.0
    worst_overall = max(worst_overall, rel)
    print(f"  {col:9s} rows_over_1e-9={n:5d}  max_abs_diff={worst:.6e}  "
          f"max_rel={rel:.3e}")
print()
if worst_overall == 0:
    print("VERDICT: byte-for-byte identical values. The rebuild reproduces exactly.")
elif worst_overall < 1e-12:
    print("VERDICT: floating-point noise only (relative < 1e-12).")
else:
    print(f"VERDICT: values MOVED, worst relative {worst_overall:.3e}.")
    print("A pack rebuild in this environment does not reproduce the committed pack.")
'
