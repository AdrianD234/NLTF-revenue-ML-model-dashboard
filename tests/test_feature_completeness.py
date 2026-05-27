from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from app import (
    LOADER_SCHEMA_VERSION,
    best_weighted_finalist_models,
    central_error_window,
    ensemble_fallback_scores,
    ensemble_composition_insight,
    ensemble_method_readout,
    enterprise_decision_brief,
    error_flags,
    global_warnings,
    hide_candidate_outliers,
    inventory_summary,
    data_quality_warning_readout,
    diagnostics_provenance_note,
    management_summary_markdown,
    model_detail_summary,
    overview_error_distribution_note,
    overview_kpi_cards,
    overview_frontier_note,
    overview_stress_watch_note,
    overview_stress_frame,
    recommended_models_with_weights,
    run_evidence_caption,
    run_health_summary,
    schema_diagnostics,
    scenario_kpi_cards,
    scenario_best_paired_by_stream,
    scenario_decision_lens_summary,
    scenario_decision_rule_text,
    scenario_drilldown_note,
    scenario_paired_display_rows,
    schiff_compact_summary,
    schiff_kpi_cards,
)
from model_dashboard.data_loader import LoadedRun, load_parquet_dashboard
from model_dashboard.data.diagnostics import build_diagnostic_acf_source_table
from model_dashboard.labels import model_alias, schiff_class
from model_dashboard.metrics import (
    best_by_stream,
    filter_by_common_controls,
    final_stress_frame,
    forecast_error_readout,
    governance_story_summary,
    inventory_rank_options,
    manager_conclusion,
    classify_error_rows,
    percent_unit_warnings,
    stress_readout,
)
from model_dashboard.plots import (
    plot_autocorrelation_diagnostics,
    plot_candidate_landscape,
    plot_ensemble_composition,
    plot_error_distribution,
    plot_error_types,
    plot_finalist_accuracy,
    plot_horizon_mape,
    plot_inventory_family_performance,
    plot_paired_improvement,
    plot_percent_error_over_time,
    plot_residual_vs_fitted,
    plot_schiff_benchmark,
    plot_schiff_class_mix,
    plot_stress_checks,
)


@pytest.fixture(scope="session")
def loaded_validation_run() -> LoadedRun:
    configured = os.environ.get("MODEL_DIAGNOSTIC_DATA_ROOT") or os.environ.get("STAGE1_DASHBOARD_DATA_ROOT")
    if not configured:
        pytest.skip("Full feature-completeness tests require MODEL_DIAGNOSTIC_DATA_ROOT or STAGE1_DASHBOARD_DATA_ROOT.")
    data_root = Path(configured).expanduser()
    if data_root.name == "mini_parquet":
        pytest.skip("Full feature-completeness tests require the external dashboard data pack, not the mini fixture.")
    if not data_root.exists():
        pytest.skip(f"Configured dashboard data root does not exist: {data_root}")
    return load_parquet_dashboard(data_root, Path(__file__).resolve().parents[1])


def selected_predictions_missing(loaded: LoadedRun) -> bool:
    qpred = loaded.data["quarterly_predictions"]
    status = loaded.file_status
    rows = status[status["Dataset"].astype(str).eq("Quarterly Predictions Selected")]
    return qpred.empty and not rows.empty and rows["Found?"].iloc[0] == "No"


def test_validation_run_has_real_data_for_all_core_pages(loaded_validation_run: LoadedRun) -> None:
    data = loaded_validation_run.data
    expected_streams = {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}

    assert len(data["recommended"]) >= 3
    assert len(data["summary"]) >= 100
    if data["quarterly_predictions"].empty:
        quarterly_status = loaded_validation_run.file_status[
            loaded_validation_run.file_status["Dataset"].astype(str).eq("Quarterly Predictions Selected")
        ]
        assert not quarterly_status.empty
        assert quarterly_status["Found?"].iloc[0] == "No"
    else:
        assert len(data["quarterly_predictions"]) >= 1_000
        assert expected_streams.issubset(set(data["quarterly_predictions"]["stream_label"]))

    if data["annual_predictions"].empty:
        annual_status = loaded_validation_run.file_status[
            loaded_validation_run.file_status["Dataset"].astype(str).eq("Annual Predictions Selected")
        ]
        assert not annual_status.empty
        assert annual_status["Found?"].iloc[0] == "No"
    else:
        assert len(data["annual_predictions"]) >= 100
    assert len(data["paired_vs_schiff"]) > 0
    assert len(data["stress"]) > 0
    assert len(data["weights"]) > 0
    assert "variant_features" in data
    assert "errors" in data

    assert expected_streams.issubset(set(data["summary"]["stream_label"]))
    required_found_files = 6 if data["quarterly_predictions"].empty or data["annual_predictions"].empty else 8
    assert loaded_validation_run.file_status["Found?"].eq("Yes").sum() >= required_found_files


