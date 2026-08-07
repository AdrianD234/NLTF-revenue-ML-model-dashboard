#!/usr/bin/env bash
# Phase 3 of the bundle-probe abort diagnosis: name the thread that dies badly.
#
# Established so far (ci/hotfix_probe_matrix.sh, artifacts/.../probe_matrix/):
#   * the abort is INTERMITTENT, not deterministic (same case: -6 then 0);
#   * it occurs on the last-good SHA as well as the merge - the merge is
#     exonerated;
#   * hosted dependency resolution was identical between the passing Aug 6 run
#     and the failing Aug 7 runs - no drift;
#   * JSON is complete in every aborting run: the crash is strictly AFTER the
#     probe's last Python statement, in interpreter/native teardown.
#
# This harness reruns the exact probe with teardown instrumentation:
#   * PYTHONFAULTHANDLER=1  - on SIGABRT, dumps every thread's Python stack;
#   * PYTHONUNBUFFERED=1    - nothing lost in a dying process's buffers;
#   * a thread census + loaded-native-module list appended after the probe's
#     final print, i.e. the last Python to run before teardown;
#   * an atexit marker, so "abort before vs after Python finalisation began"
#     is decidable from the output.
#
# The probe body is byte-identical to the validator's _PROBE; instrumentation
# is appended AFTER its last statement and changes nothing it measures.
# The validator itself is not modified. Nothing here publishes anything.
#
# Usage: bash ci/phase3_instrumented_probe.sh [N_RUNS]

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EV="$REPO_ROOT/artifacts/ci_optimisation/probe_matrix/phase3"
mkdir -p "$EV"

SHA="5e9d2d2840050c8ff0f063f8567030791d6950ef"   # merge tip; abort exists on both SHAs
N_RUNS="${1:-8}"
CLONE="/tmp/nltf-phase3-$$"

cleanup() { local s=$?; rm -rf "$CLONE"; exit "$s"; }
trap cleanup EXIT

banner() { printf '\n\n############ %s ############\n' "$*"; }

banner "disposable clone at ${SHA:0:7}"
git clone --quiet --local "$REPO_ROOT" "$CLONE"
git -C "$CLONE" checkout --quiet --detach "$SHA"
[ -z "$(git -C "$CLONE" status --porcelain)" ] || { echo "clone dirty"; exit 2; }

banner "building the bundle once"
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$CLONE:/work" -w /work --entrypoint python nltf-publish-probe:local \
  scripts/build_databricks_app_bundle.py --source . --output build/databricks_app/app --clean \
  > "$EV/bundle_build.log" 2>&1 || { tail -5 "$EV/bundle_build.log"; exit 2; }

banner "extracting the probe and appending instrumentation"
docker run --rm -i --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$CLONE:/work" -w /work --entrypoint python nltf-publish-probe:local - <<'PY'
import importlib.util, pathlib

spec = importlib.util.spec_from_file_location(
    "vdb", "scripts/validate_databricks_app_bundle.py"
)
vdb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vdb)

instrumentation = '''

# ===== phase3 teardown instrumentation (appended by diagnosis harness) =====
import sys as _p3_sys, threading as _p3_threading, atexit as _p3_atexit
print("===THREAD-CENSUS-BEGIN===")
for _t in _p3_threading.enumerate():
    print(f"thread name={_t.name!r} daemon={_t.daemon} alive={_t.is_alive()}")
_p3_mods = [m for m in ("pyarrow", "streamlit", "tornado", "watchdog",
                        "google.protobuf", "numpy", "pandas", "PIL",
                        "openpyxl", "plotly", "altair", "pydeck")
            if m in _p3_sys.modules]
print("native-backed modules loaded:", ", ".join(_p3_mods))
print("===THREAD-CENSUS-END===", flush=True)
_p3_atexit.register(lambda: print("===ATEXIT-REACHED===", flush=True))
'''

pathlib.Path("phase3_probe.py").write_text(vdb._PROBE + instrumentation, encoding="utf-8")
print("wrote phase3_probe.py:", len(vdb._PROBE.splitlines()), "probe lines + instrumentation")
PY

banner "running the instrumented probe $N_RUNS times (bundle cwd, publish env)"
SUMMARY="$EV/phase3_summary.txt"
: > "$SUMMARY"
aborts=0
for RUN in $(seq 1 "$N_RUNS"); do
  TAG="p3_run${RUN}"
  docker run --rm --user "$(id -u):$(id -g)" \
    -e HOME=/tmp -e PYTHONFAULTHANDLER=1 -e PYTHONUNBUFFERED=1 \
    -e STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    -v "$CLONE:/repo" -w /repo/build/databricks_app/app \
    --entrypoint python nltf-publish-probe:local /repo/phase3_probe.py \
    > "$EV/$TAG.stdout.txt" 2> "$EV/$TAG.stderr.txt"
  code=$?

  json_ok="no"; grep -q "===PROBE-JSON-END===" "$EV/$TAG.stdout.txt" && json_ok="yes"
  census="no";  grep -q "===THREAD-CENSUS-END===" "$EV/$TAG.stdout.txt" && census="yes"
  atexit_ok="no"; grep -q "===ATEXIT-REACHED===" "$EV/$TAG.stdout.txt" && atexit_ok="yes"
  abort="no"; grep -q "terminate called without an active exception" "$EV/$TAG.stderr.txt" && { abort="yes"; aborts=$((aborts+1)); }

  line="$TAG: rc=$code json=$json_ok census=$census atexit=$atexit_ok abort=$abort"
  echo "$line" | tee -a "$SUMMARY"

  if [ "$abort" = "yes" ]; then
    {
      echo "--- $TAG thread census ---"
      sed -n '/===THREAD-CENSUS-BEGIN===/,/===THREAD-CENSUS-END===/p' "$EV/$TAG.stdout.txt"
      echo "--- $TAG faulthandler (stderr tail) ---"
      tail -40 "$EV/$TAG.stderr.txt"
    } >> "$SUMMARY"
  fi
done

banner "RESULT: $aborts abort(s) in $N_RUNS runs"
cat "$SUMMARY"
