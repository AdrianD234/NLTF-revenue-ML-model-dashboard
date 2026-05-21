from __future__ import annotations


FILE_ALIASES = {
    "recommended": ["recommended_finalists.csv"],
    "summary": ["final_summary.csv", "all_model_summary.csv", "top100_candidates.csv", "top50_by_stream.csv"],
    "quarterly_predictions": ["quarterly_predictions.csv", "all_quarterly_predictions.csv"],
    "annual_predictions": ["annual_predictions.csv", "all_annual_predictions.csv"],
    "quarterly_summary": ["quarterly_summary.csv"],
    "annual_summary": ["annual_summary.csv"],
    "paired_vs_schiff": ["paired_vs_schiff.csv", "paired_finalist_vs_schiff.csv"],
    "stress": ["stress_tests.csv", "finalist_stress_tests.csv"],
    "weights": ["ensemble_weights.csv"],
    "features": ["feature_audit_log_real_only.csv", "detected_core_feature_columns.csv", "feature_audit.csv"],
    "variant_features": ["variant_feature_counts.csv"],
    "leaderboards": ["leaderboards.csv"],
    "errors": ["errors.csv"],
    "autogluon_workbook": ["autogluon_final_robust_all_streams_results.xlsx"],
    "autogluon_report": ["autogluon_final_robust_report.md"],
    "bespoke_workbook": ["stage1_bespoke_solver_results.xlsx"],
    "bespoke_report": ["stage1_bespoke_solver_report.md"],
}

WORKBOOK_DATASETS = {
    "recommended",
    "summary",
    "quarterly_predictions",
    "annual_predictions",
    "quarterly_summary",
    "annual_summary",
    "paired_vs_schiff",
    "stress",
    "weights",
    "features",
    "variant_features",
    "leaderboards",
    "errors",
}

WORKBOOK_ALIASES = [
    "autogluon_final_robust_all_streams_results.xlsx",
    "stage1_bespoke_solver_results.xlsx",
]

SHEET_HINTS = {
    "recommended": ["recommended_finalists", "recommended", "finalists"],
    "summary": ["final_summary", "all_model_summary", "model_summary", "summary", "candidates"],
    "quarterly_predictions": ["quarterly_predictions", "all_quarterly_predictions", "quarterly_forecasts"],
    "annual_predictions": ["annual_predictions", "all_annual_predictions", "annual_forecasts"],
    "quarterly_summary": ["quarterly_summary"],
    "annual_summary": ["annual_summary"],
    "paired_vs_schiff": ["paired_vs_schiff", "paired_finalist_vs_schiff", "schiff_comparison"],
    "stress": ["stress_tests", "finalist_stress_tests", "stress"],
    "weights": ["ensemble_weights", "weights"],
    "features": ["feature_audit_log_real_only", "feature_audit", "detected_core_feature_columns"],
    "variant_features": ["variant_feature_counts"],
    "leaderboards": ["leaderboards", "leaderboard"],
    "errors": ["errors", "error_log"],
}

PREDICTION_COLUMN_ALIASES = {
    "actual": ["actual", "target", "actual_annual", "actual_value", "y_true"],
    "pred": ["pred", "prediction", "pred_annual", "forecast", "y_pred"],
    "origin": ["origin", "forecast_origin", "train_origin"],
    "target_period": ["target_period", "quarter", "period", "forecast_period"],
    "horizon": ["horizon", "forecast_horizon", "h"],
    "june_year": ["june_year", "year", "annual_year"],
}

SUMMARY_COLUMNS = [
    "stage",
    "stream",
    "variant",
    "source_family",
    "model",
    "quarterly_mape",
    "annual_mape",
    "quarterly_bias_pct",
    "annual_bias_pct",
    "quarterly_p90_ape",
    "annual_p90_ape",
    "governance_score",
    "n_quarterly_pairs",
    "n_annual_pairs",
]

INVENTORY_COLUMNS = [
    "stage",
    "stream_label",
    "variant",
    "source_family",
    "model",
    "quarterly_mape",
    "annual_mape",
    "quarterly_bias_pct",
    "annual_bias_pct",
    "quarterly_p90_ape",
    "governance_score",
    "n_quarterly_pairs",
    "n_annual_pairs",
]

