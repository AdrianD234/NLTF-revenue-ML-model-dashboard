#!/usr/bin/env bash
# Tier dispatcher for the local clean-room CI image.
#
# Contract with scripts/ci_local.*:
#   * /work        is a read-consistent, byte-exact copy of the tracked tree
#   * /out         is where every artefact this run produces must land
#   * the exit code is the real exit code of the tier's decisive command
#
# Nothing here writes to the caller's checkout. Nothing here promotes a pack.

set -uo pipefail

TIER="${1:-fast}"
shift || true

OUT="${CI_OUT_DIR:-/out}"
mkdir -p "$OUT"

# Fail-closed on the one mistake that would invalidate every result below:
# running against a tree that is not the one the caller thinks it is.
if [ ! -f /work/pytest.ini ]; then
  echo "FATAL: /work does not look like the repository (no pytest.ini)" >&2
  exit 2
fi

cd /work

cp /image_environment.json "$OUT/image_environment.json" 2>/dev/null || true

log() { printf '\n=== %s ===\n' "$*"; }

# Every tier records the tree it ran against, so a result can never be
# attributed to the wrong source state.
{
  echo "tier=$TIER"
  echo "source_sha=${CI_SOURCE_SHA:-unknown}"
  echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$OUT/run_context.txt"

# Deterministic curated data. Cheap (~1s) and required by tests that would
# otherwise fail for a reason that has nothing to do with the change.
prepare_curated_data() {
  log "Rebuild curated data from the committed pack"
  python scripts/regenerate_curated_data_from_pack.py
}

# --- governed-tree cleanliness gate ------------------------------------------
# A parallel test run once rewrote artifacts/chart_sources/r2_ladder_summary.csv
# and moved a governed PED calibration R-squared from 0.559 to 0.580, with every
# test still passing. See artifacts/ci_optimisation/xdist_benchmark.md. Every
# tier now proves it left the governed tree exactly as it found it.
GATE_SNAPSHOT="$OUT/governed_tree_before.json"
GATE_ARMED=0

# Arm the gate. From here the EXIT trap verifies on EVERY exit path - including
# a failing test suite, a failing later step, and `exit $?` partway through a
# tier. An explicit "verify after the suite" call would miss the steps that run
# after it, which is exactly where a materialisation step could move a pack.
gate_arm() {
  if python scripts/assert_governed_tree_unchanged.py --snapshot "$GATE_SNAPSHOT" \
       > "$OUT/governed_tree_snapshot.log" 2>&1; then
    GATE_ARMED=1
  else
    echo "WARNING: could not snapshot the governed tree; cleanliness cannot be proven" >&2
    cat "$OUT/governed_tree_snapshot.log" >&2 || true
  fi
}

# The tier's own verdict dominates. A lane that mutated governed content must
# never report success, but it must also never mask a real test failure with a
# cleanliness code - so a failing suite keeps its own exit status.
gate_on_exit() {
  local original=$?
  [ "$GATE_ARMED" -eq 1 ] || exit "$original"
  GATE_ARMED=0  # disarm: an exit inside the trap must not re-enter it

  printf '\n=== Verifying the run did not mutate governed content ===\n'
  python scripts/assert_governed_tree_unchanged.py --verify "$GATE_SNAPSHOT" \
    > "$OUT/governed_tree_verify.log" 2>&1
  local gate=$?
  cat "$OUT/governed_tree_verify.log"

  if [ "$gate" -ne 0 ]; then
    echo "" >&2
    echo "FAILING: this lane modified tracked or governed content (see above)." >&2
    if [ "$original" -eq 0 ]; then
      exit 3
    fi
  fi
  exit "$original"
}

trap gate_on_exit EXIT

PYTEST_BASE=(python -m pytest -q -m "not e2e and not requires_local_scratch")

case "$TIER" in

  fast)
    # Target: <= 5 minutes warm. Compile, imports, planner, changed-module units.
    log "Compile all sources"
    python -m compileall -q . || exit $?

    log "Import smoke"
    python -c "import app" >/dev/null || exit $?

    log "Change planner tests"
    python -m pytest -q tests/test_ci_plan.py || exit $?

    if [ "$#" -gt 0 ]; then
      log "Changed-module unit tests"
      prepare_curated_data
      gate_arm
      python -m pytest -q -m "not e2e and not requires_local_scratch" \
        --junitxml="$OUT/junit_fast.xml" "$@"
      suite_status=$?
      exit "$suite_status"
    fi
    echo "No selected tests passed to the fast tier; compile + smoke + planner only."
    exit 0
    ;;

  affected)
    # Target: <= 15 minutes. Everything fast does, plus the planner's selection.
    log "Compile all sources"
    python -m compileall -q . || exit $?
    prepare_curated_data

    if [ "$#" -eq 0 ]; then
      echo "affected tier received no test selection; nothing to prove." >&2
      echo "Run scripts/ci_local.* which passes the ci_plan.py selection through." >&2
      exit 2
    fi

    gate_arm
    log "Planner-selected tests"
    "${PYTEST_BASE[@]}" --junitxml="$OUT/junit_affected.xml" "$@"
    suite_status=$?
    exit "$suite_status"
    ;;

  full)
    # The present clean-clone assurance, reproduced exactly. Step order matches
    # .github/workflows/ci.yml so a disagreement is a real disagreement.
    log "Compile all sources"
    python -m compileall -q . || exit $?

    prepare_curated_data

    log "GDP sign-guard binding register"
    python scripts/audit_gdp_sign_guard_bindings.py || exit $?

    log "Report clean-clone coverage"
    python -m pytest -q --collect-only -m "not e2e and not requires_local_scratch" \
      2>/dev/null | tail -3 || true
    echo "--- excluded from the clean-clone claim ---"
    python -m pytest -q --collect-only -m "requires_local_scratch" 2>/dev/null | tail -3 || true

    gate_arm

    log "Core test suite"
    "${PYTEST_BASE[@]}" --junitxml="$OUT/junit_full.xml" "$@"
    suite_status=$?


    log "Conflict scenario extract validation"
    python scripts/materialize_conflict_scenario_extract.py \
      --output-dir "$OUT/conflict_scenario_extract" || exit $?
    python - "$OUT/conflict_scenario_extract/conflict_scenario_validation.csv" <<'PY'
