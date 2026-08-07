#!/usr/bin/env bash
# Phase D step 4, second half: after rebuilding the affected packs in governed
# order, the calculation lane passes.
#
# The first half is already proven - an unrebuilt digest-bound change to
# model_dashboard/rate_paths.py fails the lane in 8 seconds with one concise
# stale-pack diagnostic (exit 4) rather than 185 derived fixture errors.
#
# This proves the other half, which is the one that matters for a developer:
# having been told what to rebuild, doing it makes the lane green.
#
# Everything happens in a DISPOSABLE clone. The synthetic probe commit and the
# packs rebuilt on top of it are discarded at the end - they must never reach
# the real branch, because they were built from a probe, not from a decision.
#
# Usage: bash ci/phase_d_calc_lane_rebuild.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EV="$REPO_ROOT/artifacts/ci_optimisation/phase2"
mkdir -p "$EV"

BASE_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
PROBE="/tmp/nltf-calcprobe-$$"
TARGET="model_dashboard/rate_paths.py"

# Preserve the script's real exit status through cleanup. A proof that reports
# success while having failed internally is worse than no proof: the first run
# of this script printed "CALC PROOF exit=0" immediately after "the planner
# produced no rebuild commands".
cleanup() {
  local status=$?
  rm -rf "$PROBE"
  exit "$status"
}
trap cleanup EXIT

section() { printf '\n\n############ %s ############\n' "$*"; }

section "Building a disposable probe clone at $BASE_SHA"
git clone --quiet --local "$REPO_ROOT" "$PROBE" || { echo "clone failed"; exit 2; }
git -C "$PROBE" checkout --quiet --detach "$BASE_SHA"
git -C "$PROBE" remote set-url origin "$REPO_ROOT"
git -C "$PROBE" fetch --quiet origin '+refs/heads/*:refs/remotes/origin/*' 2>/dev/null || true

# Match the file's line-ending convention: .gitattributes pins `* -text`, so
# appending the wrong one corrupts the file and a repository test rejects it.
if grep -qU $'\r' "$PROBE/$TARGET" 2>/dev/null; then eol=$'\r\n'; else eol=$'\n'; fi
printf '%s# phase D calculation-lane probe%s' "$eol" "$eol" >> "$PROBE/$TARGET"
git -C "$PROBE" add "$TARGET"
git -C "$PROBE" -c user.email=ci@local -c user.name=phaseD \
  commit --quiet -m "probe: digest-bound calculation change"
PROBE_SHA="$(git -C "$PROBE" rev-parse HEAD)"
echo "probe commit: ${PROBE_SHA:0:12}"

run_in_probe() {
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$PROBE:/work" -w /work --entrypoint python nltf-ci:local "$@"
}

section "BEFORE rebuild — pack status must report policy_runtime stale"
run_in_probe scripts/plan_governed_pack_rebuilds.py --format human \
  2>&1 | tee "$EV/calc_lane_before_rebuild.log" | sed -n '1,12p'

stale_count=$(grep -c 'REBUILD' "$EV/calc_lane_before_rebuild.log" || echo 0)
echo "packs flagged for rebuild: $stale_count"
if [ "$stale_count" -eq 0 ]; then
  echo "UNEXPECTED: a digest-bound change did not mark any pack stale." >&2
  exit 1
fi

section "Rebuilding the affected packs in the governed order"
# Take the commands FROM the planner, in the order it gives them. An earlier
# version hardcoded a policy_runtime rebuild and failed, because a change to
# model_dashboard/rate_paths.py invalidates the replay cache first:
#
#   ReplayCacheStale: Compiled Revenue Outlook replay cache for engine 'ar1'
#   is stale (replay inputs changed since the cache was built)
#
# Hardcoding the rebuild would have proved only that I could guess; reading the
# planner's own ordering is the thing worth proving.
# Write the plan to a file inside the probe and read it back in ONE container
# call. Piping one `docker run` into another needs -i on the consumer, and
# without it the second container gets no stdin at all:
#
#   json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
#
# A file avoids the whole class of problem.
run_in_probe scripts/plan_governed_pack_rebuilds.py --format json \
  > "$PROBE/plan.json" 2>/dev/null

mapfile -t REBUILD_CMDS < <(
  run_in_probe -c 'import json
plan = json.load(open("/work/plan.json"))
for name in plan["required_rebuilds"]:
    if name == "databricks_bundle":
        continue  # published from main by its own workflow, not part of this lane
    print(plan["packs"][name]["rebuild_command"])'
)

if [ "${#REBUILD_CMDS[@]}" -eq 0 ]; then
  echo "the planner produced no rebuild commands" >&2
  exit 1
