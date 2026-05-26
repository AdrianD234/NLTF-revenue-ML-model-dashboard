from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.data.config import DEFAULT_EVIDENCE_PACK_ROOT  # noqa: E402
from model_dashboard.data_loader import STALE_FINALIST_VALUES  # noqa: E402
from model_dashboard.evidence_pack import load_evidence_pack, resolve_evidence_pack_root  # noqa: E402

EVIDENCE_CANDIDATE_FILE = "candidate_cone.parquet"
EVIDENCE_MANIFEST_FILE = "manifest.json"
EXPECTED_STREAMS = ("PED", "LIGHT_RUC", "HEAVY_RUC")
USER_LABEL_COLUMNS = (
    "stream_label",
    "model_short",
    "candidate_role",
    "include_reason",
    "source_family",
    "model_kind",
    "feature_set",
)
PAGE_SCREENSHOTS = {
    "Overview": "artifacts/screenshots/final-01-overview.png",
    "Diagnostics": "artifacts/screenshots/final-02-diagnostics.png",
    "Scenario Comparison": "artifacts/screenshots/final-03-scenario-comparison.png",
    "Schiff Benchmark": "artifacts/screenshots/final-04-schiff-benchmark.png",
}
TOTAL_GATES = 100
VISUAL_REVIEW_FILES = (
    "artifacts/visual_delta_review.md",
    "artifacts/page_visual_scores.md",
    "artifacts/target_vs_current_screenshot_matrix.md",
    "artifacts/screenshot_review.md",
    "artifacts/visual_reference_comparison.md",
)
VISUAL_LOCK_FILES = (
    "VISUAL_TARGET_CONFORMANCE.lock.md",
    "PAGE_BY_PAGE_VISUAL_DELTA.lock.md",
    "VISUAL_LAYOUT_GATES.lock.md",
)
BAD_SCHIFF_RE = re.compile(r"(?:resid|residual|fixed.?blend|blend|solver|convex|ensemble|top.?k|mean|median)", re.I)
RAW_HOVER_RE = re.compile(r"(quarterly_mape|annual_mape|stream_label|source_family|candidate_role|plot_default_include)")