def test_executive_summary_metrics_are_derived_from_finalist_csv(loaded_validation_run: LoadedRun) -> None:
    best = best_by_stream(loaded_validation_run.data["recommended"])
    expected_streams = {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}

    assert expected_streams.issubset(set(best["stream_label"]))
    for stream in expected_streams:
        row = best[best["stream_label"] == stream].iloc[0]
        assert row["quarterly_mape"] > 0
        assert row["annual_mape"] > 0


def test_enterprise_decision_brief_summarises_readiness_and_next_gate(loaded_validation_run: LoadedRun) -> None:
    story = governance_story_summary(
        loaded_validation_run.data["recommended"],
        loaded_validation_run.data["paired_vs_schiff"],
        final_stress_frame(
            loaded_validation_run.data["stress"],
            loaded_validation_run.data["quarterly_predictions"],
            loaded_validation_run.data["annual_predictions"],
            loaded_validation_run.data["recommended"],
            include_extra_buckets=True,
        ),
        loaded_validation_run.data["errors"],
    )

    title, narrative, cards = enterprise_decision_brief(story, loaded_validation_run)

    assert title == "Stage 1 governance decision brief"
    assert "beat the Schiff specification benchmark" in narrative
    assert "Stage 2" in narrative
    assert len(cards) == 4
    assert {card[0] for card in cards} == {"Readiness", "Benchmark result", "Watch point", "Next gate"}


def test_scenario_kpi_cards_lift_decision_metrics(loaded_validation_run: LoadedRun) -> None:
    data = loaded_validation_run.data
    story = governance_story_summary(
        data["recommended"],
        data["paired_vs_schiff"],
        final_stress_frame(
            data["stress"],
            data["quarterly_predictions"],
            data["annual_predictions"],
            data["recommended"],
            include_extra_buckets=True,
        ),
        data["errors"],
    )

    cards = scenario_kpi_cards(data["recommended"], data["paired_vs_schiff"], story)

    assert [card[0] for card in cards] == ["Quarterly MAPE", "Annual MAPE", "Gain vs benchmark", "Decision status"]
    assert all(card[1] for card in cards)
    gain_card = cards[2]
    assert gain_card[1].endswith(" pp")
    assert "Schiff specification benchmark" in gain_card[2]
    assert "paired win" in gain_card[2]
    assert gain_card[3] in {"A better", "Benchmark better"}
    assert "streams beat Schiff specification" in cards[-1][2]


def test_scenario_best_paired_by_stream_keeps_one_manager_row_per_stream(loaded_validation_run: LoadedRun) -> None:
    paired = loaded_validation_run.data["paired_vs_schiff"]

    best = scenario_best_paired_by_stream(paired)

    assert len(best) == best["stream_label"].nunique()
    for stream, group in paired.groupby("stream_label"):
        expected = pd.to_numeric(group["mape_improvement_pct_points"], errors="coerce").max()
        actual = float(best.loc[best["stream_label"] == stream, "mape_improvement_pct_points"].iloc[0])
        assert actual == expected


def test_scenario_paired_display_rows_use_readable_stream_labels(loaded_validation_run: LoadedRun) -> None:
    display = scenario_paired_display_rows(loaded_validation_run.data["paired_vs_schiff"])

    assert set(display["challenger"]) == set(display["stream_label"])
    assert not display["challenger"].astype(str).str.contains("__").any()


