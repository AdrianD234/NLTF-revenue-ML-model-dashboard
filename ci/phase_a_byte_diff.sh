#!/usr/bin/env bash
# Phase A addendum 3: at byte level, what distinguishes the regenerated
# chart source from the committed one?
#
# The column-level comparison found NO cell difference, yet every line in the
# file changed. That pattern - all lines differ, no value differs - is the
# signature of a line-ending rewrite, not a data change. Confirm it, because the
# distinction decides whether this is a governance incident or a nuisance.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

T="artifacts/chart_sources/r2_ladder_summary.csv"

git checkout -- "$T" 2>/dev/null || true

crlf_count() { grep -c $'\r' "$1" 2>/dev/null || echo 0; }

echo "=== COMMITTED ==="
echo "  bytes    : $(wc -c < "$T")"
echo "  lines    : $(wc -l < "$T")"
echo "  CR lines : $(crlf_count "$T")"
cp "$T" /tmp/committed.csv

echo
echo "=== regenerating (tests/test_r2_ladder.py alone) ==="
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$REPO_ROOT:/work" -w /work --entrypoint python nltf-ci:local \
  -m pytest -q -p no:cacheprovider tests/test_r2_ladder.py > /dev/null 2>&1

echo "=== REGENERATED ==="
echo "  bytes    : $(wc -c < "$T")"
echo "  lines    : $(wc -l < "$T")"
echo "  CR lines : $(crlf_count "$T")"
cp "$T" /tmp/regenerated.csv

git checkout -- "$T" 2>/dev/null || true

echo
echo "=== identical after removing CR? ==="
tr -d '\r' < /tmp/committed.csv > /tmp/committed_lf.csv
tr -d '\r' < /tmp/regenerated.csv > /tmp/regenerated_lf.csv
if cmp -s /tmp/committed_lf.csv /tmp/regenerated_lf.csv; then
  echo "  YES - identical once carriage returns are ignored."
  echo "  The regeneration is a LINE-ENDING rewrite. No value moved."
else
  echo "  NO - content genuinely differs:"
  diff /tmp/committed_lf.csv /tmp/regenerated_lf.csv | head -10
fi

echo
echo "restored: $(git status --porcelain -- "$T" | wc -l) modified"
