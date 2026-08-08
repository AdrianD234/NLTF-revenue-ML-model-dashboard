# R² first divergence — the exact layer where the identities part

The two published numbers per basis diverge at the FIRST input layer: the
evidence root. Nothing downstream of root selection differs.

| layer | ensemble identity | AR(1) identity | diverges? |
| --- | --- | --- | --- |
| evidence root | `data/dashboard_evidence_pack` | `data/engine_ar1/dashboard_evidence_pack` | **YES — the root cause** |
| `scorecard_predictions.parquet` sha256 | per `r2_input_hash_matrix.csv` | different file, different hash | yes (follows the root) |
| `diagnostic_tests.parquet` sha256 | per `r2_input_hash_matrix.csv` | different file, different hash | yes (follows the root) |
| finalist row selection (`scenario == finalist`, `valid_for_mape`) | 606 / 126 rows | AR(1) pack's own row counts | follows the input |
| stored paper-basis override (`diagnostic_tests.calibration_r2`) | `0.9230110422702978` | `0.9448430187011027` | follows the input |
| MZ lstsq fit (operational basis) | `0.5591936636031876` | `0.5803595524485978` | follows the input |
| row ordering, grouping keys, reductions | stable sorts (`kind="stable"`), deterministic lstsq | identical code path | **no** |
| environment (Windows 3.13 vs Linux 3.11) | identical values | identical values | **no** (line endings only) |
| repetition (sequential, xdist 2/4, load/loadscope/loadfile) | identical values | identical values | **no** |

Decision-tree outcome (Phase B, section 4): "workers receive different
inputs" — the differing input layer is the evidence-pack root, which is a
function of the engine identity of the writing process, not of worker
scheduling. The fix is input-identity isolation (per-worker output roots that
actually survive xdist, plus tests pinning each identity to its own numbers),
not serialization of the calculation — which was proven deterministic.