def test_scenario_decision_lens_summary_is_concise(loaded_validation_run: LoadedRun) -> None:
    data = loaded_validation_run.data
    story = governance_story_summary(
        data["recommended"],
        data["paired_vs_schiff"],
        final_stress_frame(
            data["stress"],
            data["quarterly_predictions"],
            data["annual_predictions"],
            data["recommended"],
            include_extra_buckets=True,
        ),
        data["errors"],
    )

    summary = scenario_decision_lens_summary(story)

    assert len(summary) < 180
    assert "Schiff specification benchmark" in summary
    assert "Stage 2" in summary


def test_scenario_decision_rule_text_explains_beats_schiff_badge() -> None:
    rule = scenario_decision_rule_text()

    assert "positive full-sample MAPE gain" in rule
    assert "win rate above 55%" in rule


def test_scenario_drilldown_note_names_full_tail_evidence() -> None:
    note = scenario_drilldown_note(184_356, 336)

    assert "Forecast and stress evidence keeps" in note
    assert "full forecast-error tails" in note
    assert "184,356 prediction rows" in note
    assert "336 stress rows" in note


def test_overview_kpi_cards_explain_schiff_specification_and_diagnostics(loaded_validation_run: LoadedRun) -> None:
    data = loaded_validation_run.data
    stress_frame = overview_stress_frame(loaded_validation_run, data["recommended"])
    story = governance_story_summary(data["recommended"], data["paired_vs_schiff"], stress_frame, data["errors"])

    cards = overview_kpi_cards(data["summary"], data["recommended"], story, data["errors"])

    governance_card = next(card for card in cards if card[0] == "Benchmark Pass")
    assert "beat Schiff specification benchmark" in governance_card[2]
    assert "logged diagnostics" in governance_card[3]
    assert "/" in governance_card[1]


def test_overview_frontier_note_is_data_backed(loaded_validation_run: LoadedRun) -> None:
    context = {
        "label": "400 plotted candidates from 400 curated rows",
        "coverage": "Coverage: PED 132 frontier rows; Light RUC 136 frontier rows; Heavy RUC 132 frontier rows.",
    }
    note = overview_frontier_note(loaded_validation_run.data["summary"], context)

    assert "Frontier read:" in note
    assert "Lower-left is better" in note
    assert "Balanced all-stream frontier view" in note
    assert "excluded from governance scoring" in note
    assert "plotted candidates" in note
    assert "Light RUC 136 frontier rows" in note
    assert "plotted Schiff specification anchor rows" in note


def test_overview_stress_watch_note_names_worst_visible_bucket(loaded_validation_run: LoadedRun) -> None:
    frame = overview_stress_frame(loaded_validation_run, loaded_validation_run.data["recommended"])
    note = overview_stress_watch_note(frame)

    assert note.startswith("Stress watch:")
    assert "weakest visible point" in note
    assert "MAPE" in note
    assert "%" in note


def test_overview_error_distribution_note_names_prediction_rows() -> None:
    qpred = pd.DataFrame({"error_pct": [1.0, 2.0, 3.0]})
    note = overview_error_distribution_note(qpred)

    assert "Error distribution read:" in note
    assert "3 finalist prediction rows" in note
    assert "full tails remain in Forecasts and Errors" in note


def test_governance_story_matches_source_csv_metrics(loaded_validation_run: LoadedRun) -> None:
    data = loaded_validation_run.data
    best = best_by_stream(data["recommended"])
    stress_frame = final_stress_frame(
        data["stress"],
        data["quarterly_predictions"],
        data["annual_predictions"],
        data["recommended"],
    )

    story = governance_story_summary(data["recommended"], data["paired_vs_schiff"], stress_frame, data["errors"])

    assert len(story) == best["stream_label"].nunique()
    for _, row in story.iterrows():
        source = best[best["stream_label"] == row["stream_label"]].iloc[0]
        assert row["winning_model"] == source["model"]
        assert row["quarterly_mape"] == source["quarterly_mape"]
        assert row["annual_mape"] == source["annual_mape"]
        assert row["schiff_status"] in {"Beats Schiff", "Average gain, mixed wins", "Does not beat Schiff", "Not verified"}
        assert row["robustness_status"] != ""
        assert row["schiff_summary"]
        assert row["warning_summary"]
        assert row["decision_status"] in {"Promote", "Watchlist", "Reject", "Needs Stage 2"}

    conclusion = manager_conclusion(story)
    assert "Stage 2 uncertainty testing" in conclusion
    assert set(story["decision_status"]).issubset({"Promote", "Watchlist", "Reject", "Needs Stage 2"})

    warning_readout = data_quality_warning_readout(loaded_validation_run, story)
    management_export = management_summary_markdown(loaded_validation_run, story)
    assert "Data-quality warning panel:" in warning_readout
    assert "Stage 1 Management Summary" in management_export
    assert "Stream Decisions" in management_export


