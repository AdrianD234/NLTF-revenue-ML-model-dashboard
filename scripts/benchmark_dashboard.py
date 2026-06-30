from __future__ import annotations

import argparse
import importlib
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def prefer_local_pyarrow_runtime() -> None:
    """Use the repo-local PyArrow runtime for local benchmarks when present.

    The benchmark imports data_loader before app.py. Without this guard, local
    Windows base Python can import older PyArrow first and fail on committed
    evidence-pack parquet files that the app itself can read.
    """

    disabled = os.environ.get("NLTF_DISABLE_RUNTIME_PYARROW24", "").strip().lower() in {"1", "true", "yes"}
    runtime = ROOT / ".runtime_pyarrow24"
    if not disabled and runtime.exists() and str(runtime) not in sys.path:
        sys.path.insert(0, str(runtime))


prefer_local_pyarrow_runtime()

DEFAULT_PARQUET_DATA_ROOT = Path(
    os.environ.get("DASHBOARD_EVIDENCE_PACK_ROOT")
    or os.environ.get("STAGE1_DASHBOARD_EVIDENCE_PACK_ROOT")
    or Path("data") / "dashboard_evidence_pack"
)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def timed(label: str, fn: Callable[[], Any], repeats: int = 3) -> dict[str, Any]:
    values: list[float] = []
    last_result: Any = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        last_result = fn()
        values.append(time.perf_counter() - t0)
    result = {
        "label": label,
        "repeats": repeats,
        "min_sec": min(values),
        "median_sec": statistics.median(values),
        "max_sec": max(values),
        "result_type": type(last_result).__name__,
    }
    if isinstance(last_result, int | float | str | bool | type(None)):
        result["result_value"] = last_result
    return result


def load_dashboard_modules() -> dict[str, Any]:
    modules: dict[str, Any] = {}
    for name in ["model_dashboard.data_loader", "model_dashboard.metrics", "model_dashboard.plots", "app"]:
        try:
            modules[name] = importlib.import_module(name)
        except Exception as exc:  # pragma: no cover - reported in benchmark JSON
            modules[name] = f"IMPORT_ERROR: {type(exc).__name__}: {exc}"
    return modules


def row_counts(loaded: Any) -> dict[str, int]:
    data = getattr(loaded, "data", {})
    return {name: int(len(frame)) for name, frame in data.items() if hasattr(frame, "__len__")}


def figure_json_bytes(fig: Any) -> int:
    if not hasattr(fig, "to_json"):
        return 0
    return len(fig.to_json().encode("utf-8"))


def summary_table_prep(summary: Any) -> int:
    if summary is None or getattr(summary, "empty", True):
        return 0
    metric_cols = [
        col
        for col in ["quarterly_mape", "annual_mape", "governance_score", "quarterly_bias_pct", "annual_bias_pct"]
        if col in summary.columns
    ]
    if not metric_cols:
        return int(len(summary))
    grouped = summary.groupby(["stream_label", "source_family"], dropna=False)[metric_cols].median(numeric_only=True)
    return int(len(grouped))


def candidate_landscape_prep(summary: Any, plots: Any) -> int:
    if summary is None or getattr(summary, "empty", True):
        return 0
    required = {"quarterly_mape", "annual_mape", "stream_label"}
    if not required.issubset(summary.columns):
        return 0
    data = summary.dropna(subset=["quarterly_mape", "annual_mape"]).copy()
    if data.empty:
        return 0
    return int(len(plots._competitive_landscape_subset(data)))


def ensemble_composition_prep(weights: Any) -> int:
    if weights is None or getattr(weights, "empty", True) or "component_model" not in weights.columns:
        return 0
    group_cols = [col for col in ["stream_label", "ensemble", "component_model"] if col in weights.columns]
    if not group_cols:
        return int(len(weights))
    return int(len(weights.groupby(group_cols, dropna=False)))


def stress_summary_prep(stress: Any) -> int:
    if stress is None or getattr(stress, "empty", True):
        return 0
    group_cols = [col for col in ["stream_label", "stress_bucket"] if col in stress.columns]
    if not group_cols or "mape" not in stress.columns:
        return int(len(stress))
    grouped = stress.groupby(group_cols, dropna=False)["mape"].median()
    return int(len(grouped))


def model_inventory_prep(summary: Any) -> int:
    if summary is None or getattr(summary, "empty", True):
        return 0
    metric = "quarterly_mape" if "quarterly_mape" in summary.columns else summary.columns[0]
    return int(len(summary.sort_values(metric, ascending=True).head(100)))