fi

printf 'planner ordering (%d step(s)):\n' "${#REBUILD_CMDS[@]}"
printf '  %s\n' "${REBUILD_CMDS[@]}"

: > "$EV/calc_lane_rebuild.log"
for cmd in "${REBUILD_CMDS[@]}"; do
  printf '\n--- %s ---\n' "$cmd" | tee -a "$EV/calc_lane_rebuild.log"
  # shellcheck disable=SC2086
  run_in_probe ${cmd#python } >> "$EV/calc_lane_rebuild.log" 2>&1
  step_code=$?
  echo "exit=$step_code" | tee -a "$EV/calc_lane_rebuild.log"
  if [ "$step_code" -ne 0 ]; then
    tail -12 "$EV/calc_lane_rebuild.log"
    echo "rebuild step failed: $cmd" >&2
    exit "$step_code"
  fi
done
rebuild_code=0
echo "all rebuild steps completed"

section "AFTER rebuild — every pack must report current"
run_in_probe scripts/plan_governed_pack_rebuilds.py --format human --fail-on-stale \
  2>&1 | tee "$EV/calc_lane_after_rebuild.log" | sed -n '1,10p'
after_code="${PIPESTATUS[0]}"
echo "pack gate exit=$after_code"
[ "$after_code" -eq 0 ] || { echo "packs still stale after the governed rebuild" >&2; exit 1; }

section "Committing the rebuilt packs in the probe clone only"
# ALL the rebuilt packs, not just the last one. An earlier version staged only
# data/revenue_outlook_policy_runtime, so the fresh clone taken at the rebuilt
# SHA did not receive the rebuilt replay cache - and the lane then reported
# ReplayCacheStale 332 times, immediately after the pack status check had said
# every pack was ok. The status check was reading the probe directory; the lane
# was reading a clone of the commit.
git -C "$PROBE" add \
  data/revenue_outlook_replay_cache \
  data/revenue_outlook_quarterly_display \
  data/revenue_outlook_uncertainty \
  data/revenue_outlook_policy_runtime

staged="$(git -C "$PROBE" diff --cached --name-only | wc -l)"
echo "staged $staged rebuilt pack file(s)"
[ "$staged" -gt 0 ] || { echo "nothing staged; the rebuild produced no change" >&2; exit 1; }

git -C "$PROBE" -c user.email=ci@local -c user.name=phaseD \
  commit --quiet -m "probe: rebuild affected packs in governed order"
REBUILT_SHA="$(git -C "$PROBE" rev-parse HEAD)"
echo "rebuilt commit: ${REBUILT_SHA:0:12}"

# The commit must leave nothing behind, or the clone taken from it is not the
# tree we just proved current.
residual="$(git -C "$PROBE" status --porcelain -- data/)"
if [ -n "$residual" ]; then
  echo "FATAL: rebuilt pack content remains uncommitted:" >&2
  echo "$residual" >&2
  exit 1
fi
echo "no rebuilt pack content left uncommitted"

section "Running the affected lane against the rebuilt probe"
start=$(date +%s)
( cd "$PROBE" && bash scripts/ci_local.sh --tier affected \
    --base "$BASE_SHA" --ref "$REBUILT_SHA" ) \
  > "$EV/calc_lane_after_rebuild_run.log" 2>&1
lane_code=$?
elapsed=$(( $(date +%s) - start ))

tail -20 "$EV/calc_lane_after_rebuild_run.log"

{
  echo "base_sha=$BASE_SHA"
  echo "probe_sha=$PROBE_SHA"
  echo "rebuilt_sha=$REBUILT_SHA"
  echo "lane_exit_code=$lane_code"
  echo "elapsed_seconds=$elapsed"
  echo "summary=$(grep -oE '[0-9]+ (passed|failed)[^=]*' "$EV/calc_lane_after_rebuild_run.log" | tail -1)"
  echo "gate_tripped=$(grep -c 'GOVERNED TREE MUTATED' "$EV/calc_lane_after_rebuild_run.log")"
} > "$EV/calc_lane_rebuild_result.txt"

printf '\n\n############ RESULT ############\n'
cat "$EV/calc_lane_rebuild_result.txt"

if [ "$lane_code" -eq 0 ]; then
  echo
  echo "PROVEN: the calculation lane fails fast on an unrebuilt digest-bound"
  echo "change, and passes once the affected packs are rebuilt in governed order."
else
  echo
  echo "The lane did not pass after the governed rebuild (exit $lane_code)." >&2
fi

echo
echo "Discarding the probe clone and its rebuilt packs."
exit "$lane_code"