def test_governance_story_uses_all_loaded_stress_buckets(loaded_validation_run: LoadedRun) -> None:
    data = loaded_validation_run.data
    stress_frame = final_stress_frame(
        data["stress"],
        data["quarterly_predictions"],
        data["annual_predictions"],
        data["recommended"],
        include_extra_buckets=True,
    )
    story = governance_story_summary(data["recommended"], data["paired_vs_schiff"], stress_frame, data["errors"])
    ped = story[story["stream_label"] == "PED VKT per capita"].iloc[0]

    assert ped["robustness_bucket"] in {"9-12 qtrs", "2022-23", "2024+", "Annual"}
    assert float(ped["robustness_mape"]) > 0


def test_error_flags_match_errors_csv_counts(loaded_validation_run: LoadedRun) -> None:
    errors = loaded_validation_run.data["errors"]
    flags = error_flags(errors).set_index("Flag")["Rows"].to_dict()

    if errors.empty:
        assert flags == {}
        return
    assert flags["Total logged errors"] == len(errors)
    for flag in [
        "HyperOpt missing",
        "Ray root-cause errors",
        "Ray/Tune traceback mentions",
        "Permission errors",
        "neural-model errors",
        "empty files",
    ]:
        assert flag in flags
        assert flags[flag] >= 0
    assert flags["Ray root-cause errors"] == 0
    assert flags["Ray/Tune traceback mentions"] >= flags["Ray root-cause errors"]


def test_error_type_classification_summarises_root_causes(loaded_validation_run: LoadedRun) -> None:
    classified = classify_error_rows(loaded_validation_run.data["errors"]).set_index("Error type")["Rows"].to_dict()

    if loaded_validation_run.data["errors"].empty:
        assert classified == {}
        return
    assert classified["HyperOpt missing"] == len(loaded_validation_run.data["errors"])
    assert classified["Ray root-cause"] == 0
    assert sum(classified.values()) >= len(loaded_validation_run.data["errors"])


def test_percent_unit_warning_detects_mixed_units() -> None:
    frame = pd.DataFrame({"quarterly_mape": [0.05, 0.07, 5.0, 6.0]})
    warnings = percent_unit_warnings(frame, "synthetic")

    assert warnings
    assert "Mixed percent-unit pattern" in warnings[0]


def test_run_health_summary_interprets_error_materiality(loaded_validation_run: LoadedRun) -> None:
    cards, readout = run_health_summary(loaded_validation_run)
    card_titles = [title for title, _, _ in cards]

    assert "Diagnostic Coverage" in card_titles
    assert "Missing Outputs" in card_titles
    assert "Logged Diagnostics" in card_titles
    assert "Ray Root Causes" in card_titles
    assert "Run health read:" in readout
    if loaded_validation_run.data["errors"].empty:
        assert "no logged diagnostics" in readout
    else:
        assert "missing-HyperOpt candidate-search failures" in readout


def test_diagnostics_provenance_note_names_proxy_evidence(loaded_validation_run: LoadedRun) -> None:
    note = diagnostics_provenance_note(loaded_validation_run)

    assert "Diagnostics provenance:" in note
    assert "forecast residual rows" in note
    assert "feature-count rows" in note
    assert "proxy panels are labelled as equivalents" in note


