from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "model_input_history"
WORKBOOK_NAME = "Master Copy revenue modelling workbook.xlsx"

STREAM_SHEETS = {
    "ped": "PED Inputs",
    "light_ruc": "Light RUC Inputs",
    "heavy_ruc": "Heavy RUC Inputs",
}

SOURCE_CANDIDATES = [
    ROOT / "data" / "source_workbooks" / WORKBOOK_NAME,
    ROOT.parent.parent / "Revenue Modeling - Strategic Review" / "04 Models" / "Inputs" / WORKBOOK_NAME,
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build compact repo-local model input history from the master workbook.")
    parser.add_argument("--workbook", type=Path, default=None, help="Optional source workbook override.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    workbook = resolve_workbook(args.workbook)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    raw = {stream: pd.read_excel(workbook, sheet_name=sheet) for stream, sheet in STREAM_SHEETS.items()}
    light = standardise_light(raw["light_ruc"])
    ped = standardise_ped(raw["ped"])
    heavy = standardise_heavy(raw["heavy_ruc"], light=light, ped=ped)
    frames = {"ped": ped, "light_ruc": light, "heavy_ruc": heavy}

    manifest_rows: list[dict[str, Any]] = []
    for stream, frame in frames.items():
        output = output_dir / f"{stream}_inputs.parquet"
        frame.to_parquet(output, index=False)
        manifest_rows.append(
            {
                "stream": stream.upper(),
                "source_sheet": STREAM_SHEETS[stream],
                "repo_relative_path": output.relative_to(ROOT).as_posix(),
                "rows": int(len(frame)),
                "columns": list(frame.columns),
                "first_period": first_non_null(frame.get("period")),
                "last_period": last_non_null(frame.get("period")),
                "positive_target_rows": int(pd.to_numeric(frame.get("target"), errors="coerce").gt(0).sum())
                if "target" in frame.columns
                else 0,
                "sha256": sha256(output),
                "size_bytes": output.stat().st_size,
            }
        )

    manifest = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_basename": workbook.name,
        "source_size_bytes": workbook.stat().st_size,
        "source_sha256": sha256(workbook),
        "source_sheets": STREAM_SHEETS,
        "workbook_full_path_public": False,
        "notes": (
            "Compact model-input history built from the master workbook input sheets. "
            "The raw workbook is intentionally not vendored."
        ),
        "artifacts": manifest_rows,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_markdown_manifest(output_dir / "manifest.md", manifest)
    print(f"Wrote model input history to {output_dir}")


def resolve_workbook(override: Path | None) -> Path:
    candidates: list[Path] = []
    if override is not None:
        candidates.append(override)
    for env_name in ["NLTF_MODEL_INPUT_WORKBOOK", "MODEL_INPUT_WORKBOOK_PATH"]:
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value))
    candidates.extend(SOURCE_CANDIDATES)
    for candidate in candidates:
        path = candidate.expanduser()
        if path.exists():
            return path
    searched = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"Could not find {WORKBOOK_NAME}. Searched: {searched}")


def standardise_light(frame: pd.DataFrame) -> pd.DataFrame:
    out = base_frame(frame)
    add_columns(
        out,
        frame,
        {
            "nominal_gdp_sa_nzd": "Nominal GDP (SA, NZD)",
            "gdp_deflator_sa": "GDP deflator (seasonally adjusted)",
            "gdp_rebasing_factor": "GDP rebasing factor",
            "real_gdp_sa_nzd": "Real GDP (SA, NZD)",
            "log_real_gdp": "Log real GDP",
            "diesel_price_nominal_cents_per_litre": "Diesel price (nominal, cents/litre)",
            "cpi_rebasing_factor": "CPI rebasing factor",
            "real_diesel_price_cents_per_litre": "Diesel price (real, cents/litre)",
            "log_real_diesel_price": "Log real diesel price",
            "light_ruc_revenue_nzd": "Light RUC revenue (NZD)",
            "target": "Light RUC net km",
            "light_ruc_price_nominal_nzd_per_1000km": "Light RUC price (nominal, NZD/1,000 km)",
            "real_light_ruc_price_nzd_per_1000km": "Light RUC price (real, NZD/1,000 km)",
            "log_real_light_ruc_price": "Log real light RUC price",
            "lagged_real_light_ruc_price_nzd_per_1000km": "Lagged light RUC price (real, NZD/1,000 km)",
            "log_lagged_real_light_ruc_price": "Log lagged light RUC price",
            "q2_dummy": "Q2 dummy",
            "q3_dummy": "Q3 dummy",
            "q4_dummy": "Q4 dummy",
            "post_2020_dummy": "Post-2020 dummy",
            "data_status": "Data status",
            "notes": "Notes",
        },
    )
    add_light_feature_engineering(out)
    return ordered(out)


