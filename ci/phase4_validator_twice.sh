#!/usr/bin/env bash
# Phase 4 proof: the complete bundle validator, twice, in the publish
# environment, on the fixed source.
#
# Why twice matters here specifically: before the fix each validation ran two
# probes (bundle, then source) with a ~50% teardown abort each, so a full
# validation passed only ~25% of the time and TWO consecutive passes had ~6%
# probability. Two clean validations on the fixed source are therefore ~94%
# detection power against "the fix changed nothing", on top of the
# deterministic census tests.
#
# Also required and checked: the checkout is not mutated (the validator probes
# disposable copies by design), and the manifest re-verification step inside
# the validator passes both times.
#
# Usage: bash ci/phase4_validator_twice.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EV="$REPO_ROOT/artifacts/ci_optimisation/probe_matrix/phase4"
mkdir -p "$EV"

SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
CLONE="/tmp/nltf-phase4-$$"

cleanup() { local s=$?; rm -rf "$CLONE"; exit "$s"; }
trap cleanup EXIT

banner() { printf '\n\n############ %s ############\n' "$*"; }

banner "disposable clone at ${SHA:0:12}"
git clone --quiet --local "$REPO_ROOT" "$CLONE"
git -C "$CLONE" checkout --quiet --detach "$SHA"
[ -z "$(git -C "$CLONE" status --porcelain)" ] || { echo "clone dirty"; exit 2; }

run_env() {
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$CLONE:/work" -w /work --entrypoint python nltf-publish-probe:local "$@"
}

banner "building the bundle"
run_env scripts/build_databricks_app_bundle.py \
  --source . --output build/databricks_app/app --clean \
  > "$EV/build.log" 2>&1 || { tail -5 "$EV/build.log"; exit 2; }

for PASS in 1 2; do
  banner "full validation, pass $PASS"
  start=$(date +%s)
  run_env scripts/validate_databricks_app_bundle.py \
    --bundle build/databricks_app/app --source . \
    > "$EV/validate_pass$PASS.log" 2>&1
  code=$?
  elapsed=$(( $(date +%s) - start ))
  abort="no"
  grep -q "terminate called without an active exception" "$EV/validate_pass$PASS.log" && abort="yes"
  echo "pass $PASS: exit=$code elapsed=${elapsed}s abort=$abort"
  tail -3 "$EV/validate_pass$PASS.log"
  [ "$code" -eq 0 ] || { echo "VALIDATION FAILED on pass $PASS"; exit 1; }
done

banner "checkout non-mutation"
mutated="$(git -C "$CLONE" status --porcelain)"
if [ -n "$mutated" ]; then
  echo "the validator mutated the checkout:"; echo "$mutated"; exit 1
fi
echo "clone byte-identical to ${SHA:0:12} after two full validations"

banner "RESULT: both validations green, checkout unmutated"