def test_run_evidence_caption_names_run_files_family_scope_and_data_as_of(loaded_validation_run: LoadedRun) -> None:
    caption = run_evidence_caption(loaded_validation_run, "all", "All", 4)

    assert caption.startswith("Run evidence:")
    assert Path(str(loaded_validation_run.run_dir)).name in caption
    assert "files loaded" in caption
    assert "Stage filter: all" in caption
    assert "Family scope: All 4 families" in caption
    assert "Data as of:" in caption


def test_model_aliases_make_dense_model_names_readable() -> None:
    assert model_alias("HEAVY_RUC__struct_log_only__SCHIFF_RESID_GBR__max_depth_1") == (
        "Heavy RUC - Schiff-residual GBM - struct log"
    )
    assert model_alias("PED__screen__solver_static_convex_top19") == "PED - Static solver"


def test_schiff_purity_classifier_separates_residuals_and_blends() -> None:
    assert schiff_class("PED__SCHIFF_SPEC_FINAL_OLS_EXPANDING") == "Schiff specification benchmark"
    assert schiff_class("PED__struct_log_only__SCHIFF_OLS") == "legacy Schiff-style benchmark"
    assert schiff_class("PED__struct_log_only__SCHIFF_RESID_GBR__max_depth_2") == "Schiff residual challenger"
    assert schiff_class("PED__fixedblend_schiff") == "Schiff blend challenger"
    assert schiff_class("PED__screen__solver_static_convex_top19") == "Ensemble challenger"


def test_schiff_compact_summary_lifts_best_paired_gain(loaded_validation_run: LoadedRun) -> None:
    summary = schiff_compact_summary(loaded_validation_run.data["paired_vs_schiff"])

    assert "Best paired challenger:" in summary
    assert "Schiff specification benchmark" in summary
    assert "%" in summary


def test_schiff_kpi_cards_keep_schiff_specification_language(loaded_validation_run: LoadedRun) -> None:
    data = loaded_validation_run.data
    cards = schiff_kpi_cards(data["summary"], data["paired_vs_schiff"], data["recommended"])
    titles = [card[0] for card in cards]
    subtexts = [card[2] for card in cards]

    assert "Schiff Specification Streams" in titles
    assert "Best Schiff Specification Qtr MAPE" in titles
    assert "Paired Comparisons" in titles
    assert "Schiff specification benchmark only" in subtexts
    assert "Schiff specification common pairs" in subtexts


def test_inventory_summary_lifts_key_counts_and_best_rows(loaded_validation_run: LoadedRun) -> None:
    cards, readout = inventory_summary(loaded_validation_run.data["summary"])
    titles = [title for title, _, _ in cards]

    assert "Filtered rows" in titles
    assert "Streams represented" in titles
    assert "Source families" in titles
    assert "Variants" in titles
    assert "Quarterly leader:" in readout
    assert "Annual leader:" in readout
    assert "Scope:" in readout
    assert "Quarterly leader" in readout
    assert "Annual leader" in readout
    assert "source families" in readout


def test_model_detail_summary_links_model_to_schiff_stress_and_components(loaded_validation_run: LoadedRun) -> None:
    model = loaded_validation_run.data["recommended"].iloc[0]["model"]
    detail = model_detail_summary(loaded_validation_run, str(model))

    titles = [title for title, _, _ in detail["cards"]]
    assert "Quarterly MAPE" in titles
    assert "Annual MAPE" in titles
    assert "Components" in titles
    assert "Model detail read:" in detail["readout"]
    assert "stress" in detail["readout"].lower()


def test_inventory_ranking_options_include_governance_and_bias_when_available(loaded_validation_run: LoadedRun) -> None:
    options = inventory_rank_options(loaded_validation_run.data["summary"])

    assert "quarterly_mape" in options
    assert "annual_mape" in options
    assert "governance_score" in options
    assert "quarterly_bias_pct" in options


def test_inventory_visuals_show_family_performance_and_schiff_mix(loaded_validation_run: LoadedRun) -> None:
    summary = loaded_validation_run.data["summary"].head(200)
    family_fig = plot_inventory_family_performance(summary, "quarterly_mape")
    mix_fig = plot_schiff_class_mix(summary)

    assert "schiff_class" in loaded_validation_run.data["summary"].columns
    assert len(family_fig.data) > 0
    assert "Model family performance by stream" in str(family_fig.layout.title.text)
    assert len(mix_fig.data) > 0
    assert "Schiff specification and legacy-style mix" in str(mix_fig.layout.title.text)