def standardise_ped(frame: pd.DataFrame) -> pd.DataFrame:
    out = base_frame(frame)
    add_columns(
        out,
        frame,
        {
            "nominal_gdp_sa_nzd": "Nominal GDP (SA, NZD)",
            "population": "Population",
            "nominal_gdp_per_capita_nzd": "Nominal GDP per capita (NZD)",
            "gdp_deflator_sa": "GDP deflator (seasonally adjusted)",
            "gdp_rebasing_factor": "GDP rebasing factor",
            "real_gdp_per_capita_nzd": "Real GDP per capita (NZD)",
            "log_real_gdp_per_capita": "Log real GDP per capita",
            "petrol_price_nominal_cents_per_litre": "Petrol price (nominal, cents/litre)",
            "cpi_rebasing_factor": "CPI rebasing factor",
            "real_petrol_price_cents_per_litre": "Petrol price (real, cents/litre)",
            "log_real_petrol_price": "Log real petrol price",
            "target": "Light petrol VKT per capita (km)",
            "light_petrol_vkt_total_km": "Light petrol VKT total (km)",
            "log_target": "Log VKT per capita",
            "log_total_vkt": "Log total VKT",
            "unemployment_percent": "Unemployment (%)",
            "unemployment_rate": "Unemployment rate",
            "log_unemployment_rate": "Log unemployment rate",
            "trend_index": "Trend index",
            "log_trend": "Log trend index",
            "post_2011_dummy": "Post-2011 dummy",
            "dummy_2020": "2020 dummy",
            "post_2020_dummy": "Post-2020 dummy",
            "q2_dummy": "Q2 dummy",
            "q3_dummy": "Q3 dummy",
            "q4_dummy": "Q4 dummy",
            "post_2011_x_log_trend": "Post-2011 \u00d7 log trend",
            "data_status": "Data status",
            "notes": "Notes",
        },
    )
    add_target_lags(out)
    return ordered(out)


def standardise_heavy(frame: pd.DataFrame, *, light: pd.DataFrame, ped: pd.DataFrame) -> pd.DataFrame:
    out = base_frame(frame)
    add_columns(
        out,
        frame,
        {
            "nominal_gdp_sa_nzd": "Nominal GDP (SA, NZD)",
            "gdp_deflator_sa": "GDP deflator (seasonally adjusted)",
            "gdp_rebasing_factor": "GDP rebasing factor",
            "real_gdp_sa_nzd": "Real GDP (SA, NZD)",
            "log_real_gdp": "Log real GDP",
            "heavy_ruc_revenue_nzd": "Heavy RUC revenue (NZD)",
            "target": "Heavy RUC net km",
            "heavy_ruc_price_nominal_nzd_per_1000km": "Heavy RUC price (nominal, NZD/1,000 km)",
            "real_heavy_ruc_price_nzd_per_1000km": "Heavy RUC price (real, NZD/1,000 km)",
            "log_real_heavy_ruc_price": "Log real heavy RUC price",
            "lead_real_heavy_ruc_price_nzd_per_1000km": "Lead heavy RUC price (real, NZD/1,000 km)",
            "log_lead_real_heavy_ruc_price": "Log lead heavy RUC price",
            "q2_dummy": "Q2 dummy",
            "q3_dummy": "Q3 dummy",
            "q4_dummy": "Q4 dummy",
            "data_status": "Data status",
            "notes": "Notes",
        },
    )
    light_lookup = light.set_index("period")
    for column in [
        "real_diesel_price_cents_per_litre",
        "log_real_diesel_price",
        "real_light_ruc_price_nzd_per_1000km",
        "lagged_real_light_ruc_price_nzd_per_1000km",
        "log_real_light_ruc_price",
        "log_lagged_real_light_ruc_price",
    ]:
        out[column] = out["period"].map(light_lookup[column]) if column in light_lookup.columns else np.nan
    ped_lookup = ped.set_index("period")
    out["unemployment_rate"] = out["period"].map(ped_lookup["unemployment_rate"]) if "unemployment_rate" in ped_lookup.columns else np.nan
    out["log_unemployment_rate"] = out["period"].map(ped_lookup["log_unemployment_rate"]) if "log_unemployment_rate" in ped_lookup.columns else np.nan
    add_target_lags(out)
    return ordered(out)


