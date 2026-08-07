#!/usr/bin/env bash
# Phase 2 acceptance: prove the local clean room can replace GitHub as the
# ordinary validation loop.
#
# Runs the tiers sequentially - never concurrently, never with xdist - and
# records what each one actually did, so the full tier can be compared against
# the hosted clean-clone contract on all six required dimensions.
#
# Usage: bash ci/phase2_docker_parity.sh [step]
#        step: build | fast | affected | profile | full | all

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

EV="$REPO_ROOT/artifacts/ci_optimisation/phase2"
mkdir -p "$EV"

STEP="${1:-all}"

banner() { printf '\n\n############ %s ############\n' "$*"; }

# Refuse to start while any pytest is alive. A contended run is not a benchmark,
# and this is the exact mistake that invalidated an earlier measurement.
guard_no_pytest() {
  local running
  running="$(pgrep -fc 'pytest' 2>/dev/null || echo 0)"
  if [ "${running:-0}" -gt 0 ]; then
    echo "REFUSING: $running pytest process(es) already running." >&2
    exit 2
  fi
}

record() {
  local name="$1" exit_code="$2" elapsed="$3" log="$4"
  {
    echo "step=$name"
    echo "exit_code=$exit_code"
    echo "elapsed_seconds=$elapsed"
    echo "elapsed_hms=$((elapsed / 60))m$((elapsed % 60))s"
    echo "summary=$(grep -oE '[0-9]+ (passed|failed)[^=]*' "$log" 2>/dev/null | tail -1)"
    echo "failed_lines=$(grep -cE '^FAILED' "$log" 2>/dev/null || echo 0)"
    echo "gate=$(grep -c 'Governed tree unchanged' "$log" 2>/dev/null || echo 0)"
    echo "gate_tripped=$(grep -c 'GOVERNED TREE MUTATED' "$log" 2>/dev/null || echo 0)"
  } > "$EV/${name}_result.txt"
  echo "--- $name ---"
  cat "$EV/${name}_result.txt"
}

run_tier() {
  local name="$1"; shift
  guard_no_pytest
  banner "$name"
  local start elapsed code
  start=$(date +%s)
  bash scripts/ci_local.sh "$@" > "$EV/${name}.log" 2>&1
  code=$?
  elapsed=$(( $(date +%s) - start ))
  tail -25 "$EV/${name}.log"
  record "$name" "$code" "$elapsed" "$EV/${name}.log"
  return "$code"
}

case "$STEP" in
  build|all)
    banner "image build"
    start=$(date +%s)
    DOCKER_BUILDKIT=1 docker build -f ci/Dockerfile -t nltf-ci:local . \
      > "$EV/build.log" 2>&1
    code=$?
    echo "build exit=$code elapsed=$(( $(date +%s) - start ))s"
    docker run --rm --entrypoint cat nltf-ci:local /image_environment.json \
      > "$EV/image_environment.json"
    [ "$STEP" = "build" ] && exit "$code"
    ;;&

  fast|all)
    run_tier fast --tier fast
    [ "$STEP" = "fast" ] && exit $?
    ;;&

  affected|all)
    # Four representative scopes. Each is planned from a real base..head range,
    # so the selection is the planner's, not a hand-picked list.
    run_tier affected_default --tier affected --base origin/main
    [ "$STEP" = "affected" ] && exit $?
    ;;&

  profile|all)
    run_tier profile --tier profile
    [ "$STEP" = "profile" ] && exit $?
    ;;&

  full|all)
    run_tier full --tier full
    full_code=$?
    banner "pack status after the full tier"
    docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
      -v "$REPO_ROOT:/work" -w /work --entrypoint python nltf-ci:local \
      scripts/plan_governed_pack_rebuilds.py --format json \
      > "$EV/pack_status_after_full.json" 2>"$EV/pack_status_after_full.err"
    tail -3 "$EV/pack_status_after_full.err" 2>/dev/null || true
    exit "$full_code"
    ;;
esac