def test_loader_schema_version_invalidates_streamlit_cache_for_schema_changes() -> None:
    assert "schiff-class" in LOADER_SCHEMA_VERSION


def test_schema_diagnostics_are_kept_out_of_global_warning_stack() -> None:
    warnings = (
        "Run folder does not exist",
        "Mixed percent-unit pattern detected in stress.bias_pct; review whether values are proportions or percentage points.",
    )

    assert global_warnings(warnings) == ["Run folder does not exist"]
    assert schema_diagnostics(warnings) == [warnings[1]]


def test_core_charts_are_populated_from_real_run_data(loaded_validation_run: LoadedRun) -> None:
    data = loaded_validation_run.data
    stress_frame = final_stress_frame(
        data["stress"],
        data["quarterly_predictions"],
        data["annual_predictions"],
        data["recommended"],
    )

    figures = [
        plot_finalist_accuracy(data["recommended"]),
        plot_candidate_landscape(data["summary"].head(100)),
        plot_schiff_benchmark(data["summary"]),
        plot_paired_improvement(data["paired_vs_schiff"], top_n=20),
        plot_stress_checks(stress_frame),
    ]
    if not selected_predictions_missing(loaded_validation_run):
        figures.append(plot_error_distribution(data["quarterly_predictions"].head(5_000)))

    for figure in figures:
        assert len(figure.data) > 0
        assert all(getattr(trace, "x", None) is not None or getattr(trace, "y", None) is not None for trace in figure.data)


def test_candidate_landscape_focuses_competitive_frontier(loaded_validation_run: LoadedRun) -> None:
    figure = plot_candidate_landscape(loaded_validation_run.data["summary"])

    assert figure.layout.xaxis.range is not None
    assert figure.layout.yaxis.range is not None
    assert figure.layout.xaxis.range[1] < 40
    assert figure.layout.yaxis.range[1] < 25
    assert any("competitive frontier" in annotation.text for annotation in figure.layout.annotations)
    assert not any(trace.name == "Efficient frontier" for trace in figure.data)
    assert not any(getattr(trace, "mode", "") == "lines" for trace in figure.data)
    assert "Schiff class" in str(figure.data[0].hovertemplate)


def test_candidate_outlier_filter_preserves_finalists_and_schiff(loaded_validation_run: LoadedRun) -> None:
    summary = loaded_validation_run.data["summary"].copy()
    filtered = hide_candidate_outliers(summary)

    assert 0 < len(filtered) <= len(summary)
    if "is_finalist" in summary.columns:
        finalist_keys = set(summary.loc[summary["is_finalist"], "model"].astype(str))
        filtered_keys = set(filtered["model"].astype(str))
        assert finalist_keys.issubset(filtered_keys)
    if "is_schiff" in summary.columns:
        schiff_keys = set(summary.loc[summary["is_schiff"], "model"].astype(str))
        filtered_keys = set(filtered["model"].astype(str))
        assert schiff_keys.issubset(filtered_keys)


def test_ensemble_composition_uses_recommended_weighted_finalists(loaded_validation_run: LoadedRun) -> None:
    recommended = loaded_validation_run.data["recommended"]
    weights = loaded_validation_run.data["weights"]

    matching_models = recommended_models_with_weights(recommended, weights)
    selected_models = best_weighted_finalist_models(recommended, weights)
    plot_data = weights[weights["ensemble"].astype(str).isin(selected_models)]
    figure, mapping = plot_ensemble_composition(plot_data)

    assert matching_models, "recommended_finalists.csv should include ensemble names present in ensemble_weights.csv"
    assert selected_models, "best finalist by stream must resolve to at least one weighted ensemble"
    assert not plot_data.empty
    assert len(figure.data) > 0
    assert not mapping.empty
    assert {"Label", "Component model identifier", "Average weight (%)"}.issubset(mapping.columns)