def run_audit_prep(loaded: Any) -> int:
    file_rows = len(getattr(loaded, "file_status", []))
    errors = loaded.data.get("errors") if hasattr(loaded, "data") else None
    error_rows = 0 if errors is None or getattr(errors, "empty", True) else len(errors)
    return int(file_rows + error_rows)


def finalist_prediction_rows(loaded: Any, metrics: Any) -> Any:
    qpred = loaded.data.get("quarterly_predictions")
    recommended = loaded.data.get("recommended")
    if qpred is None or getattr(qpred, "empty", True) or recommended is None or getattr(recommended, "empty", True):
        return qpred
    best = metrics.best_by_stream(recommended)
    keys = metrics.model_key_set(best)
    if not keys:
        return qpred.head(1000)
    return metrics.filter_to_model_keys(qpred, keys)


def render_overview_page_proxy(loaded: Any, metrics: Any, plots: Any) -> int:
    recommended = loaded.data.get("recommended")
    summary = loaded.data.get("summary")
    weights = loaded.data.get("weights")
    stress = loaded.data.get("stress")
    qpred = finalist_prediction_rows(loaded, metrics)
    figures = [
        plots.plot_finalist_accuracy(recommended),
        plots.plot_candidate_landscape(summary),
        plots.plot_ensemble_composition(weights)[0],
        plots.plot_stress_checks(stress),
        plots.plot_error_distribution(qpred),
    ]
    return int(sum(figure_json_bytes(fig) for fig in figures))


def render_forecasts_page_proxy(loaded: Any, metrics: Any, plots: Any) -> int:
    qpred = finalist_prediction_rows(loaded, metrics)
    figures = [
        plots.plot_actual_vs_predicted(qpred),
        plots.plot_percent_error_over_time(qpred),
        plots.plot_error_distribution(qpred),
        plots.plot_horizon_mape(qpred),
    ]
    return int(sum(figure_json_bytes(fig) for fig in figures))


