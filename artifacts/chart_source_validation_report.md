# Chart Source Validation Report

Status: **passed**.

| Check | Status | Evidence |
| --- | --- | --- |
| overview_finalist_forecast_accuracy.csv exists and has required columns | PASS | rows=6; missing=[]; page_ok=True; chart_id_ok=True |
| overview_candidate_search_frontier.csv exists and has required columns | PASS | rows=287; missing=[]; page_ok=True; chart_id_ok=True |
| overview_ensemble_composition.csv exists and has required columns | PASS | rows=8; missing=[]; page_ok=True; chart_id_ok=True |
| overview_stress_horizon_checks.csv exists and has required columns | PASS | rows=18; missing=[]; page_ok=True; chart_id_ok=True |
| diagnostics_residual_autocorrelation.csv exists and has required columns | PASS | rows=36; missing=[]; page_ok=True; chart_id_ok=True |
| diagnostics_residual_vs_fitted.csv exists and has required columns | PASS | rows=2,904; missing=[]; page_ok=True; chart_id_ok=True |
| diagnostics_pass_matrix.csv exists and has required columns | PASS | rows=27; missing=[]; page_ok=True; chart_id_ok=True |
| diagnostics_error_distribution_by_horizon.csv exists and has required columns | PASS | rows=2,904; missing=[]; page_ok=True; chart_id_ok=True |
| scenario_stream_comparison.csv exists and has required columns | PASS | rows=12; missing=[]; page_ok=True; chart_id_ok=True |
| scenario_improvement_vs_benchmark.csv exists and has required columns | PASS | rows=6; missing=[]; page_ok=True; chart_id_ok=True |
| scenario_horizon_comparison.csv exists and has required columns | PASS | rows=72; missing=[]; page_ok=True; chart_id_ok=True |
| scenario_decision_summary.csv exists and has required columns | PASS | rows=9; missing=[]; page_ok=True; chart_id_ok=True |
| schiff_vs_finalist_mape.csv exists and has required columns | PASS | rows=12; missing=[]; page_ok=True; chart_id_ok=True |
| schiff_benchmark_horizon_profiles.csv exists and has required columns | PASS | rows=72; missing=[]; page_ok=True; chart_id_ok=True |
| schiff_paired_or_fullsample_gain.csv exists and has required columns | PASS | rows=6; missing=[]; page_ok=True; chart_id_ok=True |
| schiff_benchmark_summary.csv exists and has required columns | PASS | rows=21; missing=[]; page_ok=True; chart_id_ok=True |
| Ensemble source uses Parquet component weights | PASS | Expected current finalist component weights were checked. |
| Stress chart source coalesces aliases and preserves missing gaps | PASS | Six buckets per stream; Heavy RUC policy windows remain gaps. |
| Scenario summary labels full-sample gains and paired win rate | PASS | Decision-source metric labels inspected. |
| Schiff gain chart is labelled full-sample and preserves Light RUC paired weakness | PASS | Light paired gain=-1.159 pp. |
| scenario_horizon_comparison.csv includes all streams and scenarios | PASS | streams=['Heavy RUC volume', 'Light RUC volume', 'PED VKT per capita']; scenarios=['Finalist', 'Schiff'] |
| schiff_benchmark_horizon_profiles.csv includes all streams and scenarios | PASS | streams=['Heavy RUC volume', 'Light RUC volume', 'PED VKT per capita']; scenarios=['Finalist', 'Schiff'] |
| ACF source table documents residual source | PASS | rows=36 |
| Diagnostics source labels calibration R2 and Watch/Fail statuses | PASS | tests=['ADF', 'Breusch-Pagan', 'Calibration R2', 'Cointegration', 'Durbin-Watson', 'Jarque-Bera', 'KPSS', 'Overall', 'White'] |
| Residual vs fitted source uses native-unit calculation basis | PASS | rows=2,904 |