def test_ensemble_composition_explains_single_component_finalists(loaded_validation_run: LoadedRun) -> None:
    recommended = loaded_validation_run.data["recommended"]
    weights = loaded_validation_run.data["weights"]
    selected_models = best_weighted_finalist_models(recommended, weights)
    plot_data = weights[weights["ensemble"].astype(str).isin(selected_models)]

    insight = ensemble_composition_insight(plot_data)

    assert ("Single-component finalist selection" in insight and "not placeholder weights" in insight) or (
        "Blended finalist selection" in insight and "components per stream" in insight
    )


def test_ensemble_method_readout_flags_static_without_prequential_support(loaded_validation_run: LoadedRun) -> None:
    readout = ensemble_method_readout(
        loaded_validation_run.data["weights"],
        loaded_validation_run.data["recommended"],
    )

    assert "Ensemble method read:" in readout
    assert "static" in readout.lower() or "prequential" in readout.lower()


def test_ensemble_fallback_scores_normalise_origin_level_weights() -> None:
    weights = pd.DataFrame(
        {
            "stream_label": ["PED VKT per capita"] * 4,
            "ensemble": ["static", "prequential", "prequential", "prequential"],
            "component_model": ["a", "b", "b", "b"],
            "origin": ["", "2020Q1", "2020Q2", "2020Q3"],
            "weight": [1.0, 1.0, 1.0, 1.0],
        }
    )
    scores = ensemble_fallback_scores(weights).set_index("ensemble")["selection_score"].to_dict()

    assert scores["static"] == 1.0
    assert scores["prequential"] == 1.0


def test_filters_change_candidate_results(loaded_validation_run: LoadedRun) -> None:
    summary = loaded_validation_run.data["summary"]
    ped_only = filter_by_common_controls(
        summary,
        stage="all",
        streams=["PED VKT per capita"],
        source_families=None,
        variants=None,
        include_schiff=True,
        show_screen=True,
        show_final=True,
    )

    assert 0 < len(ped_only) < len(summary)
    assert set(ped_only["stream_label"]) == {"PED VKT per capita"}


def test_empty_common_filter_selections_return_empty_frames(loaded_validation_run: LoadedRun) -> None:
    summary = loaded_validation_run.data["summary"]

    assert filter_by_common_controls(summary, streams=[]).empty
    assert filter_by_common_controls(summary, source_families=[]).empty
    assert filter_by_common_controls(summary, variants=[]).empty


def test_candidate_landscape_export_columns_are_available(loaded_validation_run: LoadedRun) -> None:
    summary = loaded_validation_run.data["summary"].head(20)
    required = {"stage", "stream_label", "variant", "source_family", "model", "quarterly_mape", "annual_mape"}

    assert required.issubset(summary.columns)
    assert "schiff_class" in summary.columns


def test_stress_checks_cover_required_buckets(loaded_validation_run: LoadedRun) -> None:
    data = loaded_validation_run.data
    stress_frame = final_stress_frame(
        data["stress"],
        data["quarterly_predictions"],
        data["annual_predictions"],
        data["recommended"],
    )
    buckets = set(stress_frame["stress_bucket"].astype(str))

    for bucket in ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2024+", "2022-23", "Annual"]:
        assert bucket in buckets
    expanded_buckets = set(
        final_stress_frame(
            data["stress"],
            data["quarterly_predictions"],
            data["annual_predictions"],
            data["recommended"],
            include_extra_buckets=True,
        )["stress_bucket"].astype(str)
    )
    assert {"1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2024+", "2022-23", "Annual"}.issubset(expanded_buckets)


def test_overview_stress_frame_matches_reference_buckets(loaded_validation_run: LoadedRun) -> None:
    frame = overview_stress_frame(loaded_validation_run, loaded_validation_run.data["recommended"])
    buckets = list(frame["stress_bucket"].dropna().astype(str).unique())

    assert "2020-21" not in buckets
    assert "2024+" not in buckets
    assert "2022-23" not in buckets
    for bucket in ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "Annual"]:
        assert bucket in buckets


