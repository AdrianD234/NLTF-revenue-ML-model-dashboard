# IMPROVEMENT_TARGETS.lock.md

After basic verification passes, the agent must complete at least 5 post-pass improvement loops.

## Improvement dimensions

Each loop must improve one or more of:

- executive clarity;
- chart quality;
- chart usefulness;
- filter usefulness;
- model-governance explanation;
- run-audit robustness;
- missing-data handling;
- Schiff comparison clarity;
- ensemble composition clarity;
- forecast-error exploration;
- stress-window explanation.

## Minimum quality thresholds

Each page must score at least 8/10 on:

- analytical usefulness;
- visual clarity;
- real-data depth;
- executive readability;
- interactivity;
- robustness;
- alignment to source report.

## Completion rule

If any page scores below 8/10, continue improving.

If fewer than 5 post-pass improvement loops are complete, continue improving.

If blocked, write `artifacts/blocker_report.md` and `.agent_state.md`. Do not claim completion.
