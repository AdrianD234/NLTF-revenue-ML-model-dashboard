# Data Schema Report

Status: **passed**. Resolved Parquet path: `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone.parquet`.
Metadata path: `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone_metadata.json`
CSV mirror path: `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone.csv`
Rows: 300
Columns: 153

## Columns
- `candidate_uid`
- `stream`
- `stream_label`
- `model`
- `model_short`
- `run_source`
- `source_file`
- `source_family`
- `model_kind`
- `feature_set`
- `family_tag`
- `include_target_lags`
- `window`
- `n_quarterly_pairs`
- `n_origins`
- `quarterly_mape`
- `annual_mape`
- `quarterly_bias_pct`
- `annual_bias_pct`
- `quarterly_p90_ape`
- `annual_p90_ape`
- `quarterly_rmse`
- `mape_h01_04`
- `mape_h05_08`
- `mape_h09_12`
- `selection_score`
- `performance_distance`
- `performance_rank_within_stream`
- `performance_percentile`
- `performance_decile`
- `decile_sample_rank`
- `candidate_role`
- `include_reason`
- `is_current_recommended`
- `is_pure_schiff`
- `is_pdf_reference`
- `is_pareto_frontier`
- `is_top_quarterly`
- `is_top_annual`
- `is_top_governance`
- `is_solver`
- `is_static_solver`
- `is_prequential`
- `is_hpo`
- `is_rescue`
- `is_heavy_reconciliation`
- `plot_role`
- `plot_marker`
- `plot_size`
- `plot_alpha`
- `quarterly_mape_label`
- `annual_mape_label`
- `quarterly_bias_label`
- `model_readout`
- `curated_sample_method`
- `is_curated_cone_sample`
- `cone_x_quarterly_mape`
- `cone_y_annual_mape`
- `mape_h01`
- `mape_h02`
- `mape_h03`
- `mape_h04`
- `mape_h05`
- `mape_h06`
- `mape_h07`
- `mape_h08`
- `mape_h09`
- `mape_h10`
- `mape_h11`
- `mape_h12`
- `n_annual_pairs`
- `governance_score`
- `is_schiff_name`
- `is_residual_or_blend`
- `feature_family`
- `model_uid`
- `run_id`
- `h1_4_mape`
- `h1_4_n`
- `h5_8_mape`
- `h5_8_n`
- `h9_12_mape`
- `h9_12_n`
- `recent_2024_plus_mape`
- `recent_2024_plus_bias_pct`
- `recent_2024_plus_n`
- `policy_2022_23_mape`
- `policy_2022_23_bias_pct`
- `policy_2022_23_n`
- `abs_quarterly_bias`
- `abs_annual_bias`
- `source_family_anchor`
- `diag_n_h1`
- `diag_mape_h1`
- `diag_bias_h1_pct`
- `diag_p90_ape_h1`
- `diag_acf1_resid`
- `diag_durbin_watson`
- `diag_ljungbox_p_lag4`
- `diag_ljungbox_p_lag8`
- `diag_ljungbox_p_lag12`
- `diag_adf_p_resid`
- `diag_kpss_p_resid`
- `diag_jarque_bera_p`
- `diag_skew_resid`
- `diag_kurtosis_resid`
- `diag_shapiro_p`
- `diag_breusch_pagan_p`
- `diag_white_p`
- `diag_arch_lm_p`
- `diag_coint_p_actual_pred`
- `diag_mz_intercept`
- `diag_mz_slope`
- `diag_mz_r2`
- `diag_mz_f_p`
- `diag_pass_no_autocorr_lb8`
- `diag_pass_dw_range`
- `diag_pass_adf_stationary`
- `diag_pass_kpss_stationary`
- `diag_pass_no_hetero_bp`
- `diag_pass_no_arch`
- `diag_pass_coint`
- `diag_pass_normal_jb`
- `diagnostic_role`
- `diagnostic_available`
- `stress_h1_4_mape`
- `stress_h5_8_mape`
- `stress_h9_12_mape`
- `stress_2024plus_mape`
- `stress_2022_23_mape`
- `stress_annual_mape`
- `stress_1_4_qtrs_mape`
- `stress_5_8_qtrs_mape`
- `stress_9_12_qtrs_mape`
- `paired_common_pairs`
- `paired_schiff_mape`
- `paired_model_mape`
- `paired_improvement_pp`
- `paired_win_rate_pct`
- `ensemble_component_count`
- `ensemble_max_weight`
- `ensemble_top_component`
- `ensemble_top_component_short`
- `ensemble_weight_entropy`
- `ensemble_components_json`
- `annual_mape_filled`
- `abs_quarterly_bias_pct`
- `is_primary_schiff_benchmark`
- `is_extreme_outlier`
- `plot_default_include`
- `plot_q_cap`
- `plot_a_cap`
- `params_json`

## Row Counts By Stream
- Heavy RUC volume: 100
- Light RUC volume: 100
- PED VKT per capita: 100

## Flagged Rows
- Current Recommended: 3
- Pure Schiff: 5
- Pdf Reference: 14
- Frontier: 2
- Distribution Sample: 300
- Plot Default Include: 287

