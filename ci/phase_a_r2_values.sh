#!/usr/bin/env bash
# Phase A addendum: the governed R-squared values behind the writer-matrix hashes.
#
# The matrix showed every writer module, run alone, produces one identical
# output that differs from the committed file. This prints the actual numbers,
# because a hash tells you something moved and not what it moved to.
#
# Restores the tree afterwards. Nothing here promotes anything.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TARGET="artifacts/chart_sources/r2_ladder_summary.csv"

read_values() {
  docker run --rm -i --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$REPO_ROOT:/work" -w /work --entrypoint python nltf-ci:local - <<'PY'
import csv, pathlib
path = pathlib.Path("artifacts/chart_sources/r2_ladder_summary.csv")
with path.open(encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
        if row.get("stream", "").startswith("PED VKT per capita"):
            print(f"  {row.get('score_basis','?'):32s} calibration_r2={row.get('calibration_r2','')}")
PY
}

git checkout -- "$TARGET" 2>/dev/null || true
echo "=== COMMITTED (sha $(sha256sum "$TARGET" | cut -c1-16)) ==="
read_values

echo
echo "=== regenerating via tests/test_r2_ladder.py alone ==="
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$REPO_ROOT:/work" -w /work --entrypoint python nltf-ci:local \
  -m pytest -q -p no:cacheprovider tests/test_r2_ladder.py > /dev/null 2>&1

echo "=== REGENERATED (sha $(sha256sum "$TARGET" | cut -c1-16)) ==="
read_values

echo
echo "=== diff of the changed rows ==="
git diff --unified=0 -- "$TARGET" | grep -E '^[-+].*PED VKT per capita' \
  | sed -E 's/^(.).*calibration_r2[^,]*//; s/(.{200}).*/\1.../' || true
git diff --stat -- "$TARGET"

git checkout -- "$TARGET" 2>/dev/null || true
echo
echo "restored: $(git status --porcelain -- "$TARGET" | wc -l) modified"