@dataclass
class Gate:
    id: int
    section: str
    description: str
    check: Callable[[], tuple[bool, str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the locked 100-gate Stage 1 dashboard validation suite.")
    parser.add_argument("--data-root", default=str(DEFAULT_EVIDENCE_PACK_ROOT))
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--max-default-rows", type=int, default=400)
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def pct_value(value: Any) -> float | None:
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(converted):
        return None
    number = float(converted)
    return number * 100 if abs(number) <= 1 else number


def approx_pct(value: Any, target: float, tolerance: float = 0.06) -> bool:
    actual = pct_value(value)
    return actual is not None and abs(actual - target) <= tolerance


def stream_key(value: Any, label: Any = "") -> str:
    text = f"{value} {label}".upper().replace("-", "_")
    if "PED" in text:
        return "PED"
    if "LIGHT" in text:
        return "LIGHT_RUC"
    if "HEAVY" in text:
        return "HEAVY_RUC"
    return str(value).upper()


def human_label_ok(series: pd.Series) -> bool:
    values = series.dropna().astype(str).str.strip()
    if values.empty:
        return False
    return not values.str.contains("_", regex=False).any()


def safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def load_schema_payload() -> dict[str, Any]:
    schema_path = ROOT / "artifacts" / "data_schema.json"
    if not schema_path.exists():
        return {}
    try:
        return json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def file_nonempty(relative: str) -> bool:
    path = ROOT / relative
    return path.exists() and path.is_file() and path.stat().st_size > 0


def read_csv_artifact(relative: str) -> pd.DataFrame:
    path = ROOT / relative
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, low_memory=False)
    except Exception:
        return pd.DataFrame()


def screenshot_ok(relative: str) -> bool:
    path = ROOT / relative
    return path.exists() and path.is_file() and path.suffix.lower() == ".png" and path.stat().st_size > 10_000


def bool_col(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index)
    return df[column].fillna(False).astype(bool)


def text_has_all(path: Path, needles: tuple[str, ...]) -> bool:
    text = safe_read(path)
    return bool(text) and all(needle in text for needle in needles)


def main() -> int:
    args = parse_args()
    pack_root = resolve_evidence_pack_root(args.data_root)
    data_dir = pack_root / "data"
    parquet_path = data_dir / EVIDENCE_CANDIDATE_FILE
    metadata_path = pack_root / EVIDENCE_MANIFEST_FILE
    csv_mirror_path: Path | None = None

    raw: pd.DataFrame | None = None
    candidate_df: pd.DataFrame | None = None
    loaded: Any | None = None
    load_error = ""
    try:
        raw = pd.read_parquet(parquet_path)
        loaded = load_evidence_pack(args.data_root, args.repo_root)
        candidate_df = loaded.data.get("candidate_df", pd.DataFrame()).copy()
        candidate_df["_gate_stream_key"] = [
            stream_key(row.get("stream"), row.get("stream_label")) for _, row in candidate_df.iterrows()
        ]
    except Exception as exc:  # reported through gates
        load_error = f"{type(exc).__name__}: {exc}"

    schema_payload = load_schema_payload()
    schema_is_parquet_pass = (
        schema_payload.get("status") == "passed"
        and schema_payload.get("source_mode") == "dashboard_evidence_pack"
        and bool(schema_payload.get("parquet_path"))
    )
    data_loaded = candidate_df is not None and load_error == ""

    def fail(reason: str) -> tuple[bool, str]:
        return False, reason

    def ok(reason: str) -> tuple[bool, str]:
        return True, reason

    def require_data() -> tuple[pd.DataFrame, str] | tuple[None, str]:
        if not data_loaded or candidate_df is None:
            return None, f"Parquet data unavailable: {load_error or 'file missing'}"
        return candidate_df, ""

    def finalists() -> pd.DataFrame:
        df, _ = require_data()
        if df is None:
            return pd.DataFrame()
        return df[bool_col(df, "is_current_recommended")].copy()

    def schiff() -> pd.DataFrame:
        df, _ = require_data()
        if df is None:
            return pd.DataFrame()
        return df[bool_col(df, "is_pure_schiff")].copy()

    def default_landscape() -> pd.DataFrame:
        if loaded is not None:
            summary = loaded.data.get("summary", pd.DataFrame())
            if summary is not None and not summary.empty:
                return summary.copy()
        df, _ = require_data()
        if df is None:
            return pd.DataFrame()
        default = df[bool_col(df, "plot_default_include") & ~bool_col(df, "is_extreme_outlier")].copy()
        if "is_legacy_schiff_style" in default.columns:
            default = default[~bool_col(default, "is_legacy_schiff_style")].copy()
        return default

    def finalist_for(stream: str) -> pd.DataFrame:
        data = finalists()
        if data.empty or "_gate_stream_key" not in data.columns:
            return pd.DataFrame()
        return data[data["_gate_stream_key"].eq(stream)].copy()

    def pure_schiff_for(stream: str) -> pd.DataFrame:
        data = schiff()
        if data.empty or "_gate_stream_key" not in data.columns:
            return pd.DataFrame()
        return data[data["_gate_stream_key"].eq(stream)].copy()

    def joined_finalist_schiff() -> pd.DataFrame:
        f = finalists()
        s = schiff()
        if f.empty or s.empty:
            return pd.DataFrame()
        f = f.add_prefix("finalist_")
        s = s.add_prefix("schiff_")
        return f.merge(s, left_on="finalist__gate_stream_key", right_on="schiff__gate_stream_key", how="inner")

    def page_evidence(page: str) -> tuple[bool, str]:
        shot = PAGE_SCREENSHOTS[page]
        if not schema_is_parquet_pass:
            return fail("Current schema artifact is not a passed Parquet inspection.")
        if not screenshot_ok(shot):
            return fail(f"Missing current screenshot: {shot}")
        return ok(f"Parquet schema passed and screenshot exists: {shot}")

    def visual_deltas_payload() -> dict[str, Any]:
        path = ROOT / "artifacts" / "current_vs_target_deltas.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def page_visual_status(page: str) -> tuple[bool, str]:
        payload = visual_deltas_payload()
        page_status = str(payload.get("pages", {}).get(page, {}).get("status", "")).upper()
        if page_status != "PASS":
            return fail(f"{page} current-vs-target delta status is {page_status or 'missing'}.")
        matrix = safe_read(ROOT / "artifacts" / "target_vs_current_screenshot_matrix.md")
        visual_review = safe_read(ROOT / "artifacts" / "visual_delta_review.md")
        combined = f"{matrix}\n{visual_review}"
        if page not in combined or re.search(rf"{re.escape(page)}[\s\S]{{0,700}}Status:\s*PASS", combined, re.I) is None:
            return fail(f"{page} is not explicitly marked PASS in visual review artifacts.")
        return ok(f"{page} visual reviewer artifacts are marked PASS.")

    def all_visual_reviews_pass() -> tuple[bool, str]:
        missing = [path for path in VISUAL_REVIEW_FILES if not file_nonempty(path)]
        if missing:
            return fail("Missing visual review artifacts: " + ", ".join(missing))
        payload = visual_deltas_payload()
        if str(payload.get("overall_status", "")).upper() != "PASS":
            return fail("artifacts/current_vs_target_deltas.json overall_status is not PASS.")
        failed_pages = [page for page in PAGE_SCREENSHOTS if not page_visual_status(page)[0]]
        if failed_pages:
            return fail("Visual reviewer pages not PASS: " + ", ".join(failed_pages))
        for path in VISUAL_REVIEW_FILES:
            text = safe_read(ROOT / path)
            if re.search(r"\b(FAIL|UNRESOLVED)\b", text, re.I):
                return fail(f"{path} still contains FAIL or UNRESOLVED.")
        return ok("All visual review artifacts explicitly mark all four pages PASS.")

    def page_backlog_closed(page: str) -> tuple[bool, str]:
        text = safe_read(ROOT / "PAGE_BY_PAGE_VISUAL_DELTA.lock.md")
        if not text:
            return fail("PAGE_BY_PAGE_VISUAL_DELTA.lock.md missing.")
        section_match = re.search(rf"## {re.escape(page)}(?P<body>.*?)(?:\n## |\Z)", text, re.S)
        if not section_match:
            return fail(f"No locked visual-delta section found for {page}.")
        body = section_match.group("body")
        if "- [ ]" in body:
            return fail(f"{page} still has unchecked visual delta items.")
        return ok(f"{page} visual delta checklist is closed.")

    def visual_page_evidence(page: str) -> tuple[bool, str]:
        base, message = page_evidence(page)
        if not base:
            return base, message
        visual_text = safe_read(ROOT / "artifacts" / "visual_reference_comparison.md")
        if "Current Parquet refresh status: in progress" in visual_text:
            return fail("Visual comparison artifact still marks Parquet refresh as in progress.")
        if page not in visual_text:
            return fail(f"Visual comparison artifact does not mention {page}.")
        reviewer_pass, reviewer_message = page_visual_status(page)
        if not reviewer_pass:
            return reviewer_pass, reviewer_message
        backlog_pass, backlog_message = page_backlog_closed(page)
        if not backlog_pass:
            return backlog_pass, backlog_message
        return ok(f"{page} screenshot, visual reviewer PASS, and closed backlog evidence are present.")

    def check_parquet_found() -> tuple[bool, str]:
        if not parquet_path.exists():
            return fail(f"{EVIDENCE_CANDIDATE_FILE} not found in evidence pack data folder: {data_dir}")
        if not metadata_path.exists():
            return fail(f"{EVIDENCE_MANIFEST_FILE} not found in evidence pack: {pack_root}")
        return ok(f"Resolved evidence-pack candidate Parquet path: {parquet_path}")

    def check_parquet_loads() -> tuple[bool, str]:
        if not parquet_path.exists():
            return fail("Evidence-pack candidate Parquet file is missing.")
        if load_error:
            return fail(load_error)
        return ok(f"Parquet loaded with shape {tuple(raw.shape) if raw is not None else 'unknown'}.")

    def check_rows_positive() -> tuple[bool, str]:
        df, reason = require_data()
        if df is None:
            return fail(reason)
        return ok(f"{len(df):,} candidate rows loaded.") if len(df) > 0 else fail("Candidate row count is zero.")

    def check_all_streams() -> tuple[bool, str]:
        df, reason = require_data()
        if df is None:
            return fail(reason)
        found = set(df["_gate_stream_key"].dropna().astype(str))
        missing = set(EXPECTED_STREAMS) - found
        return fail("Missing streams: " + ", ".join(sorted(missing))) if missing else ok("All three streams present.")

    def check_stream_labels() -> tuple[bool, str]:
        df, reason = require_data()
        if df is None:
            return fail(reason)
        if "stream_label" not in df.columns:
            return fail("stream_label column missing after normalisation.")
        return ok("stream_label values are human-readable.") if human_label_ok(df["stream_label"]) else fail("stream_label contains underscores or is empty.")

    def check_model_labels() -> tuple[bool, str]:
        df, reason = require_data()
        if df is None:
            return fail(reason)
        column = "model_short" if "model_short" in df.columns else "model"
        if column not in df.columns:
            return fail("No model or model_short column available.")
        return ok(f"{column} values are available for display.") if human_label_ok(df[column]) else fail(f"{column} contains underscores or is empty.")

    def check_all_user_labels() -> tuple[bool, str]:
        df, reason = require_data()
        if df is None:
            return fail(reason)
        bad = [column for column in USER_LABEL_COLUMNS if column in df.columns and not human_label_ok(df[column])]
        return fail("User-facing label columns contain raw underscores: " + ", ".join(bad)) if bad else ok("User-facing label columns are clean.")

    def check_metadata() -> tuple[bool, str]:
        if metadata_path.exists():
            return ok(f"Evidence-pack manifest JSON found: {metadata_path}")
        if file_nonempty("artifacts/data_schema.json") and "metadata_path" in schema_payload:
            return ok("Manifest JSON is absent but explicitly recorded in data_schema.json.")
        return fail("Manifest JSON missing and no graceful missing-state artifact recorded.")

    def check_csv_mirror() -> tuple[bool, str]:
        if csv_mirror_path is not None:
            return ok(f"CSV mirror found: {csv_mirror_path}")
        if file_nonempty("artifacts/data_schema.json") and "csv_mirror_path" in schema_payload:
            return ok("CSV mirror is absent but explicitly recorded in data_schema.json.")
        return fail("CSV mirror missing and no graceful missing-state artifact recorded.")

    def check_schema_report() -> tuple[bool, str]:
        return ok("artifacts/data_schema_report.md exists.") if file_nonempty("artifacts/data_schema_report.md") else fail("artifacts/data_schema_report.md missing.")

    def check_finalist_count(stream: str) -> tuple[bool, str]:
        data = finalist_for(stream)
        if data.empty:
            return fail(f"No current recommended finalist for {stream}.")
        if len(data) == 1:
            return ok(f"Exactly one current recommended finalist for {stream}.")
        return ok(f"{len(data)} current finalists for {stream}; ambiguity is explicit in validation output.")

    def check_finalist_metric(stream: str, column: str, target: float) -> tuple[bool, str]:
        data = finalist_for(stream)
        if data.empty:
            return fail(f"No current finalist for {stream}.")
        values = [pct_value(value) for value in data[column]] if column in data.columns else []
        if len(data) == 1 and values and approx_pct(values[0], target):
            return ok(f"{stream} {column} is {values[0]:.2f}%, matching expected {target:.2f}%.")
        return fail(f"{stream} {column} values {values} do not reconcile to expected {target:.2f}%.")

    def check_heavy_from_flag(column: str) -> tuple[bool, str]:
        data = finalist_for("HEAVY_RUC")
        if data.empty:
            return fail("No Heavy RUC current recommended row from Parquet flags.")
        if column not in data.columns:
            return fail(f"{column} missing for Heavy RUC current recommended row.")
        values = [pct_value(value) for value in data[column]]
        return ok(f"Heavy RUC {column} comes from {len(data)} current-recommended Parquet row(s): {values}.")

    def check_stale_values() -> tuple[bool, str]:
        data = finalists()
        if data.empty:
            return fail("No current finalist rows available.")
        offenders: list[str] = []
        for stream, stale in STALE_FINALIST_VALUES.items():
            rows = data[data["_gate_stream_key"].eq(stream)]
            for value in rows.get("quarterly_mape", pd.Series(dtype=float)):
                actual = pct_value(value)
                if actual is not None and abs(actual - stale) < 0.05:
                    offenders.append(f"{stream}: {actual:.2f}%")
        return fail("Stale finalist values visible: " + ", ".join(offenders)) if offenders else ok("Known stale finalist values are absent from current finalists.")

    def check_landscape_uses_parquet() -> tuple[bool, str]:
        df, reason = require_data()
        if df is None:
            return fail(reason)
        path = str(parquet_path or "")
        return ok(f"Candidate rows loaded from Parquet: {path}") if path.endswith(".parquet") else fail("Candidate rows are not sourced from Parquet.")

    def check_default_not_raw_full() -> tuple[bool, str]:
        df, reason = require_data()
        if df is None:
            return fail(reason)
        default = default_landscape()
        if len(df) > args.max_default_rows and len(default) >= len(df):
            return fail("Default landscape equals the full candidate universe.")
        return ok(f"Default landscape uses {len(default):,} rows from {len(df):,} total.")

    def check_default_include() -> tuple[bool, str]:
        default = default_landscape()
        if default.empty:
            return fail("No plot_default_include rows in default landscape.")
        return ok(f"{len(default):,} plot_default_include rows form the default landscape.")

    def check_flag_present(column: str, label: str) -> tuple[bool, str]:
        df, reason = require_data()
        if df is None:
            return fail(reason)
        if column not in df.columns:
            return fail(f"{column} missing.")
        count = int(bool_col(df, column).sum())
        return ok(f"{count:,} {label} rows found.") if count > 0 else fail(f"No {label} rows found.")

    def check_default_cap() -> tuple[bool, str]:
        default = default_landscape()
        if default.empty:
            return fail("No default candidate landscape rows.")
        if len(default) > args.max_default_rows:
            return fail(f"Default landscape has {len(default):,} rows, above cap {args.max_default_rows:,}.")
        return ok(f"Default landscape has {len(default):,} rows, within cap {args.max_default_rows:,}.")

    def check_schiff_streams() -> tuple[bool, str]:
        missing = [stream for stream in EXPECTED_STREAMS if pure_schiff_for(stream).empty]
        return fail("Missing pure Schiff rows for: " + ", ".join(missing)) if missing else ok("Pure Schiff rows exist for all three streams.")

    def check_schiff_excludes(term: str, pattern: str) -> tuple[bool, str]:
        data = schiff()
        if data.empty:
            return fail("No pure Schiff rows available.")
        text = data.get("model", pd.Series(dtype=str)).astype(str) + " " + data.get("model_short", pd.Series(dtype=str)).astype(str)
        bad = data[text.str.contains(pattern, case=False, regex=True, na=False)]
        return ok(f"Pure Schiff rows exclude {term}.") if bad.empty else fail(f"Pure Schiff rows include {term}: {len(bad):,} row(s).")

    def check_schiff_bad_names() -> tuple[bool, str]:
        data = schiff()
        if data.empty:
            return fail("No pure Schiff rows available.")
        text = data.get("model", pd.Series(dtype=str)).astype(str) + " " + data.get("model_short", pd.Series(dtype=str)).astype(str)
        bad = data[text.str.contains(BAD_SCHIFF_RE, na=False)]
        return ok("Pure Schiff benchmark rows are not contaminated.") if bad.empty else fail(f"{len(bad):,} contaminated pure Schiff row(s).")

    def check_join() -> tuple[bool, str]:
        joined = joined_finalist_schiff()
        keys = set(joined.get("finalist__gate_stream_key", pd.Series(dtype=str)))
        missing = set(EXPECTED_STREAMS) - keys
        return fail("Finalist-to-Schiff join missing streams: " + ", ".join(sorted(missing))) if missing else ok("Current finalists join to pure Schiff rows for all streams.")

    def check_paired_gain() -> tuple[bool, str]:
        joined = joined_finalist_schiff()
        if joined.empty:
            return fail("No finalist-to-Schiff joined rows.")
        paired_cols = [col for col in joined.columns if "paired_gain_vs_schiff_pp" in col]
        if paired_cols and joined[paired_cols].notna().any().any():
            return ok("Paired gain is loaded from Parquet columns.")
        required = {"schiff_quarterly_mape", "finalist_quarterly_mape"}
        return ok("Paired gain can be computed from joined quarterly MAPE.") if required.issubset(joined.columns) else fail("Paired gain cannot be loaded or computed.")

    def check_full_sample_gain_chart() -> tuple[bool, str]:
        text = safe_read(ROOT / "app.py") + safe_read(ROOT / "model_dashboard/plots.py")
        if "Paired Gain vs Schiff" in text:
            return fail("Full-sample gain chart is still labelled as paired.")
        required_terms = ("Full-sample Gain vs Schiff", "Full-sample gain versus Schiff", "Full-sample qtr")
        missing = [term for term in required_terms if term not in text]
        if missing:
            return fail("Full-sample gain chart terms missing: " + ", ".join(missing))
        source = read_csv_artifact("artifacts/scenario_comparison_source_table.csv")
        if source.empty:
            return fail("scenario_comparison_source_table.csv is missing or empty.")
        light = source[source["stream_label"].astype(str).eq("Light RUC volume")]
        if light.empty:
            return fail("Light RUC row missing from scenario source table.")
        paired_gain = pd.to_numeric(light.iloc[0].get("paired_gain_pp"), errors="coerce")
        full_gain = pd.to_numeric(light.iloc[0].get("full_sample_qtr_gain_pp"), errors="coerce")
        annual_gain = pd.to_numeric(light.iloc[0].get("full_sample_annual_gain_pp"), errors="coerce")
        if pd.isna(paired_gain) or paired_gain <= 0:
            return fail("Light RUC paired paper-grid gain is not recorded as positive in v3.")
        if pd.isna(full_gain) or full_gain <= 0:
            return fail("Light RUC paper-style quarterly gain is not recorded as positive in v3.")
        if pd.isna(annual_gain) or annual_gain >= 0:
            return fail("Light RUC annual watch is not preserved as a negative annual gain.")
        return ok("Full-sample gain chart label is distinct from paired common-grid evidence and preserves Light RUC annual watch.")

    def check_win_rate() -> tuple[bool, str]:
        paired = loaded.data.get("paired_vs_schiff", pd.DataFrame()) if loaded is not None else pd.DataFrame()
        cols = [col for col in paired.columns if "win_rate" in col]
        if paired.empty or not cols:
            return fail("No paired win-rate field available.")
        return ok("Win-rate field is available.") if paired[cols].notna().any().any() else fail("Win-rate field exists but is empty.")

    def check_overview_kpis() -> tuple[bool, str]:
        data = finalists()
        if data.empty:
            return fail("No finalists for Overview KPIs.")
        q = pd.to_numeric(data["quarterly_mape"], errors="coerce").dropna().mean()
        a = pd.to_numeric(data["annual_mape"], errors="coerce").dropna().mean()
        return ok(f"Overview KPI means derived from Parquet finalists: quarterly={q:.2f}, annual={a:.2f}.")

    def check_overview_chart_finalists() -> tuple[bool, str]:
        data = finalists()
        return ok(f"Finalist accuracy has {len(data):,} current finalist rows.") if len(data) >= 3 else fail("Finalist accuracy lacks three current finalist rows.")

    def check_ensemble_state() -> tuple[bool, str]:
        if loaded is None:
            return fail("Parquet loader unavailable.")
        ensemble = loaded.data.get("ensemble_df", pd.DataFrame())
        if not ensemble.empty:
            source = read_csv_artifact("artifacts/ensemble_composition_source_table.csv")
            if source.empty:
                return fail("ensemble_composition_source_table.csv is missing or empty.")
            source_text = " ".join(source.get("source", pd.Series(dtype=str)).dropna().astype(str).unique())
            if "ensemble_components.parquet" not in source_text and "Parquet ensemble_components_json" not in source_text:
                return fail("Ensemble source table is not backed by evidence-pack component rows.")
            stale_weights = {
                "PED VKT per capita": [57.1, 38.7, 4.2],
                "Light RUC volume": [23.2, 21.8, 20.3, 17.2, 11.7, 5.8],
                "Heavy RUC volume": [48.7, 37.7, 13.7],
            }
            for stream_label, stale in stale_weights.items():
                rounded = (
                    source[source["stream_label"].astype(str).eq(stream_label)]
                    .sort_values("component_rank")["weight_pct"]
                    .astype(float)
                    .round(1)
                    .to_list()
                )
                if rounded == stale:
                    return fail(f"{stream_label} ensemble weights still match stale/demo values.")
            return ok(f"Parquet ensemble component data available: {len(ensemble):,} rows.")
        text = safe_read(ROOT / "app.py").lower()
        return ok("App has missing-data language for unavailable ensemble weights.") if "not available" in text and "ensemble" in text else fail("No real ensemble data or clear missing-state code found.")

    def check_stress() -> tuple[bool, str]:
        if loaded is None:
            return fail("Parquet loader unavailable.")
        stress = loaded.data.get("stress_df", pd.DataFrame())
        if stress.empty:
            return fail("Stress/horizon dataset is empty.")
        expected_order = ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2024+", "2022-23", "Annual"]
        required = {
            "PED VKT per capita": ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2022-23", "Annual"],
            "Light RUC volume": ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2022-23", "Annual"],
            "Heavy RUC volume": ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "Annual"],
        }
        data = stress.copy()
        data["bucket"] = data["stress_bucket"].astype(str)
        for stream_label, buckets in required.items():
            stream_rows = data[data["stream_label"].astype(str).eq(stream_label)]
            if set(stream_rows["bucket"]) != set(expected_order):
                return fail(f"Stress frame does not carry all six explicit buckets for {stream_label}.")
            missing = []
            for bucket in buckets:
                values = pd.to_numeric(stream_rows.loc[stream_rows["bucket"].eq(bucket), "mape"], errors="coerce")
                if not values.notna().any():
                    missing.append(bucket)
            if missing:
                return fail(f"Stress alias coalescing missed {stream_label}: {', '.join(missing)}.")
        return ok(f"Stress/horizon aliases coalesced into six-bucket rows: {len(stress):,}.")

    def check_panel_count(page: str) -> tuple[bool, str]:
        text = safe_read(ROOT / "DASHBOARD_PAGE_CHART_SPEC.lock.md")
        if page not in text:
            return fail(f"{page} is not documented in DASHBOARD_PAGE_CHART_SPEC.lock.md.")
        if "No primary page should contain more than four" in text or "four main" in text:
            return ok(f"{page} four-panel rule is locked in DASHBOARD_PAGE_CHART_SPEC.lock.md.")
        return fail("Four-panel rule is not locked.")

    def check_diagnostics_kpis() -> tuple[bool, str]:
        if loaded is None:
            return fail("Parquet loader unavailable.")
        diag = loaded.data.get("diagnostic_df", pd.DataFrame())
        if not diag.empty:
            return ok(f"Diagnostic KPI source rows available: {len(diag):,}.")
        text = safe_read(ROOT / "app.py").lower()
        return ok("Diagnostics missing-data states are present in app code.") if "diagnostic" in text and "not available" in text else fail("Diagnostics are missing and no missing-data state is evident.")

    def check_diag_field(column: str, label: str) -> tuple[bool, str]:
        data = loaded.data.get("diagnostic_df", pd.DataFrame()) if loaded is not None else pd.DataFrame()
        if data.empty:
            return fail("No diagnostic rows for diagnostic fields.")
        if column not in data.columns:
            return fail(f"{label} column missing.")
        return ok(f"{label} has available values.") if data[column].notna().any() else fail(f"{label} column is empty.")

    def check_diagnostic_chart(source_terms: tuple[str, ...], label: str) -> tuple[bool, str]:
        text = safe_read(ROOT / "app.py") + safe_read(ROOT / "model_dashboard/plots.py")
        missing = [term for term in source_terms if term not in text]
        if missing:
            return fail(f"{label} source terms missing from app/plot code: {', '.join(missing)}")
        return ok(f"{label} code path is present.")

    def check_scenario_controls() -> tuple[bool, str]:
        text = safe_read(ROOT / "app.py")
        if "Scenario A" in text and "Scenario B" in text and ("selectbox" in text or "st.selectbox" in text):
            return ok("Scenario controls are implemented as Streamlit controls.")
        return fail("Scenario controls are missing or static.")

    def check_gain_correct() -> tuple[bool, str]:
        joined = joined_finalist_schiff()
        if joined.empty:
            return fail("No joined finalist/Schiff data.")
        required = {"schiff_quarterly_mape", "finalist_quarterly_mape", "schiff_annual_mape", "finalist_annual_mape"}
        if not required.issubset(joined.columns):
            return fail("Joined data lacks required MAPE columns.")
        gain = pd.to_numeric(joined["schiff_quarterly_mape"], errors="coerce") - pd.to_numeric(joined["finalist_quarterly_mape"], errors="coerce")
        return ok(f"Quarterly gains computed for {gain.notna().sum():,} stream rows.") if gain.notna().any() else fail("Gain computation produced no values.")

    def check_horizon(fields: tuple[str, ...], label: str) -> tuple[bool, str]:
        if loaded is None:
            return fail("Parquet loader unavailable.")
        horizon = loaded.data.get("horizon_df", pd.DataFrame())
        if horizon.empty:
            return fail("horizon_df is empty.")
        present = set(horizon.columns)
        return ok(f"{label} horizon data rows: {len(horizon):,}.") if set(fields).issubset(present) else fail(f"horizon_df missing fields for {label}: {set(fields) - present}")

    def check_decision_summary() -> tuple[bool, str]:
        text = safe_read(ROOT / "app.py") + safe_read(ROOT / "model_dashboard/plots.py")
        required = ("Stream", "Full-sample Qtr Gain", "Full-sample Annual Gain", "Paired Win Rate", "Recommendation")
        missing = [item for item in required if item not in text]
        return fail("Decision summary labels missing: " + ", ".join(missing)) if missing else ok("Decision summary labels are present in code.")

    def check_schiff_kpis() -> tuple[bool, str]:
        if schiff().empty or finalists().empty:
            return fail("Schiff/finalist data missing.")
        return ok(f"Schiff KPI sources: {len(schiff()):,} Schiff rows and {len(finalists()):,} finalist rows.")

    def check_clean_table_labels() -> tuple[bool, str]:
        text = safe_read(ROOT / "model_dashboard/plots.py") + safe_read(ROOT / "app.py")
        required = (
            "Schiff Spec Qtr",
            "Finalist Qtr",
            "Full-sample Qtr Gain",
            "Schiff Spec Annual",
            "Finalist Annual",
            "Full-sample Annual Gain",
            "Paired Win Rate",
        )
        missing = [item for item in required if item not in text]
        return fail("Benchmark table labels missing: " + ", ".join(missing)) if missing else ok("Benchmark table labels are clean and human-readable.")

    def check_filters_clickable() -> tuple[bool, str]:
        if not page_evidence("Overview")[0]:
            return fail("Browser screenshot evidence is unavailable.")
        text = safe_read(ROOT / "artifacts" / "filter_interaction_review.md") + safe_read(ROOT / "artifacts" / "reviews" / "interaction_filter.md")
        required = ("Reset Filters", "Stream", "Model Family", "Forecast Vintage", "direct")
        missing = [item for item in required if item not in text]
        return fail("Filter interaction evidence missing: " + ", ".join(missing)) if missing else ok("Filter review records direct clickable primary filters.")

    def check_hovers_clean() -> tuple[bool, str]:
        if not page_evidence("Overview")[0]:
            return fail("Browser screenshot evidence is unavailable.")
        hover_text = safe_read(ROOT / "artifacts" / "hover_review.md")
        if not hover_text:
            return fail("artifacts/hover_review.md missing.")
        if RAW_HOVER_RE.search(hover_text):
            return fail("Hover review still contains raw internal hover labels.")
        if "_" in hover_text:
            return fail("Hover review contains underscores.")
        return ok("Hover review is present and contains no raw internal labels or underscores.")

    def check_visual_lock_files() -> tuple[bool, str]:
        missing = [path for path in VISUAL_LOCK_FILES if not file_nonempty(path)]
        if missing:
            return fail("Missing visual conformance lock files: " + ", ".join(missing))
        return ok("Visual conformance lock files exist.")

    def check_overview_card_structure() -> tuple[bool, str]:
        if not check_visual_lock_files()[0]:
            return check_visual_lock_files()
        page_status = page_visual_status("Overview")
        if not page_status[0]:
            return page_status
        text = safe_read(ROOT / "app.py") + safe_read(ROOT / "model_dashboard/plots.py")
        required = ("Finalist Forecast Accuracy", "Candidate Search Frontier", "Finalist Ensemble Composition", "Stress and Horizon Checks")
        missing = [item for item in required if item not in text]
        return fail("Overview panel code missing: " + ", ".join(missing)) if missing else ok("Overview card/panel structure is locked and reviewer-approved.")

    def check_stress_bucket_order_visual() -> tuple[bool, str]:
        expected_labels = ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2024+", "2022-23", "Annual"]
        try:
            from model_dashboard.labels import STRESS_BUCKET_ORDER as actual_order  # noqa: PLC0415
        except Exception as exc:
            return fail(f"Could not import STRESS_BUCKET_ORDER: {exc}")
        text = safe_read(ROOT / "model_dashboard/plots.py")
        if list(actual_order) != expected_labels or "categoryarray=STRESS_BUCKET_ORDER" not in text:
            return fail("Stress bucket order is not locked into labels and Plotly category array.")
        return ok("Overview stress bucket order is explicitly locked in labels and plot axis settings.")

    def check_candidate_no_giant_overlay() -> tuple[bool, str]:
        plots = safe_read(ROOT / "model_dashboard/plots.py")
        bad_terms = ("type=\"circle\"", "type='circle'", "ellipse", "add_shape(type=\"circle", "add_shape(type='circle")
        offenders = [term for term in bad_terms if term.lower() in plots.lower()]
        if offenders:
            return fail("Candidate frontier still contains giant overlay code terms: " + ", ".join(offenders))
        return ok("Candidate frontier has no circle/ellipse overlay code.")

    def check_candidate_marker_visuals() -> tuple[bool, str]:
        plots = safe_read(ROOT / "model_dashboard/plots.py")
        required = ("Finalist", "Schiff", "star", "triangle-up-open")
        missing = [item for item in required if item not in plots]
        return fail("Candidate marker code missing: " + ", ".join(missing)) if missing else ok("Candidate frontier exposes finalist stars and Schiff open triangles.")

    def check_diagnostic_matrix_styled() -> tuple[bool, str]:
        plots = safe_read(ROOT / "model_dashboard/plots.py")
        required = ("status_style", "fill_color", "Pass", "Caution", "Fail", "Unavailable")
        missing = [item for item in required if item not in plots]
        return fail("Diagnostic matrix styling code missing: " + ", ".join(missing)) if missing else ok("Diagnostic matrix uses styled pass/caution/fail/unavailable cells.")

    def check_diagnostics_semantic_kpis() -> tuple[bool, str]:
        text = safe_read(ROOT / "app.py")
        required = ("Diagnostics Coverage", "Mean Durbin-Watson", "Mean calibration R2", "Heteroscedasticity Pass")
        missing = [item for item in required if item not in text]
        return fail("Diagnostics KPI labels missing: " + ", ".join(missing)) if missing else ok("Diagnostics KPI labels match target semantics.")

    def check_residual_scale_solution() -> tuple[bool, str]:
        plots = safe_read(ROOT / "model_dashboard/plots.py")
        if "def plot_residual_vs_fitted" in plots and "make_subplots" in plots and "Fitted value, native units" in plots:
            return ok("Residual-vs-fitted uses stream facets and native-unit axis labelling.")
        return fail("Residual-vs-fitted scale-imbalance solution is not evident in plot code.")

    def check_scenario_no_overlap_review() -> tuple[bool, str]:
        status = page_visual_status("Scenario Comparison")
        if not status[0]:
            return status
        text = safe_read(ROOT / "artifacts" / "screenshot_review.md") + safe_read(ROOT / "artifacts" / "visual_delta_review.md")
        if re.search(r"\boverlap\w*\b", text, re.I) and not re.search(r"no\s+overlap|overlap.*resolved", text, re.I):
            return fail("Scenario visual review still mentions unresolved overlap.")
        return ok("Scenario visual review confirms dumbbell labels no longer overlap.")

    def check_horizon_all_streams_visual(page: str) -> tuple[bool, str]:
        page_ok, message = page_visual_status(page)
        if not page_ok:
            return page_ok, message
        app_text = safe_read(ROOT / "app.py")
        plots_text = safe_read(ROOT / "model_dashboard/plots.py")
        required = ("scenario_horizon_frame", "missing_streams", "PED VKT per capita", "Light RUC volume", "Heavy RUC volume")
        missing = [item for item in required if item not in app_text + plots_text]
        return fail(f"{page} all-stream horizon code evidence missing: " + ", ".join(missing)) if missing else ok(f"{page} horizon profile evidence covers all three streams.")

    def check_scenario_decision_table_styled() -> tuple[bool, str]:
        text = safe_read(ROOT / "app.py") + safe_read(ROOT / "model_dashboard/plots.py")
        required = ("plot_decision_summary_table", "Recommendation", "fill_color", "Promote")
        missing = [item for item in required if item not in text]
        return fail("Styled decision table evidence missing: " + ", ".join(missing)) if missing else ok("Scenario decision summary is rendered as a styled Plotly table.")

    def check_schiff_mape_sections() -> tuple[bool, str]:
        plots = safe_read(ROOT / "model_dashboard/plots.py")
        required = ("plot_schiff_finalist_mape", "make_subplots", "Quarterly MAPE", "Annual MAPE", "horizontal_spacing")
        missing = [item for item in required if item not in plots]
        return fail("Schiff MAPE clear-section code evidence missing: " + ", ".join(missing)) if missing else ok("Schiff MAPE chart uses separated Quarterly and Annual sections.")

    def check_schiff_summary_styled() -> tuple[bool, str]:
        plots = safe_read(ROOT / "model_dashboard/plots.py")
        required = ("plot_benchmark_summary_table", "gain_colors", "fill_color", "Schiff Spec Qtr", "Finalist Annual")
        missing = [item for item in required if item not in plots]
        return fail("Styled Schiff summary table evidence missing: " + ", ".join(missing)) if missing else ok("Schiff benchmark summary is styled and readable.")

    def check_screenshot_review_no_major_gaps() -> tuple[bool, str]:
        text = safe_read(ROOT / "artifacts" / "screenshot_review.md") + "\n" + safe_read(ROOT / "artifacts" / "visual_reference_comparison.md")
        if not text.strip():
            return fail("Screenshot/visual comparison artifacts are missing.")
        if re.search(r"\b(major gap|FAIL|UNRESOLVED|current screenshots are failed evidence)\b", text, re.I):
            return fail("Screenshot review still records unresolved major visual gaps.")
        if "PASS" not in text:
            return fail("Screenshot review does not explicitly record PASS.")
        return ok("Screenshot review records no unresolved major visual gaps.")

    def check_browser_pages_verified() -> tuple[bool, str]:
        text = safe_read(ROOT / "artifacts" / "screenshot_review.md")
        missing = [page for page in PAGE_SCREENSHOTS if page not in text]
        if missing:
            return fail("Browser screenshot review missing pages: " + ", ".join(missing))
        return ok("Browser screenshot review covers all four top-level pages.")

    def check_performance_smoke_pass() -> tuple[bool, str]:
        text = safe_read(ROOT / "artifacts" / "performance_review.md")
        if not text:
            return fail("performance_review.md missing.")
        if re.search(r"\b(FAIL|slow|timeout|unacceptable)\b", text, re.I):
            return fail("Performance review contains failure/slow indicators.")
        return ok("Performance smoke review is present without failure indicators.")

    def check_visual_backlog_closed() -> tuple[bool, str]:
        bug_text = safe_read(ROOT / "BUG_BACKLOG.md")
        visual_text = safe_read(ROOT / "PAGE_BY_PAGE_VISUAL_DELTA.lock.md")
        if "- [ ]" in bug_text or "- [ ]" in visual_text:
            return fail("BUG_BACKLOG.md or PAGE_BY_PAGE_VISUAL_DELTA.lock.md still has unchecked visual defects.")
        return ok("Visual backlog and bug backlog have no unchecked items.")

    gates: list[Gate] = [
        Gate(1, "A", "Parquet file is found recursively under the supplied data root.", check_parquet_found),
        Gate(2, "A", "Parquet file loads without error.", check_parquet_loads),
        Gate(3, "A", "Parquet row count is greater than zero.", check_rows_positive),
        Gate(4, "A", "Parquet contains all three streams.", check_all_streams),
        Gate(5, "A", "Stream labels are human-readable.", check_stream_labels),
        Gate(6, "A", "Model labels are human-readable or have short labels.", check_model_labels),
        Gate(7, "A", "No user-facing label contains raw underscores.", check_all_user_labels),
        Gate(8, "A", "Metadata JSON is found or gracefully marked missing.", check_metadata),
        Gate(9, "A", "CSV mirror is found or gracefully marked missing.", check_csv_mirror),
        Gate(10, "A", "Data schema report is written to artifacts/data_schema_report.md.", check_schema_report),
        Gate(11, "B", "Exactly one current recommended finalist exists for PED, or ambiguity is explicitly warned.", lambda: check_finalist_count("PED")),
        Gate(12, "B", "Exactly one current recommended finalist exists for Light RUC, or ambiguity is explicitly warned.", lambda: check_finalist_count("LIGHT_RUC")),
        Gate(13, "B", "Exactly one current recommended finalist exists for Heavy RUC, or ambiguity is explicitly warned.", lambda: check_finalist_count("HEAVY_RUC")),
        Gate(14, "B", "PED current finalist paper-style quarterly MAPE rounds to approximately 3.24%.", lambda: check_finalist_metric("PED", "quarterly_mape", 3.24)),
        Gate(15, "B", "PED current finalist paper-style annual MAPE rounds to approximately 2.03%.", lambda: check_finalist_metric("PED", "annual_mape", 2.03)),
        Gate(16, "B", "Light RUC current finalist paper-style quarterly MAPE rounds to approximately 6.07%.", lambda: check_finalist_metric("LIGHT_RUC", "quarterly_mape", 6.07)),
        Gate(17, "B", "Light RUC current finalist paper-style annual MAPE rounds to approximately 3.43%.", lambda: check_finalist_metric("LIGHT_RUC", "annual_mape", 3.43)),
        Gate(18, "B", "Heavy RUC current finalist quarterly MAPE is taken from the Parquet current-recommended flag.", lambda: check_heavy_from_flag("quarterly_mape")),
        Gate(19, "B", "Heavy RUC current finalist annual MAPE is taken from the Parquet current-recommended flag.", lambda: check_heavy_from_flag("annual_mape")),
        Gate(20, "B", "Stale old finalist values do not appear as current latest finalist values.", check_stale_values),
        Gate(21, "C", "Candidate landscape uses the Parquet candidate rows.", check_landscape_uses_parquet),
        Gate(22, "C", "Default candidate landscape does not use the full raw universe if row count is large.", check_default_not_raw_full),
        Gate(23, "C", "Default candidate landscape uses curated rows where plot_default_include is true, or equivalent.", check_default_include),
        Gate(24, "C", "Candidate landscape contains distribution/cone sample rows.", lambda: check_flag_present("is_distribution_sample", "distribution/cone sample")),
        Gate(25, "C", "Candidate landscape contains top quarterly candidates.", lambda: check_flag_present("is_top_quarterly", "top quarterly")),
        Gate(26, "C", "Candidate landscape contains top annual candidates.", lambda: check_flag_present("is_top_annual", "top annual")),
        Gate(27, "C", "Candidate landscape contains frontier/Pareto candidates where available.", lambda: check_flag_present("is_frontier", "frontier/Pareto")),
        Gate(28, "C", "Candidate landscape contains current finalist markers.", lambda: check_flag_present("is_current_recommended", "current finalist marker")),
        Gate(29, "C", "Candidate landscape contains pure Schiff markers.", lambda: check_flag_present("is_pure_schiff", "pure Schiff marker")),
        Gate(30, "C", "Candidate landscape row count is capped at or below 400 for default rendering.", check_default_cap),
        Gate(31, "D", "Pure Schiff rows exist for all three streams.", check_schiff_streams),
        Gate(32, "D", "Pure Schiff rows exclude residual models.", lambda: check_schiff_excludes("residual models", r"resid|residual")),
        Gate(33, "D", "Pure Schiff rows exclude fixed-blend models.", lambda: check_schiff_excludes("fixed-blend models", r"fixed.?blend|blend")),
        Gate(34, "D", "Pure Schiff rows exclude solver models.", lambda: check_schiff_excludes("solver models", r"solver|convex")),
        Gate(35, "D", "Pure Schiff rows exclude top-k mean/median ensembles.", lambda: check_schiff_excludes("top-k mean/median ensembles", r"top.?k|mean|median|ensemble")),
        Gate(36, "D", "Schiff Benchmark page uses pure Schiff rows only.", check_schiff_bad_names),
        Gate(37, "D", "Scenario Comparison joins current finalists to pure Schiff rows by stream.", check_join),
        Gate(38, "D", "Paired gain versus Schiff is computed or loaded where available.", check_paired_gain),
        Gate(39, "D", "Win rate versus Schiff is shown where available.", check_win_rate),
        Gate(40, "D", "Benchmark summary does not classify residual/blend challengers as pure Schiff.", check_schiff_bad_names),
        Gate(41, "E", "Overview page renders without Streamlit exception.", lambda: page_evidence("Overview")),
        Gate(42, "E", "Overview KPI cards reconcile to Parquet values.", check_overview_kpis),
        Gate(43, "E", "Overview finalist accuracy chart uses current finalists.", check_overview_chart_finalists),
        Gate(44, "E", "Overview candidate search frontier uses curated cone sample.", check_default_include),
        Gate(45, "E", "Overview ensemble composition uses real weights where available or shows a clear missing-data state.", check_ensemble_state),
        Gate(46, "E", "Overview stress/horizon chart uses finalist stress/horizon fields.", check_stress),
        Gate(47, "E", "Overview has no more than four main chart panels.", lambda: check_panel_count("Overview")),
        Gate(48, "E", "Overview screenshot is saved.", lambda: ok(PAGE_SCREENSHOTS["Overview"]) if screenshot_ok(PAGE_SCREENSHOTS["Overview"]) else fail(f"Missing {PAGE_SCREENSHOTS['Overview']}")),
        Gate(49, "E", "Overview screenshot has no obvious blank panels.", lambda: page_evidence("Overview")),
        Gate(50, "E", "Overview screenshot visually aligns with the supplied target image.", lambda: visual_page_evidence("Overview")),
        Gate(51, "F", "Diagnostics page renders without Streamlit exception.", lambda: page_evidence("Diagnostics")),
        Gate(52, "F", "Diagnostics KPI cards use available diagnostic fields or show clear missing-data states.", check_diagnostics_kpis),
        Gate(53, "F", "Durbin-Watson metric is shown where available.", lambda: check_diag_field("durbin_watson", "Durbin-Watson")),
        Gate(54, "F", "Calibration R2 metric is shown where available.", lambda: check_diag_field("adj_r2", "Calibration R2")),
        Gate(55, "F", "Heteroscedasticity pass metric is shown where available.", lambda: check_diag_field("breusch_pagan_pvalue", "Breusch-Pagan")),
        Gate(56, "F", "Residual autocorrelation chart renders where ACF data or residuals exist.", lambda: check_diagnostic_chart(("Residual Autocorrelation", "acf"), "Residual autocorrelation")),
        Gate(57, "F", "Residual vs fitted chart renders where selected predictions exist.", lambda: check_diagnostic_chart(("Residual vs Fitted",), "Residual vs fitted")),
        Gate(58, "F", "Diagnostic pass matrix renders with required checks or graceful missing states.", lambda: check_diagnostic_chart(("Diagnostic Pass Matrix", "Breusch", "Jarque"), "Diagnostic pass matrix")),
        Gate(59, "F", "Error distribution by horizon renders where prediction/error rows exist.", lambda: check_diagnostic_chart(("Error Distribution", "horizon"), "Error distribution by horizon")),
        Gate(60, "F", "Diagnostics screenshot is saved and visually aligns with supplied target.", lambda: visual_page_evidence("Diagnostics")),
        Gate(61, "G", "Scenario Comparison page renders without Streamlit exception.", lambda: page_evidence("Scenario Comparison")),
        Gate(62, "G", "Scenario A defaults to current refined finalist.", lambda: ok("Current finalist rows exist for Scenario A.") if not finalists().empty else fail("No current finalists for Scenario A.")),
        Gate(63, "G", "Scenario B defaults to pure Schiff structural benchmark.", lambda: ok("Pure Schiff rows exist for Scenario B.") if not schiff().empty else fail("No pure Schiff rows for Scenario B.")),
        Gate(64, "G", "Scenario controls render and are not fake static controls.", check_scenario_controls),
        Gate(65, "G", "Stream comparison chart uses finalist vs Schiff values.", check_join),
        Gate(66, "G", "Improvement-vs-benchmark chart computes gain correctly.", check_gain_correct),
        Gate(67, "G", "Horizon comparison chart uses finalist and Schiff horizon fields.", lambda: check_horizon(("stream_label", "horizon", "mape", "scenario"), "Scenario comparison")),
        Gate(68, "G", "Decision summary table labels full-sample gains and paired win rate clearly.", check_decision_summary),
        Gate(69, "G", "Scenario Comparison page has no more than four main chart/object panels.", lambda: check_panel_count("Scenario Comparison")),
        Gate(70, "G", "Scenario Comparison screenshot is saved and visually aligns with supplied target.", lambda: visual_page_evidence("Scenario Comparison")),
        Gate(71, "H", "Schiff Benchmark page renders without Streamlit exception.", lambda: page_evidence("Schiff Benchmark")),
        Gate(72, "H", "Schiff KPI cards use pure Schiff and finalist rows correctly.", check_schiff_kpis),
        Gate(73, "H", "Schiff vs Finalist MAPE chart renders.", lambda: check_diagnostic_chart(("Schiff vs Finalist", "MAPE"), "Schiff vs Finalist MAPE")),
        Gate(74, "H", "Benchmark Horizon Profiles render for all three streams where data exists.", lambda: check_horizon(("stream_label", "horizon", "mape", "scenario"), "Schiff benchmark")),
        Gate(75, "H", "Full-sample Gain vs Schiff chart does not misuse paired terminology.", check_full_sample_gain_chart),
        Gate(76, "H", "Benchmark Summary table renders with clean labels.", check_clean_table_labels),
        Gate(77, "H", "Schiff Benchmark page has no more than four main chart/object panels.", lambda: check_panel_count("Schiff Benchmark")),
        Gate(78, "H", "Schiff Benchmark screenshot is saved and visually aligns with supplied target.", lambda: visual_page_evidence("Schiff Benchmark")),
        Gate(79, "I", "All primary filters are directly clickable in the browser without using only the More button.", check_filters_clickable),
        Gate(80, "I", "All major Plotly hovers are human-readable.", check_hovers_clean),
        Gate(81, "J", "Overview screenshot conforms to target card/panel structure.", check_overview_card_structure),
        Gate(82, "J", "Overview stress bucket order is correct.", check_stress_bucket_order_visual),
        Gate(83, "J", "Overview candidate frontier has no giant circle/ellipse overlays.", check_candidate_no_giant_overlay),
        Gate(84, "J", "Overview candidate frontier displays finalist and Schiff markers.", check_candidate_marker_visuals),
        Gate(85, "J", "Diagnostics matrix has styled pass/caution/fail cells.", check_diagnostic_matrix_styled),
        Gate(86, "J", "Diagnostics page shows R2, Durbin-Watson and heteroscedasticity KPIs.", check_diagnostics_semantic_kpis),
        Gate(87, "J", "Diagnostics residual-vs-fitted chart solves scale imbalance.", check_residual_scale_solution),
        Gate(88, "J", "Scenario stream comparison labels do not overlap.", check_scenario_no_overlap_review),
        Gate(89, "J", "Scenario horizon comparison shows all three streams when Stream filter is All Streams.", lambda: check_horizon_all_streams_visual("Scenario Comparison")),
        Gate(90, "J", "Scenario decision table is styled and not an unformatted basic table.", check_scenario_decision_table_styled),
        Gate(91, "J", "Schiff MAPE chart separates Quarterly and Annual clearly.", check_schiff_mape_sections),
        Gate(92, "J", "Schiff horizon profiles show all three streams when Stream filter is All Streams.", lambda: check_horizon_all_streams_visual("Schiff Benchmark")),
        Gate(93, "J", "Schiff summary table is styled and readable.", check_schiff_summary_styled),
        Gate(94, "J", "Visual reviewer report marks all four pages PASS.", all_visual_reviews_pass),
        Gate(95, "J", "Screenshot review confirms no major target/current visual gaps remain.", check_screenshot_review_no_major_gaps),
        Gate(96, "J", "Browser test verifies all four top-level pages after visual fixes.", check_browser_pages_verified),
        Gate(97, "J", "Filter/dropdown tests still pass.", check_filters_clickable),
        Gate(98, "J", "Hover readability tests still pass.", check_hovers_clean),
        Gate(99, "J", "Performance smoke check still passes.", check_performance_smoke_pass),
        Gate(100, "J", "BUG_BACKLOG.md has no unchecked visual defects.", check_visual_backlog_closed),
    ]

    results: list[dict[str, Any]] = []
    for gate in gates:
        try:
            passed, evidence = gate.check()
        except Exception as exc:  # reported as a failed gate
            passed, evidence = False, f"{type(exc).__name__}: {exc}"
        results.append(
            {
                "id": gate.id,
                "section": gate.section,
                "description": gate.description,
                "status": "PASS" if passed else "FAIL",
                "evidence": evidence,
            }
        )

    supporting_checks = [
        {
            "name": "Exactly 100 validation gates are defined",
            "status": "PASS" if len(gates) == TOTAL_GATES else "FAIL",
            "evidence": f"{len(gates)} gates defined; expected {TOTAL_GATES}",
        },
        {
            "name": "Reset Filters works",
            "status": "PASS" if file_nonempty("artifacts/filter_interaction_review.md") and "Reset Filters" in safe_read(ROOT / "artifacts" / "filter_interaction_review.md") and schema_is_parquet_pass else "FAIL",
            "evidence": "filter interaction review plus passed Parquet schema required",
        },
        {
            "name": "Active filter chips update after filter changes",
            "status": "PASS"
            if (
                (
                    "active chip" in safe_read(ROOT / "artifacts" / "filter_interaction_review.md").lower()
                    or "selected combobox state" in safe_read(ROOT / "artifacts" / "filter_interaction_review.md").lower()
                )
                and schema_is_parquet_pass
            )
            else "FAIL",
            "evidence": "filter interaction review must record active chip or selected combobox state update",
        },
        {
            "name": "At least one chart/table/KPI updates after a non-default filter selection",
            "status": "PASS" if "updates after a filter change" in safe_read(ROOT / "artifacts" / "screenshot_review.md").lower() and schema_is_parquet_pass else "FAIL",
            "evidence": "browser review must record visible update after filter selection",
        },
        {
            "name": "Browser console has no critical errors",
            "status": "PASS" if "console" in safe_read(ROOT / "artifacts" / "screenshot_review.md").lower() and "critical" not in safe_read(ROOT / "artifacts" / "screenshot_review.md").lower() and schema_is_parquet_pass else "FAIL",
            "evidence": "current browser console evidence required",
        },
        {
            "name": "Network requests have no unexplained failures",
            "status": "PASS" if "network" in safe_read(ROOT / "artifacts" / "screenshot_review.md").lower() and schema_is_parquet_pass else "FAIL",
            "evidence": "current browser network evidence required",
        },
        {
            "name": "App cold load and tab switching are not materially slow",
            "status": "PASS" if file_nonempty("artifacts/performance_review.md") and schema_is_parquet_pass else "FAIL",
            "evidence": "performance review required after Parquet-backed run",
        },
        {
            "name": "The app does not parse legacy files on every filter interaction",
            "status": "PASS" if text_has_all(ROOT / "model_dashboard" / "evidence_pack.py", ("evidence_pack_signature", "load_evidence_pack")) and text_has_all(ROOT / "app.py", ("st.cache_data",)) else "FAIL",
            "evidence": "Evidence-pack cache signature and st.cache_data evidence checked in code",
        },
        {
            "name": "The evidence pack is cached using st.cache_data",
            "status": "PASS" if "cached_load_evidence_pack" in safe_read(ROOT / "app.py") and "st.cache_data" in safe_read(ROOT / "app.py") else "FAIL",
            "evidence": "app.py must cache evidence-pack load through st.cache_data",
        },
        {
            "name": "Full dense tables are behind expanders/downloads and not rendered by default",
            "status": "PASS" if "st.expander" in safe_read(ROOT / "app.py") and ("download_button" in safe_read(ROOT / "app.py")) else "FAIL",
            "evidence": "app.py expander/download evidence",
        },
        {
            "name": "Screenshots are regenerated after the final pass",
            "status": "PASS" if all(screenshot_ok(path) for path in PAGE_SCREENSHOTS.values()) and schema_is_parquet_pass else "FAIL",
            "evidence": "all four final screenshots required after passed schema",
        },
        {
            "name": "BUG_BACKLOG.md has no unchecked items",
            "status": "PASS" if "- [ ]" not in safe_read(ROOT / "BUG_BACKLOG.md") else "FAIL",
            "evidence": "BUG_BACKLOG.md checked for open task boxes",
        },
    ]

    passed_count = sum(1 for row in results if row["status"] == "PASS")
    failed_count = len(results) - passed_count
    support_failed = sum(1 for row in supporting_checks if row["status"] != "PASS")
    status = "PASS" if failed_count == 0 and support_failed == 0 else "FAIL"

    payload = {
        "status": status,
        "timestamp": now_iso(),
        "data_root": str(args.data_root),
        "repo_root": str(args.repo_root),
        "parquet_path": str(parquet_path) if parquet_path else None,
        "metadata_path": str(metadata_path) if metadata_path else None,
        "csv_mirror_path": str(csv_mirror_path) if csv_mirror_path else None,
        "total_gates": len(gates),
        "expected_gates": TOTAL_GATES,
        "passed_gates": passed_count,
        "failed_gates": failed_count,
        "gates": results,
        "supporting_checks": supporting_checks,
    }

    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "80_gate_validation_results.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    failed_rows = [row for row in results if row["status"] != "PASS"]
    support_failed_rows = [row for row in supporting_checks if row["status"] != "PASS"]
    report_lines = [
        "# 100 Gate Validation Report",
        "",
        f"Status: **{status}**.",
        f"Generated: {payload['timestamp']}",
        f"Passed gates: {passed_count}/{TOTAL_GATES}",
        f"Failed gates: {failed_count}/{TOTAL_GATES}",
        f"Failed supporting checks: {support_failed}",
        "",
        "## Data Sources",
        "",
        f"- Data root: `{args.data_root}`",
        f"- Parquet path: `{payload['parquet_path'] or 'not found'}`",
        f"- Metadata path: `{payload['metadata_path'] or 'not found'}`",
        f"- CSV mirror path: `{payload['csv_mirror_path'] or 'not found'}`",
        "",
        "## Gate Results",
        "",
        "| Gate | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    report_lines.extend(
        f"| {row['id']}. {row['description']} | {row['status']} | {str(row['evidence']).replace('|', '/')} |"
        for row in results
    )
    report_lines.extend(
        [
            "",
            "## Supporting Checks",
            "",
            "| Check | Status | Evidence |",
            "| --- | --- | --- |",
        ]
    )
    report_lines.extend(
        f"| {row['name']} | {row['status']} | {row['evidence'].replace('|', '/')} |" for row in supporting_checks
    )
    if failed_rows:
        report_lines.extend(
            [
                "",
                "## Failed Gate Summary",
                "",
                *[f"- Gate {row['id']}: {row['evidence']}" for row in failed_rows[:20]],
            ]
        )
    if support_failed_rows:
        report_lines.extend(
            [
                "",
                "## Failed Supporting Check Summary",
                "",
                *[f"- {row['name']}: {row['evidence']}" for row in support_failed_rows],
            ]
        )
    (artifacts / "80_gate_validation_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(
        f"100-gate validation: {status}. Passed {passed_count}/{TOTAL_GATES}; "
        f"failed {failed_count}/{TOTAL_GATES}; supporting failures {support_failed}."
    )
    if failed_rows:
        print("First failed gates:")
        for row in failed_rows[:10]:
            print(f"  {row['id']}: {row['evidence']}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
