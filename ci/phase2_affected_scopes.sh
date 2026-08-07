#!/usr/bin/env bash
# Phase 2 step 3: prove the affected tier routes four representative scopes.
#
# Each scope gets a throwaway branch carrying a comment-only change to a
# representative file, so the planner runs on a real diff rather than a
# hand-supplied file list. The branches are local to this clone and are deleted
# afterwards; nothing is pushed and no governed value moves.
#
# Two of the four scopes - data_refresh and model_promotion - are DESIGNED to
# demand full assurance. For those, the proof required here is that the tier
# escalates rather than quietly running a reduced selection. Actually executing
# the escalated suite for each would run the identical ~40-minute full tier
# three times over; step 5 runs it once, which is the same work.
#
# Usage: bash ci/phase2_affected_scopes.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

EV="$REPO_ROOT/artifacts/ci_optimisation/phase2"
mkdir -p "$EV"

BASE_SHA="$(git rev-parse HEAD)"

# scope name | file to touch | comment syntax
SCOPES=(
  "dashboard_ui|model_dashboard/ui.py|#"
  "revenue_outlook_calculation|model_dashboard/rate_paths.py|#"
  "data_refresh|data/model_input_history/manifest.md|<!--"
  "model_promotion|pipeline/vnext_candidates.py|#"
)

summary="$EV/affected_scopes_summary.txt"
: > "$summary"

for entry in "${SCOPES[@]}"; do
  IFS='|' read -r scope target comment <<< "$entry"

  printf '\n\n############ affected: %s ############\n' "$scope"

  if [ ! -f "$target" ]; then
    echo "SKIP: $target does not exist" | tee -a "$summary"
    continue
  fi

  branch="phase2/scope-$scope"
  git checkout --quiet -B "$branch" "$BASE_SHA"
  if [ "$comment" = "<!--" ]; then
    printf '\n<!-- phase2 scope probe: %s -->\n' "$scope" >> "$target"
  else
    printf '\n# phase2 scope probe: %%s\n' >> /dev/null
    printf '\n# phase2 scope probe: %s\n' "$scope" >> "$target"
  fi
  git add "$target"
  git -c user.email=ci@local -c user.name=phase2 commit --quiet \
    -m "phase2 probe: $scope"
  probe_sha="$(git rev-parse HEAD)"

  # What does the planner say?
  python3 scripts/ci_plan.py --base "$BASE_SHA" --head "$probe_sha" --format json \
    > "$EV/plan_$scope.json" 2>/dev/null \
    || docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
         -v "$REPO_ROOT:/work" -w /work --entrypoint python nltf-ci:local \
         scripts/ci_plan.py --base "$BASE_SHA" --head "$probe_sha" --format json \
         > "$EV/plan_$scope.json"

  scopes_found="$(grep -o '"scopes":[^]]*]' "$EV/plan_$scope.json" | head -1)"
  full="$(grep -o '"requires_full_assurance": [a-z]*' "$EV/plan_$scope.json" | head -1)"
  npaths="$(grep -o '"required_test_paths": \[[^]]*\]' "$EV/plan_$scope.json" \
            | grep -o 'tests/' | wc -l)"

  echo "scope=$scope target=$target" | tee -a "$summary"
  echo "  $scopes_found" | tee -a "$summary"
  echo "  $full  selected_test_files=$npaths" | tee -a "$summary"

  if echo "$full" | grep -q true; then
    echo "  -> tier escalates to FULL (by design for this scope)" | tee -a "$summary"
    echo "     not executed here; step 5 runs the identical full tier once" | tee -a "$summary"
  else
    start=$(date +%s)
    bash scripts/ci_local.sh --tier affected --base "$BASE_SHA" --ref "$probe_sha" \
      > "$EV/affected_$scope.log" 2>&1
    code=$?
    elapsed=$(( $(date +%s) - start ))
    tail -12 "$EV/affected_$scope.log"
    echo "  -> affected tier exit=$code elapsed=$((elapsed/60))m$((elapsed%60))s" \
      | tee -a "$summary"
    echo "     gate_tripped=$(grep -c 'GOVERNED TREE MUTATED' "$EV/affected_$scope.log")" \
      | tee -a "$summary"
    echo "     $(grep -oE '[0-9]+ passed[^=]*' "$EV/affected_$scope.log" | tail -1)" \
      | tee -a "$summary"
  fi

  git checkout --quiet --detach "$BASE_SHA"
  git branch -D "$branch" >/dev/null 2>&1 || true
done

printf '\n\n############ SUMMARY ############\n'
cat "$summary"