def benchmark_backend(run_dir: Path, repeats: int) -> dict[str, Any]:
    modules = load_dashboard_modules()
    results: dict[str, Any] = {
        "timestamp": now_iso(),
        "run_dir": str(run_dir),
        "benchmarks": [],
        "module_status": {name: "ok" if not isinstance(module, str) else module for name, module in modules.items()},
        "notes": [],
    }

    loader = modules.get("model_dashboard.data_loader")
    metrics = modules.get("model_dashboard.metrics")
    plots = modules.get("model_dashboard.plots")
    app_module = modules.get("app")
    if isinstance(loader, str):
        results["notes"].append("data_loader import failed; no backend benchmarks were run.")
        return results

    curated_dir = Path("artifacts") / "curated_data"
    use_curated = hasattr(loader, "curated_manifest_matches") and loader.curated_manifest_matches(curated_dir, run_dir)

    def load_uncached() -> Any:
        if use_curated and hasattr(loader, "load_curated_run"):
            return loader.load_curated_run(curated_dir, run_dir)
        return loader.load_run(run_dir)

    cold = timed("load_run_uncached", load_uncached, repeats=max(1, min(repeats, 2)))
    loaded = load_uncached()
    results["benchmarks"].append(cold)
    results["row_counts"] = row_counts(loaded)

    signature = loader.run_signature(run_dir)
    curated_sig = loader.curated_signature(curated_dir) if use_curated and hasattr(loader, "curated_signature") else tuple()
    if not isinstance(app_module, str) and hasattr(app_module, "cached_load_run"):
        try:
            app_module.cached_load_run.clear()
            if hasattr(app_module, "cached_load_curated_run"):
                app_module.cached_load_curated_run.clear()
        except Exception:
            results["notes"].append("Could not clear Streamlit cache before warm-load benchmark.")

        def cached_call() -> Any:
            if use_curated and hasattr(app_module, "cached_load_curated_run"):
                return app_module.cached_load_curated_run(
                    str(curated_dir), str(run_dir), curated_sig, signature, app_module.LOADER_SCHEMA_VERSION
                )
            return app_module.cached_load_run(str(run_dir), signature, app_module.LOADER_SCHEMA_VERSION)

        results["benchmarks"].append(
            timed(
                "cached_load_run_first_call",
                cached_call,
                repeats=1,
            )
        )
        results["benchmarks"].append(
            timed(
                "cached_load_run_warm_call",
                cached_call,
                repeats=repeats,
            )
        )

    if not isinstance(metrics, str):
        recommended = loaded.data.get("recommended")
        summary = loaded.data.get("summary")
        paired = loaded.data.get("paired_vs_schiff")
        stress = loaded.data.get("stress")
        qpred = loaded.data.get("quarterly_predictions")
        results["benchmarks"].extend(
            [
                timed("summary_generation_prep", lambda: summary_table_prep(summary), repeats=repeats),
                timed("best_by_stream_recommended", lambda: metrics.best_by_stream(recommended), repeats=repeats),
                timed("governance_story_summary", lambda: metrics.governance_story_summary(recommended, paired, stress, loaded.data.get("errors")), repeats=repeats),
                timed("filter_summary_common_controls", lambda: metrics.filter_by_common_controls(summary, stage="all", streams=["All"], source_families=["All"], variants=["All"]), repeats=repeats),
                timed("filter_qpred_common_controls", lambda: metrics.filter_by_common_controls(qpred, stage="all", streams=["All"], include_schiff=True), repeats=repeats),
                timed("stress_summary_prep", lambda: stress_summary_prep(stress), repeats=repeats),
                timed("model_inventory_prep", lambda: model_inventory_prep(summary), repeats=repeats),
                timed("run_audit_prep", lambda: run_audit_prep(loaded), repeats=repeats),
            ]
        )

    if not isinstance(plots, str):
        summary = loaded.data.get("summary")
        recommended = loaded.data.get("recommended")
        weights = loaded.data.get("weights")
        qpred = loaded.data.get("quarterly_predictions")
        stress = loaded.data.get("stress")
        error_types = metrics.classify_error_rows(loaded.data.get("errors")) if not isinstance(metrics, str) else loaded.data.get("errors")
        results["benchmarks"].extend(
            [
                timed("candidate_landscape_data_prep", lambda: candidate_landscape_prep(summary, plots), repeats=repeats),
                timed("ensemble_composition_data_prep", lambda: ensemble_composition_prep(weights), repeats=repeats),
                timed("overview_page_render_proxy", lambda: render_overview_page_proxy(loaded, metrics, plots), repeats=max(1, min(repeats, 2))) if not isinstance(metrics, str) else timed("overview_page_render_proxy", lambda: 0, repeats=1),
                timed("forecasts_and_errors_render_proxy", lambda: render_forecasts_page_proxy(loaded, metrics, plots), repeats=max(1, min(repeats, 2))) if not isinstance(metrics, str) else timed("forecasts_and_errors_render_proxy", lambda: 0, repeats=1),
                timed("plot_finalist_accuracy", lambda: plots.plot_finalist_accuracy(recommended), repeats=repeats),
                timed("plot_candidate_landscape", lambda: plots.plot_candidate_landscape(summary), repeats=max(1, min(repeats, 2))),
                timed("plot_ensemble_composition", lambda: plots.plot_ensemble_composition(weights), repeats=max(1, min(repeats, 2))),
                timed("plot_horizon_mape", lambda: plots.plot_horizon_mape(qpred), repeats=max(1, min(repeats, 2))),
                timed("plot_stress_checks", lambda: plots.plot_stress_checks(stress), repeats=max(1, min(repeats, 2))),
                timed("plot_inventory_family_performance", lambda: plots.plot_inventory_family_performance(summary), repeats=max(1, min(repeats, 2))),
                timed("plot_error_types", lambda: plots.plot_error_types(error_types), repeats=max(1, min(repeats, 2))),
                timed("plot_error_distribution", lambda: plots.plot_error_distribution(qpred), repeats=max(1, min(repeats, 2))),
                timed(
                    "plot_error_distribution_json_bytes",
                    lambda: figure_json_bytes(plots.plot_error_distribution(qpred)),
                    repeats=1,
                ),
                timed(
                    "plot_candidate_landscape_json_bytes",
                    lambda: figure_json_bytes(plots.plot_candidate_landscape(summary)),
                    repeats=1,
                ),
                timed(
                    "plot_residual_vs_fitted_json_bytes",
                    lambda: figure_json_bytes(plots.plot_residual_vs_fitted(qpred)),
                    repeats=1,
                ),
            ]
        )
    return results


