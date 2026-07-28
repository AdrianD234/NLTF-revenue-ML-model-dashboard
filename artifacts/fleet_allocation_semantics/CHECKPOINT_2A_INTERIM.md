# Checkpoint 2A interim: the class-share evidence contradicts my earlier claim

## What I claimed, and why it now looks wrong

I stated that treating a conventional-only forecast as the total pool would
"mechanically cut conventional Light RUC by about 27%". The class-share
evidence does not support that.

| FY | Current conv share | MBU26 conv share |
|---|---:|---:|
| 2026 | 0.872 | 0.875 |
| 2027 | 0.838 | 0.841 |
| 2028 | 0.810 | 0.812 |
| 2029 | 0.778 | 0.781 |
| 2030 | **0.746** | **0.751** |

The conventional shares track MBU26 to within half a percentage point. If the
pipeline were taking a conventional-only forecast and multiplying it by the
conventional share, current conventional would sit ~25% below its own model
output while shares stayed normal. Shares alone cannot distinguish that, but
they rule out the *share* being wrong.

The difference is in the **pool level**, not the split:

| FY2030 | Current | MBU26 | Gap |
|---|---:|---:|---:|
| conventional | 12,519.5 | 14,402.4 | −13.1% |
| pool | 16,782.2 | 19,165.5 | −12.4% |

## The FY2025 anchor

At the actual anchor the pack does the right thing:

```
Light RUC model target (conventional-only)  12,273.984
pack light_ruc_net_km                       12,273.984   exact match
pack class sum                              13,529.743
```

Conventional carries the model value exactly; the pool is larger. That is the
correct treatment, not the mismatch I asserted.

## What is still undetermined

FY2025 is an actual year, so the match may reflect the actual rather than a
model-driven allocation rule. The decisive test is whether, in the **forecast**
years, `pack conventional == raw model output` (correct anchoring) or
`pack pool == raw model output` (the mismatch).

I could not run it: `_light_ruc_feature_frame` raised
`InvalidIndexError: Reindexing only valid with uniquely valued Index objects`
when passed the scenario-input future rows, so I have no raw FY2026-FY2030
model forecast to compare against.

Until that runs, the Light RUC verdict is **insufficient evidence**, not
"confirmed semantic mismatch". The Phase 2 target classification stands -
the target is conventional-only, exactly - but what the runtime then does with
it is not yet established.

## Correction

My previous statement that the overlay "manufactures BEV and PHEV kilometres
from a series that never contained them" was both too strong and, on this
evidence, probably wrong about the mechanism. Inferring other classes from a
conventional anchor via independently sourced shares is legitimate, and the
shares here match MBU26 closely.