def test_stress_chart_and_readout_include_high_risk_threshold(loaded_validation_run: LoadedRun) -> None:
    data = loaded_validation_run.data
    stress_frame = final_stress_frame(
        data["stress"],
        data["quarterly_predictions"],
        data["annual_predictions"],
        data["recommended"],
    )
    figure = plot_stress_checks(stress_frame)
    readout = stress_readout(stress_frame)

    assert any(float(shape.y0) == 10.0 and float(shape.y1) == 10.0 for shape in figure.layout.shapes)
    assert any(getattr(shape, "type", "") == "rect" and float(shape.y0) == 10.0 for shape in figure.layout.shapes)
    assert "10% high-risk guide" in str(figure.layout.annotations)
    assert "High-risk zone" in str(figure.layout.annotations)
    assert "Stress read:" in readout
    assert "worst bucket" in readout


def test_forecast_error_readout_summarises_selected_rows(loaded_validation_run: LoadedRun) -> None:
    qpred = loaded_validation_run.data["quarterly_predictions"].head(250)
    readout = forecast_error_readout(qpred)

    assert "Forecast read:" in readout
    if selected_predictions_missing(loaded_validation_run):
        assert "no forecast-error rows" in readout
        return
    assert "absolute error" in readout
    assert "Largest miss" in readout


def test_forecast_error_charts_include_time_and_horizon_views(loaded_validation_run: LoadedRun) -> None:
    qpred = loaded_validation_run.data["quarterly_predictions"].head(2_000)
    percent_fig = plot_percent_error_over_time(qpred)
    horizon_fig = plot_horizon_mape(qpred)

    if selected_predictions_missing(loaded_validation_run):
        assert len(percent_fig.data) == 0
        assert len(horizon_fig.data) == 0
        return
    assert len(percent_fig.data) > 0
    assert "Forecast percentage error over time" in str(percent_fig.layout.title.text)
    assert len(horizon_fig.data) > 0
    assert "MAPE by forecast horizon" in str(horizon_fig.layout.title.text)


def test_residual_vs_fitted_proxy_is_populated(loaded_validation_run: LoadedRun) -> None:
    qpred = central_error_window(loaded_validation_run.data["quarterly_predictions"].head(5_000))
    figure = plot_residual_vs_fitted(qpred)

    if selected_predictions_missing(loaded_validation_run):
        assert len(figure.data) == 0
        assert "Prediction rows need fitted values" in str(figure.layout.annotations)
        return
    assert len(figure.data) > 0
    assert "Residuals vs fitted by stream" in str(figure.layout.title.text)
    assert "Fitted value" in str(figure.layout.xaxis.title.text)


def test_autocorrelation_diagnostics_uses_lag_bars(loaded_validation_run: LoadedRun) -> None:
    qpred = central_error_window(loaded_validation_run.data["quarterly_predictions"].head(20_000))
    acf_source = build_diagnostic_acf_source_table(qpred, loaded_validation_run.data["diagnostic_df"])
    figure = plot_autocorrelation_diagnostics(qpred, acf_source=acf_source)

    assert len(figure.data) > 0
    assert all(getattr(trace, "type", "") == "bar" for trace in figure.data)
    assert "Residual ACF by lag" in str(figure.layout.title.text)
    assert "Lag" in str(figure.layout.xaxis.title.text)
    assert "Residual ACF" in str(figure.layout.yaxis.title.text)


def test_central_error_window_keeps_diagnostics_readable() -> None:
    frame = pd.DataFrame({"error_pct": [-5_000, -10, -2, 0, 1, 2, 10, 5_000] * 4})

    trimmed = central_error_window(frame, lower=0.15, upper=0.85)

    assert 0 < len(trimmed) < len(frame)
    assert trimmed["error_pct"].abs().max() < 5_000


def test_error_type_chart_is_populated_from_error_summary(loaded_validation_run: LoadedRun) -> None:
    error_types = classify_error_rows(loaded_validation_run.data["errors"])
    figure = plot_error_types(error_types)

    if loaded_validation_run.data["errors"].empty:
        assert "No error diagnostics are available" in str(figure.layout.annotations)
    else:
        assert len(figure.data) > 0
        assert "Logged diagnostics by error type" in str(figure.layout.title.text)
