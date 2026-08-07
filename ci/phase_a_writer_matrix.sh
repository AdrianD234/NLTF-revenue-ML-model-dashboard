#!/usr/bin/env bash
# Phase A: which invocation writes artifacts/chart_sources, and with what content?
#
# The cleanliness gate proved that tracked chart-source files move during test
# runs, and that the final content depends on execution context. It did NOT
# establish why. Four explanations remain open:
#
#   * test selection / order, last writer wins
#   * differing data roots or engines
#   * process cache state
#   * Python / library / platform effects
#
# This runs each writer module ALONE, sequentially, from the committed state,
# inside the Python 3.11 container - so every run differs only in which module
# ran. If the results differ, it is the caller, not the environment.
#
# The complete suite is deliberately NOT run here.
#
# Usage: bash ci/phase_a_writer_matrix.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

EV="$REPO_ROOT/artifacts/ci_optimisation/phase_a"
mkdir -p "$EV"

FILES=(
  "artifacts/chart_sources/r2_ladder_summary.csv"
  "artifacts/chart_sources/r2_reproducibility_gap_register.csv"
  "artifacts/chart_sources/r2_training_fit_detail.csv"
)

MODULES=(
  tests/test_r2_ladder.py
  tests/test_r2_metrics.py
  tests/test_chart_source_tables.py
  tests/test_chart_data_reconciliation.py
  tests/test_evidence_pack.py
  tests/test_light_ruc_reproducibility_pack.py
  tests/test_performance_budget.py
)

REPORT="$EV/writer_matrix.csv"
echo "module,file,before_sha256,after_sha256,changed,ped_calibration_r2_operational,ped_calibration_r2_paper" > "$REPORT"

in_container() {
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$REPO_ROOT:/work" -w /work --entrypoint "$1" nltf-ci:local "${@:2}"
}

# Pull the two PED calibration_r2 values the incident moved, so the matrix shows
# governed numbers rather than only hashes.
read_r2() {
  in_container python - <<'PY' 2>/dev/null || echo "unreadable,unreadable"
import csv, pathlib
path = pathlib.Path("artifacts/chart_sources/r2_ladder_summary.csv")
out = []
try:
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("stream", "").startswith("PED VKT per capita"):
                out.append(row.get("calibration_r2", ""))
except Exception:
    pass
while len(out) < 2:
    out.append("")
print(",".join(out[:2]))
PY
}

echo "Restoring chart sources to the committed state before we begin."
git checkout -- "${FILES[@]}" 2>/dev/null || true

for module in "${MODULES[@]}"; do
  printf '\n\n############ %s ############\n' "$module"

  # Always start from the committed content, so every row is comparable.
  git checkout -- "${FILES[@]}" 2>/dev/null || true

  declare -A BEFORE
  for f in "${FILES[@]}"; do BEFORE[$f]="$(sha256sum "$f" | cut -d' ' -f1)"; done
  r2_before="$(read_r2)"

  log="$EV/$(basename "$module" .py).log"
  in_container python -m pytest -q -p no:cacheprovider \
    -m "not e2e and not requires_local_scratch" "$module" > "$log" 2>&1
  code=$?
  echo "exit=$code  $(grep -oE '[0-9]+ (passed|failed|skipped)[^=]*' "$log" | tail -1)"

  r2_after="$(read_r2)"

  for f in "${FILES[@]}"; do
    after="$(sha256sum "$f" | cut -d' ' -f1)"
    changed="no"
    [ "${BEFORE[$f]}" != "$after" ] && changed="YES"
    echo "$module,$f,${BEFORE[$f]:0:16},${after:0:16},$changed,$r2_after" >> "$REPORT"
    if [ "$changed" = "YES" ]; then
      echo "  CHANGED $f  ${BEFORE[$f]:0:16} -> ${after:0:16}"
    fi
  done
  echo "  PED calibration_r2 before=[$r2_before] after=[$r2_after]"
done

# Leave the tree exactly as we found it. This diagnosis must not itself become
# the thing that moves a governed value.
git checkout -- "${FILES[@]}" 2>/dev/null || true

printf '\n\n############ WRITER MATRIX ############\n'
column -s, -t < "$REPORT"
printf '\nTracked chart sources restored: %s\n' "$(git status --porcelain -- artifacts/chart_sources | wc -l) modified"