## Current Recommended Rows
| stream | stream_label | model | quarterly_mape | annual_mape |
| --- | --- | --- | --- | --- |
| HEAVY_RUC | Heavy RUC volume | HEAVY_RUC__RECON_STATIC_REBUILT | 3.484367565681976 | 3.0199801790589795 |
| LIGHT_RUC | Light RUC volume | LIGHT_RUC__RESCUE_static_bias_penalty_top25_cap0p4 | 9.14754535409187 | 5.999498868354415 |
| PED | PED VKT per capita | PED__RESCUE_static_annual_weighted_top12_capnone | 2.4732445831169696 | 2.3856249442030424 |

## Pure Schiff Rows
| stream | stream_label | model | quarterly_mape | annual_mape |
| --- | --- | --- | --- | --- |
| HEAVY_RUC | Heavy RUC volume | HEAVY_RUC__schiff_no_lead__SCHIFF_OLS__noylag__w40 | 11.48264346093783 | 11.717803544852805 |
| LIGHT_RUC | Light RUC volume | LIGHT_RUC__schiff_no_lead__SCHIFF_OLS__noylag__w40 | 11.546786315968834 | 7.843683247318401 |
| LIGHT_RUC | Light RUC volume | LIGHT_RUC__schiff__SCHIFF_OLS__noylag__w40 | 11.546786315968834 | 7.843683247318401 |
| PED | PED VKT per capita | PED__schiff__SCHIFF_OLS__noylag__w64 | 3.082117232079539 | 2.965757956236625 |
| PED | PED VKT per capita | PED__schiff__SCHIFF_OLS__noylag__w52 | 3.085874064655451 | 3.063420439565097 |

## Diagnostic And Support Files Found
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\chart_sources\diagnostics_error_distribution_by_horizon.csv` (1,612,468 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\chart_sources\diagnostics_pass_matrix.csv` (13,767 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\chart_sources\diagnostics_residual_autocorrelation.csv` (18,763 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\chart_sources\diagnostics_residual_vs_fitted.csv` (1,614,607 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\chart_sources\schiff_benchmark_horizon_profiles.csv` (31,360 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\chart_sources\schiff_benchmark_summary.csv` (11,486 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\chart_sources\schiff_paired_or_fullsample_gain.csv` (3,717 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\chart_sources\schiff_vs_finalist_mape.csv` (6,408 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\curated_data\annual_predictions_selected.csv` (100,520 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\curated_data\paired_vs_schiff_selected.csv` (682 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\curated_data\quarterly_predictions_selected.csv` (632,860 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\curated_data\schiff_benchmark.csv` (700 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\diagnostic_acf_source_table.csv` (6,707 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\final-01-executive-summary.png` (172,800 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\final-01-overview.png` (172,800 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\final-02-diagnostics.png` (176,338 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\final-03-scenario-comparison.png` (156,544 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\final-03-schiff-comparison.png` (150,139 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\final-04-schiff-benchmark.png` (150,139 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\final-diagnostics.png` (186,487 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\final-overview.png` (187,754 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\final-scenario-comparison.png` (163,922 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\final-schiff-benchmark.png` (154,877 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\hover-candidate-landscape.png` (193,521 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\hover-ensemble-composition.png` (181,856 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\hover-finalist-accuracy.png` (190,892 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\hover-stress-checks.png` (178,295 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\mcp-01-executive-summary.png` (172,800 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\mcp-01-overview.png` (172,800 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\mcp-02-diagnostics.png` (176,338 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\mcp-03-scenario-comparison.png` (156,544 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\mcp-03-schiff-comparison.png` (150,139 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\mcp-04-schiff-benchmark.png` (150,139 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\artifacts\screenshots\visual-smoke-scenario-dumbbell.png` (115,472 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\assets\nz-transport-agency-waka-kotahi.png` (62,451 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone_pack\stage1_candidate_optimisation_cone.png` (242,431 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone_pack\stage1_curated_diagnostic_columns.csv` (67,334 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone_pack\stage1_recommended_finalist_mape.png` (70,919 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\figures\fig01_quarterly_mape_our_vs_schiff.png` (64,174 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\figures\fig02_annual_mape_our_vs_schiff.png` (62,031 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\figures\fig03_paired_improvement_vs_schiff.png` (57,251 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\figures\fig04_h1_actual_vs_predicted.png` (528,826 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\figures\fig05_h1_percent_error_over_time.png` (443,696 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\figures\fig06_residual_acf_h1.png` (104,492 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\figures\fig07_h1_error_distribution.png` (139,526 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\figures\fig08_residual_diagnostic_pass_matrix.png` (151,079 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\figures\fig09_annual_actual_vs_predicted.png` (283,821 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\figures\fig10_summary_table.png` (108,696 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\model_diagnostic_audit_report.md` (6,735 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\model_diagnostic_audit_tables.xlsx` (10,941 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\tables\diagnostic_pass_matrix.csv` (601 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\tables\h1_residual_diagnostics_our_vs_schiff.csv` (3,752 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\tables\model_summary_our_vs_schiff.csv` (1,377 bytes)
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack\tables\paired_common_forecast_pairs_our_vs_schiff.csv` (418 bytes)