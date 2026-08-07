#!/usr/bin/env bash
# Phase A addendum 2: WHAT changes in the regenerated chart sources?
#
# The R-squared reader showed the two PED calibration_r2 values are identical
# before and after, yet seven rows differ. Before anyone concludes a governed
# number moved, establish which columns actually change.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TARGET="artifacts/chart_sources/r2_ladder_summary.csv"

git checkout -- "$TARGET" 2>/dev/null || true
cp "$TARGET" /tmp/committed_r2.csv

docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$REPO_ROOT:/work" -w /work --entrypoint python nltf-ci:local \
  -m pytest -q -p no:cacheprovider tests/test_r2_ladder.py > /dev/null 2>&1

cp "$TARGET" /tmp/regenerated_r2.csv
git checkout -- "$TARGET" 2>/dev/null || true

docker run --rm -i --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v /tmp:/data --entrypoint python nltf-ci:local - <<'PY'
import csv

def load(path):
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))

before = load("/data/committed_r2.csv")
after = load("/data/regenerated_r2.csv")

print(f"rows: committed={len(before)} regenerated={len(after)}")
if len(before) != len(after):
    print("ROW COUNT DIFFERS - structural change")

key = lambda r: (r.get("stream", ""), r.get("score_basis", ""), r.get("r2_type", ""))
b_by = {key(r): r for r in before}
a_by = {key(r): r for r in after}

print(f"keys only in committed:   {sorted(set(b_by) - set(a_by))[:5]}")
print(f"keys only in regenerated: {sorted(set(a_by) - set(b_by))[:5]}")
print()

changed_cols = {}
for k in sorted(set(b_by) & set(a_by)):
    for col in b_by[k]:
        bv, av = b_by[k].get(col, ""), a_by[k].get(col, "")
        if bv != av:
            changed_cols.setdefault(col, []).append((k, bv, av))

if not changed_cols:
    print("No cell differs. The change must be ordering or formatting only.")
else:
    print("COLUMNS THAT DIFFER:")
    for col, items in sorted(changed_cols.items()):
        print(f"\n  {col}  ({len(items)} row(s))")
        for k, bv, av in items[:6]:
            print(f"    {k[0]} / {k[1]}")
            print(f"      committed   : {str(bv)[:90]}")
            print(f"      regenerated : {str(av)[:90]}")
PY