def benchmark_parquet_backend(data_root: Path, repo_root: Path, repeats: int) -> dict[str, Any]:
    modules = load_dashboard_modules()
    results: dict[str, Any] = {
        "timestamp": now_iso(),
        "source_mode": "dashboard_evidence_pack",
        "data_root": str(data_root),
        "repo_root": str(repo_root),
        "benchmarks": [],
        "module_status": {name: "ok" if not isinstance(module, str) else module for name, module in modules.items()},
        "notes": ["Evidence-pack Parquet dashboard benchmark path."],
    }

    loader = modules.get("model_dashboard.data_loader")
    metrics = modules.get("model_dashboard.metrics")
    plots = modules.get("model_dashboard.plots")
    app_module = modules.get("app")
    if isinstance(loader, str):
        results["notes"].append("data_loader import failed; no Parquet benchmarks were run.")
        return results

    def load_uncached() -> Any:
        return loader.load_evidence_pack(data_root, repo_root)

    try:
        cold = timed("load_evidence_pack_uncached", load_uncached, repeats=max(1, min(repeats, 2)))
        loaded = load_uncached()
    except Exception as exc:
        results["notes"].append(f"Evidence-pack benchmark failed: {type(exc).__name__}: {exc}")
        results["benchmarks"].append(
            {
                "label": "load_evidence_pack_uncached",
                "repeats": 0,
                "min_sec": None,
                "median_sec": None,
                "max_sec": None,
                "result_type": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        return results

    results["benchmarks"].append(cold)
    results["row_counts"] = row_counts(loaded)

    if not isinstance(app_module, str) and hasattr(app_module, "cached_load_evidence_pack"):
        try:
            app_module.cached_load_evidence_pack.clear()
        except Exception:
            results["notes"].append("Could not clear Streamlit evidence-pack cache before warm-load benchmark.")

        pack_sig = loader.evidence_pack_signature(data_root)

        def cached_call() -> Any:
            return app_module.cached_load_evidence_pack(
                str(data_root),
                str(repo_root),
                pack_sig,
                app_module.LOADER_SCHEMA_VERSION,
            )

        results["benchmarks"].append(timed("cached_load_evidence_pack_first_call", cached_call, repeats=1))
        results["benchmarks"].append(timed("cached_load_evidence_pack_warm_call", cached_call, repeats=repeats))

    if not isinstance(metrics, str):
        recommended = loaded.data.get("recommended")
        summary = loaded.data.get("summary")
        paired = loaded.data.get("paired_vs_schiff")
        stress = loaded.data.get("stress")
        qpred = loaded.data.get("quarterly_predictions")
        results["benchmarks"].extend(
            [
                timed("summary_generation_prep", lambda: summary_table_prep(summary), repeats=repeats),
                timed("best_by_stream_recommended", lambda: metrics.best_by_stream(recommended), repeats=repeats),
                timed(
                    "governance_story_summary",
                    lambda: metrics.governance_story_summary(recommended, paired, stress, loaded.data.get("errors")),
                    repeats=repeats,
                ),
                timed(
                    "filter_summary_common_controls",
                    lambda: metrics.filter_by_common_controls(
                        summary,
                        stage="all",
                        streams=["All"],
                        source_families=["All"],
                        variants=["All"],
                    ),
                    repeats=repeats,
                ),
                timed(
                    "filter_qpred_common_controls",
                    lambda: metrics.filter_by_common_controls(qpred, stage="all", streams=["All"], include_schiff=True),
                    repeats=repeats,
                ),
                timed("stress_summary_prep", lambda: stress_summary_prep(stress), repeats=repeats),
                timed("model_inventory_prep", lambda: model_inventory_prep(summary), repeats=repeats),
                timed("run_audit_prep", lambda: run_audit_prep(loaded), repeats=repeats),
            ]
        )

    if not isinstance(plots, str):
        summary = loaded.data.get("summary")
        recommended = loaded.data.get("recommended")
        weights = loaded.data.get("weights")
        qpred = loaded.data.get("quarterly_predictions")
        stress = loaded.data.get("stress")
        error_types = metrics.classify_error_rows(loaded.data.get("errors")) if not isinstance(metrics, str) else loaded.data.get("errors")
        results["benchmarks"].extend(
            [
                timed("candidate_landscape_data_prep", lambda: candidate_landscape_prep(summary, plots), repeats=repeats),
                timed("ensemble_composition_data_prep", lambda: ensemble_composition_prep(weights), repeats=repeats),
                timed(
                    "overview_page_render_proxy",
                    lambda: render_overview_page_proxy(loaded, metrics, plots),
                    repeats=max(1, min(repeats, 2)),
                )
                if not isinstance(metrics, str)
                else timed("overview_page_render_proxy", lambda: 0, repeats=1),
                timed(
                    "forecasts_and_errors_render_proxy",
                    lambda: render_forecasts_page_proxy(loaded, metrics, plots),
                    repeats=max(1, min(repeats, 2)),
                )
                if not isinstance(metrics, str)
                else timed("forecasts_and_errors_render_proxy", lambda: 0, repeats=1),
                timed("plot_finalist_accuracy", lambda: plots.plot_finalist_accuracy(recommended), repeats=repeats),
                timed("plot_candidate_landscape", lambda: plots.plot_candidate_landscape(summary), repeats=max(1, min(repeats, 2))),
                timed("plot_ensemble_composition", lambda: plots.plot_ensemble_composition(weights), repeats=max(1, min(repeats, 2))),
                timed("plot_horizon_mape", lambda: plots.plot_horizon_mape(qpred), repeats=max(1, min(repeats, 2))),
                timed("plot_stress_checks", lambda: plots.plot_stress_checks(stress), repeats=max(1, min(repeats, 2))),
                timed("plot_inventory_family_performance", lambda: plots.plot_inventory_family_performance(summary), repeats=max(1, min(repeats, 2))),
                timed("plot_error_types", lambda: plots.plot_error_types(error_types), repeats=max(1, min(repeats, 2))),
                timed("plot_error_distribution", lambda: plots.plot_error_distribution(qpred), repeats=max(1, min(repeats, 2))),
                timed(
                    "plot_error_distribution_json_bytes",
                    lambda: figure_json_bytes(plots.plot_error_distribution(qpred)),
                    repeats=1,
                ),
                timed(
                    "plot_candidate_landscape_json_bytes",
                    lambda: figure_json_bytes(plots.plot_candidate_landscape(summary)),
                    repeats=1,
                ),
                timed(
                    "plot_residual_vs_fitted_json_bytes",
                    lambda: figure_json_bytes(plots.plot_residual_vs_fitted(qpred)),
                    repeats=1,
                ),
            ]
        )

    return results


def append_history(history_path: Path, result: dict[str, Any]) -> None:
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
    else:
        history = []
    history.append(result)
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def write_performance_review(out_dir: Path, result: dict[str, Any]) -> None:
    status = "in progress"
    if result.get("benchmarks") and not any(bench.get("result_type") == "ERROR" for bench in result["benchmarks"]):
        status = "measured"
    rows = []
    for bench in result.get("benchmarks", []):
        rows.append(
            "| {label} | {median} | {max_value} | {kind} |".format(
                label=bench.get("label", "unknown"),
                median="n/a" if bench.get("median_sec") is None else f"{bench.get('median_sec'):.3f}s",
                max_value="n/a" if bench.get("max_sec") is None else f"{bench.get('max_sec'):.3f}s",
                kind=bench.get("result_type", "unknown"),
            )
        )
    review = "\n".join(
        [
            "# Performance Review",
            "",
            f"Status: **{status}**.",
            f"Generated: {result.get('timestamp', now_iso())}",
            "",
            "This artifact must be regenerated after the Parquet-backed app and browser pass are available.",
            "",
            "## Source",
            "",
            f"- Run dir: `{result.get('run_dir', 'n/a')}`",
            f"- Data root: `{result.get('data_root', 'n/a')}`",
            "",
            "## Benchmarks",
            "",
            "| Benchmark | Median | Max | Result |",
            "| --- | ---: | ---: | --- |",
            *rows,
            "",
            "## Notes",
            "",
            *[f"- {note}" for note in result.get("notes", [])],
            "",
        ]
    )
    (out_dir / "performance_review.md").write_text(review, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir")
    parser.add_argument(
        "--data-root",
        default=None,
        help="Benchmark the dashboard evidence pack. Defaults to DASHBOARD_EVIDENCE_PACK_ROOT, STAGE1_DASHBOARD_EVIDENCE_PACK_ROOT, or data/dashboard_evidence_pack.",
    )
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--out-dir", default="artifacts")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--refresh-baseline",
        action="store_true",
        help="Overwrite performance_baseline.json with this measured run.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.run_dir and args.data_root is None:
        run_dir = Path(args.run_dir).expanduser()
        results = benchmark_backend(run_dir, max(1, args.repeats))
    else:
        data_root = Path(args.data_root or DEFAULT_PARQUET_DATA_ROOT).expanduser()
        results = benchmark_parquet_backend(data_root, Path(args.repo_root).expanduser(), max(1, args.repeats))

    latest_path = out_dir / "performance_latest.json"
    baseline_path = out_dir / "performance_baseline.json"
    history_path = out_dir / "performance_history.json"
    latest_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    if args.refresh_baseline or not baseline_path.exists():
        baseline_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    append_history(history_path, results)
    write_performance_review(out_dir, results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
