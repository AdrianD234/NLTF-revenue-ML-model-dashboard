#!/usr/bin/env bash
# Phase B: the bounded PED calibration-R² writer/worker matrix.
#
# Proves, in a fresh disposable clone inside the Python 3.11 container:
#   A. what each ENGINE identity computes (ensemble vs ar1), one writer at a
#      time, sequentially — with full input identity recorded;
#   B. that the writer modules in their normal sequential order leave the
#      tracked chart sources byte-identical and produce the committed values;
#   C/D. that isolated two- and four-worker xdist runs (load, loadscope,
#      loadfile) leave the tracked tree unchanged and every worker-scoped
#      output carries its own single identity;
#   F. that a deliberately SHARED destination (the pre-fix world, recreated in
#      scratch via the env override the fix introduced) lets the last writer
#      decide the published value — the mechanism of the original incident.
#
# Usage: bash ci/phase_b_r2_matrix.sh <sha> <out-dir> [audit-tool-path]
set -euo pipefail

SHA="${1:?sha required}"
OUT="${2:?out dir required}"
AUDIT="${3:-$(cd "$(dirname "$0")" && pwd)/r2_writer_audit.py}"

REPO="$HOME/nltf-ci/repo"
WORK="/tmp/nltf-r2matrix-$$"
CLONE="$WORK/clone"
mkdir -p "$OUT" "$WORK"
trap 'rm -rf "$WORK"' EXIT

git clone --quiet --local "$REPO" "$CLONE"
git -C "$CLONE" checkout --quiet --detach "$SHA"
test -z "$(git -C "$CLONE" status --porcelain)" || { echo "clone dirty" >&2; exit 3; }

CHART_BASELINE="$(git -C "$CLONE" hash-object \
  "$CLONE/artifacts/chart_sources/r2_ladder_summary.csv" \
  "$CLONE/artifacts/chart_sources/r2_reproducibility_gap_register.csv" \
  "$CLONE/artifacts/chart_sources/r2_training_fit_detail.csv")"

in_docker() {
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$CLONE:/work" -v "$WORK:/probe" \
    -v "$AUDIT:/harness/r2_writer_audit.py:ro" \
    -w /work "$@"
}

extract_values() {
  # $1 = path (host) of a chart-source dir; prints "basis=value" lines
  python3 - "$1" <<'PY'
import csv, sys
from pathlib import Path
path = Path(sys.argv[1]) / "r2_ladder_summary.csv"
if not path.exists():
    print("absent")
    raise SystemExit(0)
with path.open(encoding="utf-8", newline="") as handle:
    for row in csv.DictReader(handle):
        if row.get("stream_label") == "PED VKT per capita":
            print(f"{row['score_basis']}={row['calibration_r2']} model={row['model']}")
PY
}

assert_tracked_unchanged() {
  local label="$1"
  local now
  now="$(git -C "$CLONE" hash-object \
    "$CLONE/artifacts/chart_sources/r2_ladder_summary.csv" \
    "$CLONE/artifacts/chart_sources/r2_reproducibility_gap_register.csv" \
    "$CLONE/artifacts/chart_sources/r2_training_fit_detail.csv")"
  if [ "$now" != "$CHART_BASELINE" ]; then
    echo "TRACKED CHART SOURCES MUTATED during $label" | tee -a "$OUT/matrix.log"
    git -C "$CLONE" status --porcelain | tee -a "$OUT/matrix.log"
    exit 5
  fi
  echo "tracked chart sources byte-identical after $label" >> "$OUT/matrix.log"
}

WRITERS="tests/test_r2_ladder.py tests/test_r2_metrics.py tests/test_chart_source_tables.py tests/test_chart_data_reconciliation.py tests/test_evidence_pack.py tests/test_score_basis_governance.py tests/test_stress_horizon_aliases.py"

echo "== A. engine identity audits ==" | tee "$OUT/matrix.log"
for engine in ensemble ar1; do
  in_docker --entrypoint python nltf-ci:local /harness/r2_writer_audit.py \
    --engine "$engine" --out "/probe/audit_${engine}.json" \
    --chart-output-dir "/probe/chart_${engine}" \
    > "$OUT/audit_${engine}.stdout" 2>&1
  cp "$WORK/audit_${engine}.json" "$OUT/"
  echo "-- $engine:" | tee -a "$OUT/matrix.log"
  extract_values "$WORK/chart_${engine}" | tee -a "$OUT/matrix.log"
done
assert_tracked_unchanged "engine audits"

echo "== B. sequential writer modules, normal order ==" | tee -a "$OUT/matrix.log"
in_docker --entrypoint python nltf-ci:local -m pytest -q -p no:cacheprovider \
  $WRITERS > "$OUT/seq_writers.log" 2>&1 || { tail -30 "$OUT/seq_writers.log"; exit 6; }
assert_tracked_unchanged "sequential writers"
for dir in "$CLONE"/test-output/chart_sources/*/; do
  echo "-- $(basename "$dir"):" | tee -a "$OUT/matrix.log"
  extract_values "$dir" | tee -a "$OUT/matrix.log"
done
rm -rf "$CLONE/test-output"

run_xdist() {
  local n="$1"
  local dist="$2"
  local label="xdist_n${n}_${dist}"
  echo "== C/D. $label ==" | tee -a "$OUT/matrix.log"
  in_docker --entrypoint python nltf-ci:local -m pytest -q -p no:cacheprovider \
    -n "$n" --dist "$dist" $WRITERS > "$OUT/${label}.log" 2>&1 \
    || { tail -30 "$OUT/${label}.log"; exit 6; }
  assert_tracked_unchanged "$label"
  for dir in "$CLONE"/test-output/chart_sources/*/; do
    echo "-- $label $(basename "$dir"):" | tee -a "$OUT/matrix.log"
    extract_values "$dir" | tee -a "$OUT/matrix.log"
  done
  rm -rf "$CLONE/test-output"
}

run_xdist 2 load
run_xdist 4 load
run_xdist 2 loadscope
run_xdist 4 loadscope
run_xdist 4 loadfile

echo "== F. shared destination (pre-fix world, in scratch) ==" | tee -a "$OUT/matrix.log"
for rep in 1 2 3; do
  rm -rf "$WORK/shared_dest"
  mkdir -p "$WORK/shared_dest"
  in_docker -e NLTF_CHART_SOURCE_OUTPUT_DIR=/probe/shared_dest \
    --entrypoint python nltf-ci:local -m pytest -q -p no:cacheprovider \
    -n 4 --dist loadscope $WRITERS tests/test_streamlit_smoke.py \
    > "$OUT/shared_rep${rep}.log" 2>&1 || true
  assert_tracked_unchanged "shared-destination rep $rep"
  echo "-- shared rep $rep final content:" | tee -a "$OUT/matrix.log"
  extract_values "$WORK/shared_dest" | tee -a "$OUT/matrix.log"
  rm -rf "$CLONE/test-output"
done

echo "MATRIX_DONE" | tee -a "$OUT/matrix.log"