import pathlib
import sys

import pandas as pd

frame = pd.read_csv(pathlib.Path(sys.argv[1]))
passed = frame["passed"].astype(str).str.lower().isin(["true", "1"])
print(f"{int(passed.sum())}/{len(frame)} extract validations passed")
if not passed.all():
    print(frame.loc[~passed, ["check_id", "observed"]].to_string(index=False))
    sys.exit(1)
PY
    extract_status=$?

    log "Streamlit deployment readiness"
    python scripts/check_streamlit_deploy_readiness.py
    deploy_status=$?

    # The suite's verdict dominates, but a later step failing must not be lost,
    # and a lane that mutated governed content never reports success.
    if [ "$suite_status" -ne 0 ]; then exit "$suite_status"; fi
    if [ "$extract_status" -ne 0 ]; then exit "$extract_status"; fi
    exit "$deploy_status"
    ;;

  profile)
    # Timing evidence only. No pack rebuild, no promotion.
    prepare_curated_data
    gate_arm
    log "Profiling run"
    "${PYTEST_BASE[@]}" \
      --durations=200 --durations-min=0.5 \
      --junitxml="$OUT/junit_profile.xml" \
      "$@" 2>&1 | tee "$OUT/profile_run.log"
    suite_status="${PIPESTATUS[0]}"
    exit "$suite_status"
    ;;

  replay)
    # Cross-environment replay fingerprint, the same one the hosted matrix runs.
    log "Governed replay fingerprint"
    python scripts/replay_parity_fingerprint.py --output "$OUT/replay_parity" "$@"
    exit $?
    ;;

  pack-status)
    log "Governed pack rebuild plan (status only, nothing is rebuilt)"
    python scripts/plan_governed_pack_rebuilds.py --format human "$@"
    exit $?
    ;;

  databricks-bundle)
    log "Build the Databricks App bundle"
    python scripts/build_databricks_app_bundle.py \
      --source . --output "$OUT/databricks_app/app" --clean || exit $?
    log "Validate the bundle"
    python scripts/validate_databricks_app_bundle.py \
      --bundle "$OUT/databricks_app/app" --source .
    exit $?
    ;;

  shell)
    exec /bin/bash "$@"
    ;;

  *)
    echo "Unknown tier: $TIER" >&2
    echo "Tiers: fast affected full profile replay pack-status databricks-bundle shell" >&2
    exit 2
    ;;
esac