def base_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["period"] = frame["Quarter"].astype(str).str.strip().str.upper()
    out["period_label"] = frame["Period"].astype(str).str.strip() if "Period" in frame.columns else ""
    out["year"] = out["period"].map(lambda value: parse_period(value)[0])
    out["quarter"] = out["period"].map(lambda value: parse_period(value)[1])
    first_key = out["period"].dropna().map(quarter_sort_key).min()
    out["period_index"] = out["period"].map(lambda value: quarter_sort_key(value) - int(first_key) + 1)
    out["trend_index"] = out["period_index"]
    out["log_trend"] = np.where(out["trend_index"] > 0, np.log(out["trend_index"]), np.nan)
    return out


def add_columns(out: pd.DataFrame, source: pd.DataFrame, mapping: dict[str, str]) -> None:
    for target, source_column in mapping.items():
        if source_column not in source.columns:
            out[target] = np.nan
            continue
        series = source[source_column]
        if target in {"data_status", "notes"}:
            out[target] = series.fillna("").astype(str)
        else:
            out[target] = pd.to_numeric(series, errors="coerce")


def add_target_lags(out: pd.DataFrame) -> None:
    target = pd.to_numeric(out.get("target"), errors="coerce")
    out["target_lag_1"] = target.shift(1)
    out["target_lag_4"] = target.shift(4)
    out["log_target"] = safe_log(target)
    out["log_target_lag_1"] = safe_log(out["target_lag_1"])
    out["log_target_lag_4"] = safe_log(out["target_lag_4"])
    out["diff_log_target_lag_1_lag_4"] = out["log_target_lag_1"] - out["log_target_lag_4"]


def add_light_feature_engineering(out: pd.DataFrame) -> None:
    add_target_lags(out)
    log_diesel = pd.to_numeric(out.get("log_real_diesel_price"), errors="coerce")
    log_ruc = pd.to_numeric(out.get("log_real_light_ruc_price"), errors="coerce")
    log_gdp = pd.to_numeric(out.get("log_real_gdp"), errors="coerce")
    post_2020 = pd.to_numeric(out.get("post_2020_dummy"), errors="coerce").fillna(0)
    out["diesel_x_ruc_price"] = log_diesel * log_ruc
    out["gdp_x_post2020"] = log_gdp * post_2020
    out["ruc_x_post2020"] = log_ruc * post_2020
    out["diesel_x_post2020"] = log_diesel * post_2020
    out["time_trend"] = out["period_index"]
    out["log_real_diesel_price_diff1"] = log_diesel.diff()
    out["log_real_diesel_price_lag1"] = log_diesel.shift(1)
    out["log_real_diesel_price_lag4"] = log_diesel.shift(4)
    out["log_real_light_ruc_price_diff1"] = log_ruc.diff()
    out["log_real_light_ruc_price_lag1"] = log_ruc.shift(1)
    out["log_real_light_ruc_price_lag4"] = log_ruc.shift(4)
    out["log_real_gdp_diff1"] = log_gdp.diff()
    out["log_real_gdp_lag1"] = log_gdp.shift(1)
    out["log_real_gdp_lag4"] = log_gdp.shift(4)


def ordered(frame: pd.DataFrame) -> pd.DataFrame:
    leading = [
        "period",
        "period_label",
        "year",
        "quarter",
        "period_index",
        "trend_index",
        "target",
        "log_target",
        "target_lag_1",
        "target_lag_4",
    ]
    columns = [column for column in leading if column in frame.columns]
    columns.extend(column for column in frame.columns if column not in columns)
    return frame[columns].copy()


def safe_log(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    out = pd.Series(np.nan, index=numeric.index, dtype=float)
    mask = numeric.gt(0)
    out.loc[mask] = np.log(numeric.loc[mask])
    return out


def parse_period(period: str) -> tuple[int, int]:
    year_text, quarter_text = str(period).upper().split("Q", 1)
    return int(year_text), int(quarter_text)


def quarter_sort_key(period: str) -> int:
    year, quarter = parse_period(period)
    return year * 4 + quarter


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def first_non_null(series: pd.Series | None) -> Any:
    if series is None:
        return None
    values = series.dropna()
    return values.iloc[0] if not values.empty else None


def last_non_null(series: pd.Series | None) -> Any:
    if series is None:
        return None
    values = series.dropna()
    return values.iloc[-1] if not values.empty else None


def write_markdown_manifest(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# Model Input History Manifest",
        "",
        f"- Source workbook: `{manifest['source_basename']}`",
        f"- Source SHA256: `{manifest['source_sha256']}`",
        f"- Created at: `{manifest['created_at']}`",
        "- Raw workbook vendored: `false`",
        "",
        "| Stream | Source sheet | Repo path | Rows | First period | Last period | SHA256 |",
        "|---|---|---|---:|---|---|---|",
    ]
    for row in manifest["artifacts"]:
        lines.append(
            "| {stream} | {source_sheet} | {repo_relative_path} | {rows} | {first_period} | {last_period} | {sha256} |".format(
                **row
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
