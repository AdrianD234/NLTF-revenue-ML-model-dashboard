from __future__ import annotations

import base64
from functools import lru_cache
import html
from pathlib import Path
import re
from typing import Any, Iterable

import pandas as pd
import streamlit as st

try:
    from .labels import POWERBI_BLUE, POWERBI_GREEN, POWERBI_TEXT, model_alias
except ImportError:
    POWERBI_BLUE = "#002B5C"
    POWERBI_GREEN = "#A7C800"
    POWERBI_TEXT = "#102A43"

    def model_alias(value: Any, max_length: int = 72) -> str:
        text = "" if value is None else str(value)
        return text if len(text) <= max_length else f"{text[: max_length - 1]}..."


LOGO_ASSET_PATH = Path(__file__).resolve().parents[1] / "assets" / "nz-transport-agency-waka-kotahi.png"


@lru_cache(maxsize=1)
def _brand_logo_src() -> str | None:
    try:
        encoded = base64.b64encode(LOGO_ASSET_PATH.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:image/png;base64,{encoded}"


def _brand_logo_html() -> str:
    src = _brand_logo_src()
    if src:
        return f'<img class="brand-logo" src="{html.escape(src)}" alt="NZ Transport Agency Waka Kotahi logo">'
    return (
        "<div class='brand-fallback-lockup'><div class='brand-mark'></div><div>NZ TRANSPORT AGENCY"
        "<span class='brand-small'>WAKA KOTAHI</span></div></div>"
    )


def inject_theme() -> None:
    st.markdown(
        f"""
        <style>
            :root {{
                --pbi-blue: {POWERBI_BLUE};
                --pbi-green: {POWERBI_GREEN};
                --pbi-text: {POWERBI_TEXT};
                --pbi-border: #D9E2EC;
                --pbi-shadow: 0 8px 20px rgba(15, 23, 42, 0.07);
                --gov-navy: #002B5C;
                --gov-deep: #003366;
                --gov-lime: #A7C800;
                --gov-green: #00843D;
                --gov-teal: #008C7E;
                --gov-orange: #F37021;
                --gov-light-blue: #EAF2F8;
                --gov-border: #D9E2EC;
                --gov-text: #102A43;
            }}
            header[data-testid="stHeader"], #MainMenu, div[data-testid="stToolbar"],
            div[data-testid="stDecoration"], div[data-testid="stStatusWidget"],
            div[data-testid="stDeployButton"], button[title="Deploy"],
            a[href*="streamlit.io/cloud"], footer {{
                display: none !important;
                visibility: hidden !important;
            }}
            div.block-container, .main .block-container, section.main > div.block-container {{
                padding: 0.12rem 1rem 1.35rem !important;
                max-width: 1900px;
            }}
            div[data-testid="stAppViewContainer"] > .main {{
                padding-top: 0 !important;
            }}
            body, .stMarkdown, .stDataFrame {{
                color: var(--pbi-text);
                font-family: "Segoe UI", Inter, Arial, sans-serif;
            }}
            .gov-header, .governance-shell {{
                border-bottom: 1px solid #D9E2EC;
                margin-bottom: 0;
                padding: 0 0 0.1rem;
            }}
            .governance-masthead {{
                align-items: center;
                display: grid;
                gap: 0.72rem;
                grid-template-columns: 250px minmax(0, 1fr) minmax(142px, auto);
                margin-bottom: 0;
            }}
            .brand-lockup {{
                align-items: center;
                color: var(--pbi-blue);
                display: flex;
                font-weight: 750;
                gap: 0;
                letter-spacing: 0;
                line-height: 1.1;
                min-width: 0;
            }}
            .brand-logo {{
                display: block;
                height: auto;
                max-height: 46px;
                max-width: 240px;
                object-fit: contain;
                object-position: left center;
                width: 100%;
            }}
            .brand-fallback-lockup {{
                align-items: center;
                display: flex;
                gap: 0.65rem;
            }}
            .brand-mark {{
                border: 4px solid var(--pbi-green);
                border-right-color: var(--pbi-blue);
                border-radius: 999px;
                height: 35px;
                width: 35px;
            }}
            .brand-small {{
                color: #334155;
                display: block;
                font-size: 0.58rem;
                font-weight: 700;
                margin-top: 0.08rem;
            }}
            .page-chip {{
                border-left: 1px solid #D9E2EC;
                color: var(--pbi-blue);
                font-size: 0.8rem;
                font-weight: 700;
                line-height: 1.15;
                max-width: 210px;
                padding: 0.35rem 0 0.35rem 0.9rem;
                text-align: right;
                white-space: normal;
            }}
            .pbi-header {{
                color: var(--pbi-blue);
                display: inline-block;
                font-size: 1.96rem;
                font-weight: 780;
                letter-spacing: 0;
                line-height: 1.05;
                margin-bottom: 0.02rem;
                padding-bottom: 0.18rem;
                position: relative;
            }}
            .pbi-header::after {{
                background: var(--pbi-green);
                border-radius: 999px;
                bottom: 0;
                content: "";
                height: 5px;
                left: 0;
                position: absolute;
                width: 100%;
            }}
            .pbi-section-title {{
                color: var(--pbi-blue);
                font-size: 1.18rem;
                font-weight: 650;
                margin: 1rem 0 0.55rem;
            }}
            .pbi-subtle {{
                color: #64748B;
                font-size: 0.76rem;
                line-height: 1.25;
                max-width: 920px;
                overflow-wrap: normal;
            }}
            .masthead-subtitle {{
                display: none;
            }}
            .gov-filter-card, .filter-shell {{
                background: #FFFFFF;
                border: 1px solid #D9E2EC;
                border-radius: 8px;
                box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05);
                margin: 0.04rem 0 0.16rem;
                padding: 0.22rem 0.42rem 0.12rem;
            }}
            div[data-testid="stRadio"] {{
                margin: -2.58rem 0 0.42rem;
            }}
            div[data-testid="stRadio"] > label {{
                display: none;
            }}
            div[data-testid="stRadio"] div[role="radiogroup"] {{
                align-items: stretch;
                border-bottom: 1px solid var(--gov-border);
                display: flex;
                gap: 0.48rem;
                justify-content: flex-end;
                min-height: 28px;
                padding-left: clamp(430px, 36vw, 650px);
                padding-right: 170px;
            }}
            div[data-testid="stRadio"] div[role="radiogroup"] label {{
                border-bottom: 3px solid transparent;
                border-radius: 7px 7px 0 0;
                color: var(--gov-navy);
                display: flex;
                font-size: 0.8rem;
                font-weight: 700;
                min-width: max-content;
                padding: 0.22rem 0.5rem 0.34rem;
                white-space: nowrap;
            }}
            div[data-testid="stRadio"] div[role="radiogroup"] label > div:first-child {{
                height: 1px !important;
                margin: 0 !important;
                min-height: 1px !important;
                opacity: 0 !important;
                overflow: hidden !important;
                padding: 0 !important;
                position: absolute !important;
                width: 1px !important;
            }}
            div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) {{
                background: var(--gov-navy);
                border-bottom-color: var(--gov-lime);
                color: #FFFFFF;
            }}
            div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) div[data-testid="stMarkdownContainer"] p {{
                color: #FFFFFF !important;
            }}
            div[data-testid="stRadio"] div[role="radiogroup"] label div[data-testid="stMarkdownContainer"] p {{
                font-size: 0.8rem;
                font-weight: 700;
                white-space: nowrap;
            }}
            .filter-title {{
                color: var(--pbi-blue);
                font-size: 0.68rem;
                font-weight: 800;
                letter-spacing: 0.03em;
                margin-bottom: 0.02rem;
                text-transform: uppercase;
            }}
            .filter-chip {{
                background: #EAF2F8;
                border: 1px solid #D9E2EC;
                border-radius: 999px;
                color: var(--pbi-blue);
                display: inline-block;
                font-size: 0.72rem;
                font-weight: 650;
                margin: 0.04rem 0.16rem 0.02rem 0;
                padding: 0.12rem 0.38rem;
            }}
            .gov-filter-grid {{
                align-items: end;
                display: grid;
                gap: 0.35rem;
                grid-template-columns: repeat(auto-fit, minmax(168px, 1fr));
                margin-top: 0.04rem;
            }}
            .gov-filter-item {{
                min-width: 0;
            }}
            .gov-filter-label {{
                color: var(--gov-navy);
                font-size: 0.66rem;
                font-weight: 750;
                line-height: 1.1;
                margin-bottom: 0.08rem;
            }}
            .gov-filter-value {{
                align-items: center;
                background: #F3F6FA;
                border: 1px solid rgba(217, 226, 236, 0.95);
                border-radius: 7px;
                color: #0B2D4D;
                display: flex;
                font-size: 0.72rem;
                font-weight: 650;
                justify-content: space-between;
                line-height: 1.14;
                min-height: 26px;
                overflow: hidden;
                padding: 0.14rem 0.34rem;
                text-overflow: clip;
                white-space: normal;
            }}
            .gov-filter-value span:first-child {{
                overflow: visible;
                text-overflow: clip;
                white-space: normal;
            }}
            .gov-filter-display {{
                display: block;
            }}
            .gov-filter-caret {{
                color: var(--gov-navy);
                flex: 0 0 auto;
                font-size: 0.74rem;
                padding-left: 0.28rem;
            }}
            .gov-kpi-grid, .kpi-grid {{
                display: grid;
                gap: 0.44rem;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                margin: 0.08rem 0 0.34rem;
            }}
            @media (max-width: 1050px) {{
                .kpi-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
            }}
            @media (max-width: 760px) {{
                .kpi-grid {{ grid-template-columns: 1fr; }}
            }}
            @media (max-width: 980px) {{
                div.block-container, .main .block-container, section.main > div.block-container {{
                    padding-left: 0.62rem !important;
                    padding-right: 0.62rem !important;
                }}
                div[data-testid="stVerticalBlockBorderWrapper"]:has(.filter-title) .gov-filter-grid {{
                    grid-template-columns: repeat(3, minmax(0, 1fr));
                }}
                div[data-testid="stVerticalBlockBorderWrapper"]:has(.filter-title) [data-testid="stCaptionContainer"] p {{
                    white-space: normal;
                }}
                .run-evidence-compact {{
                    white-space: normal;
                }}
                .governance-masthead {{
                    gap: 0.46rem;
                    grid-template-columns: 190px minmax(0, 1fr) minmax(112px, auto);
                }}
                .brand-logo {{
                    max-height: 36px;
                    max-width: 182px;
                }}
                .brand-mark {{
                    border-width: 3px;
                    height: 30px;
                    width: 30px;
                }}
                .brand-lockup {{
                    font-size: 0.78rem;
                    gap: 0.48rem;
                }}
                .brand-small {{
                    font-size: 0.48rem;
                }}
                .pbi-header {{
                    font-size: 1.58rem;
                }}
                .pbi-subtle {{
                    font-size: 0.66rem;
                    line-height: 1.2;
                }}
                .page-chip {{
                    font-size: 0.66rem;
                    max-width: 120px;
                    padding-left: 0.48rem;
                }}
                div[data-testid="stRadio"] {{
                    margin: 0 0 0.08rem;
                }}
                div[data-testid="stRadio"] div[role="radiogroup"] {{
                    gap: 0.18rem;
                    justify-content: space-between;
                    padding-left: 0;
                    padding-right: 0;
                }}
                div[data-testid="stRadio"] div[role="radiogroup"] label {{
                    font-size: 0.72rem;
                    justify-content: center;
                    min-width: 0;
                    padding: 0.18rem 0.24rem 0.3rem;
                }}
                div[data-testid="stRadio"] div[role="radiogroup"] label div[data-testid="stMarkdownContainer"] p {{
                    font-size: 0.72rem;
                    line-height: 1.08;
                    text-align: center;
                    white-space: normal;
                }}
                .gov-filter-grid {{
                    gap: 0.22rem;
                    grid-template-columns: repeat(3, minmax(0, 1fr));
                }}
                div[data-testid="stHorizontalBlock"]:has(.gov-chart-card) {{
                    flex-wrap: wrap;
                }}
                div[data-testid="stHorizontalBlock"]:has(.gov-chart-card) > div[data-testid="stColumn"] {{
                    flex: 1 1 360px !important;
                    min-width: min(100%, 350px) !important;
                    width: auto !important;
                }}
            }}
            @media (max-width: 700px) {{
                .gov-filter-grid {{
                    grid-template-columns: 1fr;
                }}
                div[data-testid="stHorizontalBlock"]:has(.gov-chart-card) > div[data-testid="stColumn"] {{
                    flex: 1 1 420px !important;
                    min-width: min(100%, 420px) !important;
                }}
            }}
            .gov-kpi-card {{
                align-items: center;
                background: #fff;
                border: 1px solid var(--pbi-border);
                border-radius: 8px;
                box-shadow: var(--pbi-shadow);
                display: grid;
                gap: 0.52rem;
                grid-template-columns: 46px 1fr;
                min-height: 64px;
                overflow: hidden;
                padding: 0.42rem 0.58rem;
                position: relative;
            }}
            .kpi-card {{
                background: #fff;
                border: 1px solid var(--pbi-border);
                border-radius: 8px;
                box-shadow: var(--pbi-shadow);
                min-height: 78px;
                overflow: hidden;
                padding: 0.68rem 0.82rem;
                position: relative;
            }}
            .kpi-card::before {{
                background: linear-gradient(90deg, var(--pbi-green), rgba(148, 163, 184, 0.38));
                content: "";
                height: 4px;
                left: 0;
                position: absolute;
                right: 0;
                top: 0;
            }}
            .kpi-title {{
                color: var(--pbi-blue);
                font-size: 0.78rem;
                font-weight: 650;
                line-height: 1.25;
                margin-bottom: 0.08rem;
            }}
            .kpi-value {{
                color: #0F172A;
                font-size: 1.42rem;
                font-weight: 700;
                line-height: 1.1;
            }}
            .kpi-sub {{
                color: #64748B;
                font-size: 0.72rem;
                line-height: 1.25;
                margin-top: 0.12rem;
            }}
            .gov-kpi-icon {{
                align-items: center;
                background: linear-gradient(145deg, var(--gov-navy), var(--gov-deep));
                border-radius: 8px;
                color: #FFFFFF;
                display: flex;
                font-size: 1.08rem;
                font-weight: 800;
                height: 38px;
                justify-content: center;
                width: 38px;
            }}
            .gov-kpi-delta {{
                color: var(--gov-green);
                font-size: 0.72rem;
                font-weight: 800;
                margin-top: 0.1rem;
            }}
            .info-panel {{
                background: #F8FAFC;
                border: 1px solid var(--pbi-border);
                border-left: 5px solid var(--pbi-blue);
                border-radius: 8px;
                color: #334155;
                margin: 0.35rem 0 0.55rem;
                padding: 0.58rem 0.72rem;
            }}
            .decision-brief {{
                background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 60%, rgba(167, 190, 25, 0.11) 100%);
                border: 1px solid rgba(25, 69, 107, 0.18);
                border-left: 6px solid var(--pbi-green);
                border-radius: 8px;
                box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
                margin: 0.35rem 0 0.95rem;
                padding: 0.95rem 1rem;
            }}
            .decision-kicker {{
                color: #64748B;
                font-size: 0.73rem;
                font-weight: 700;
                letter-spacing: 0.04em;
                margin-bottom: 0.25rem;
                text-transform: uppercase;
            }}
            .decision-title {{
                color: var(--pbi-blue);
                font-size: 1.18rem;
                font-weight: 750;
                line-height: 1.25;
                margin-bottom: 0.35rem;
            }}
            .decision-copy {{
                color: #334155;
                font-size: 0.94rem;
                line-height: 1.45;
                margin-bottom: 0.75rem;
            }}
            .decision-grid {{
                display: grid;
                gap: 0.65rem;
                grid-template-columns: repeat(4, minmax(0, 1fr));
            }}
            @media (max-width: 1180px) {{
                .decision-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
            }}
            @media (max-width: 760px) {{
                .decision-grid {{ grid-template-columns: 1fr; }}
            }}
            .decision-metric {{
                background: rgba(255, 255, 255, 0.78);
                border: 1px solid rgba(25, 69, 107, 0.13);
                border-radius: 8px;
                min-height: 82px;
                padding: 0.7rem 0.75rem;
            }}
            .decision-label {{
                color: #64748B;
                font-size: 0.74rem;
                font-weight: 700;
                line-height: 1.2;
                margin-bottom: 0.28rem;
                text-transform: uppercase;
            }}
            .decision-value {{
                color: #0F172A;
                font-size: 1.02rem;
                font-weight: 750;
                line-height: 1.2;
            }}
            .decision-sub {{
                color: #64748B;
                font-size: 0.77rem;
                line-height: 1.3;
                margin-top: 0.28rem;
            }}
            .warning-panel {{
                background: #FFF7ED;
                border: 1px solid rgba(234, 88, 12, 0.24);
                border-left: 5px solid #F97316;
                border-radius: 8px;
                color: #7C2D12;
                margin: 0.6rem 0 1rem;
                padding: 0.8rem 0.95rem;
            }}
            .gov-chart-card, .chart-card {{
                background: #fff;
                border: 0;
                border-radius: 0;
                box-shadow: none;
                margin: 0;
                padding: 0.16rem 0.12rem 0;
            }}
            .chart-card-title {{
                color: var(--pbi-blue);
                font-size: 0.9rem;
                font-weight: 760;
                line-height: 1.2;
                margin-bottom: 0.1rem;
            }}
            .chart-card-header {{
                align-items: flex-start;
                display: flex;
                gap: 0.5rem;
                justify-content: space-between;
                margin-bottom: 0.1rem;
                position: relative;
            }}
            .chart-card-subtitle {{
                color: #475569;
                font-size: 0.72rem;
                line-height: 1.25;
                margin-bottom: 0.08rem;
            }}
            .chart-info-trigger {{
                align-items: center;
                background: #EFF6FF;
                border: 1px solid #BFD4EA;
                border-radius: 999px;
                color: var(--pbi-blue);
                cursor: help;
                display: inline-flex;
                flex: 0 0 auto;
                font-size: 0.68rem;
                font-weight: 800;
                height: 1.05rem;
                justify-content: center;
                line-height: 1;
                margin-top: -0.02rem;
                outline: none;
                position: relative;
                width: 1.05rem;
                z-index: 4;
            }}
            .chart-info-trigger:focus {{
                box-shadow: 0 0 0 2px rgba(0, 43, 92, 0.22);
            }}
            .chart-info-text {{
                background: #0F172A;
                border-radius: 7px;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.24);
                color: #F8FAFC;
                font-size: 0.72rem;
                font-weight: 500;
                line-height: 1.34;
                max-width: min(420px, 72vw);
                min-width: 280px;
                opacity: 0;
                padding: 0.62rem 0.72rem;
                pointer-events: none;
                position: absolute;
                right: 0;
                text-align: left;
                top: calc(100% + 0.42rem);
                transition: opacity 120ms ease, visibility 120ms ease;
                visibility: hidden;
                white-space: normal;
                z-index: 9999;
            }}
            .chart-info-text::before {{
                border-bottom: 6px solid #0F172A;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                content: "";
                position: absolute;
                right: 0.32rem;
                top: -6px;
            }}
            .chart-info-trigger:hover .chart-info-text,
            .chart-info-trigger:focus .chart-info-text,
            .chart-info-trigger:focus-within .chart-info-text {{
                opacity: 1;
                visibility: visible;
            }}
            .gov-footer, .footer-strip {{
                align-items: center;
                background: linear-gradient(90deg, #002B5C, #003366);
                color: #FFFFFF;
                display: flex;
                font-size: 0.86rem;
                justify-content: space-between;
                margin-top: 1.25rem;
                padding: 0.75rem 1rem;
            }}
            .gov-dashboard-grid {{
                display: grid;
                gap: 0.65rem;
                grid-template-columns: repeat(12, minmax(0, 1fr));
            }}
            .gov-note {{
                color: #64748B;
                font-size: 0.72rem;
                font-style: italic;
            }}
            .gov-badge {{
                border-radius: 999px;
                display: inline-block;
                font-size: 0.72rem;
                font-weight: 750;
                padding: 0.16rem 0.48rem;
            }}
            .gov-nav, div[data-testid="stTabs"] {{
                margin-top: 0.04rem;
            }}
            .footer-strip span {{
                opacity: 0.95;
            }}
            .badge {{
                border-radius: 999px;
                display: inline-block;
                font-size: 0.78rem;
                font-weight: 650;
                margin-right: 0.3rem;
                padding: 0.18rem 0.55rem;
            }}
            .badge-good {{ background: rgba(22, 163, 74, 0.12); color: #166534; }}
            .badge-mixed {{ background: rgba(245, 158, 11, 0.14); color: #92400E; }}
            .badge-bad {{ background: rgba(220, 38, 38, 0.12); color: #991B1B; }}
            .story-grid {{
                display: grid;
                gap: 0.85rem;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                margin: 0.55rem 0 1rem;
            }}
            @media (max-width: 1180px) {{
                .story-grid {{ grid-template-columns: 1fr; }}
            }}
            .story-card {{
                background: #fff;
                border: 1px solid var(--pbi-border);
                border-radius: 8px;
                box-shadow: var(--pbi-shadow);
                min-height: 180px;
                padding: 0.9rem 1rem;
            }}
            .story-stream {{
                color: var(--pbi-blue);
                font-size: 1.02rem;
                font-weight: 700;
                line-height: 1.2;
                margin-bottom: 0.45rem;
            }}
            .story-question {{
                color: #64748B;
                font-size: 0.74rem;
                font-weight: 700;
                letter-spacing: 0;
                margin-top: 0.55rem;
                text-transform: uppercase;
            }}
            .story-model {{
                color: #0F172A;
                font-size: 0.91rem;
                font-weight: 650;
                line-height: 1.25;
                margin-top: 0.12rem;
            }}
            .story-stat {{
                color: #334155;
                font-size: 0.86rem;
                line-height: 1.35;
                margin-top: 0.25rem;
            }}
            div[data-testid="stTabs"] button[role="tab"] {{
                padding-left: 1rem;
                padding-right: 1rem;
            }}
            div[data-testid="stTabs"] button[role="tab"] p {{
                color: var(--gov-navy);
                font-size: 0.92rem;
                font-weight: 650;
                white-space: nowrap;
            }}
            div[data-baseweb="select"] > div {{
                min-height: 28px;
            }}
            div[data-baseweb="select"] span, div[data-baseweb="select"] div {{
                font-size: 0.8rem;
            }}
            .stButton > button, .stDownloadButton > button {{
                font-size: 0.76rem;
                min-height: 30px;
                padding: 0.24rem 0.56rem;
                white-space: nowrap;
            }}
            .stButton > button p, .stDownloadButton > button p {{
                font-size: 0.76rem;
                white-space: nowrap;
            }}
            div[data-testid="stPopover"] button {{
                font-size: 0.76rem;
                min-height: 30px;
                padding: 0.24rem 0.5rem;
                white-space: nowrap;
            }}
            div[data-testid="stSelectbox"], div[data-testid="stButton"], div[data-testid="stDownloadButton"] {{
                margin-bottom: 0 !important;
            }}
            div[data-testid="stVerticalBlockBorderWrapper"] {{
                padding: 0.34rem !important;
            }}
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.filter-title) {{
                margin-bottom: 0.14rem !important;
                padding: 0.18rem 0.34rem 0.02rem !important;
            }}
            div[data-testid="stLayoutWrapper"]:has(.filter-title) > div[data-testid="stVerticalBlock"] {{
                padding-bottom: 0 !important;
            }}
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.filter-title) .gov-filter-grid {{
                gap: 0.28rem;
                grid-template-columns: repeat(6, minmax(0, 1fr));
                margin-top: 0.02rem;
            }}
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.filter-title) [data-testid="stCaptionContainer"] {{
                margin-top: 0.08rem !important;
            }}
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.filter-title) [data-testid="stCaptionContainer"] p {{
                font-size: 0.68rem !important;
                line-height: 1.08 !important;
                margin: 0 !important;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }}
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.filter-title) div[data-testid="stSelectbox"] label {{
                line-height: 1.02 !important;
                margin-bottom: -0.2rem !important;
                min-height: 0 !important;
            }}
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.filter-title) div[data-baseweb="select"] > div {{
                min-height: 26px !important;
            }}
            .run-evidence-compact {{
                color: #486581;
                font-size: 0.68rem;
                line-height: 1.08;
                margin: -0.56rem 0 -0.38rem;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }}
            div[data-testid="stMetric"] {{
                background: #fff;
                border: 1px solid var(--pbi-border);
                border-radius: 8px;
                box-shadow: var(--pbi-shadow);
                padding: 0.85rem 0.95rem;
            }}
            div[data-testid="stMetric"] label {{
                color: var(--pbi-blue);
                font-weight: 650;
            }}
            div[data-testid="stDataFrame"] {{
                border: 1px solid var(--pbi-border);
                border-radius: 8px;
                box-shadow: var(--pbi-shadow);
                overflow: hidden;
            }}
            div[data-testid="stDataFrame"] [role="columnheader"] {{
                color: var(--pbi-blue);
                font-weight: 650;
            }}
            .table-caption {{
                color: #64748B;
                font-size: 0.82rem;
                margin: -0.15rem 0 0.45rem;
            }}
            .diagnostic-tooltip-matrix {{
                margin-top: 0.36rem;
                overflow: visible;
                width: 100%;
            }}
            .diagnostic-pass-matrix {{
                border-collapse: separate;
                border-spacing: 0;
                font-size: 0.76rem;
                table-layout: fixed;
                width: 100%;
            }}
            .diagnostic-pass-matrix th,
            .diagnostic-pass-matrix td {{
                border-bottom: 1px solid #E2E8F0;
                border-right: 1px solid #E2E8F0;
                padding: 0.42rem 0.28rem;
                text-align: center;
                vertical-align: middle;
            }}
            .diagnostic-pass-matrix th:first-child,
            .diagnostic-pass-matrix td:first-child {{
                border-left: 1px solid #E2E8F0;
            }}
            .diagnostic-pass-matrix thead th {{
                background: #EAF2F8;
                border-top: 1px solid #D7DEE8;
                color: var(--pbi-blue);
                font-weight: 700;
            }}
            .diagnostic-pass-matrix thead th:first-child {{
                border-top-left-radius: 8px;
            }}
            .diagnostic-pass-matrix thead th:last-child {{
                border-top-right-radius: 8px;
            }}
            .diagnostic-pass-matrix tbody th {{
                background: #FFFFFF;
                color: #0F172A;
                font-weight: 500;
                line-height: 1.18;
            }}
            .diag-status-pass {{
                background: #DDF4DD;
                color: #166534;
            }}
            .diag-status-watch {{
                background: #FEF3C7;
                color: #92400E;
            }}
            .diag-status-fail {{
                background: #FEE2E2;
                color: #991B1B;
            }}
            .diag-status-unavailable {{
                background: #F1F5F9;
                color: #64748B;
            }}
            .diag-tooltip-trigger {{
                border-radius: 4px;
                cursor: help;
                display: inline-block;
                outline: none;
                position: relative;
            }}
            .diag-tooltip-trigger:focus {{
                box-shadow: 0 0 0 2px rgba(0, 43, 92, 0.28);
            }}
            .diag-tooltip-text {{
                background: #0F172A;
                border-radius: 7px;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.22);
                color: #F8FAFC;
                font-weight: 500;
                left: 50%;
                line-height: 1.32;
                max-width: 320px;
                min-width: 230px;
                opacity: 0;
                padding: 0.58rem 0.66rem;
                pointer-events: none;
                position: absolute;
                text-align: left;
                top: calc(100% + 0.44rem);
                transform: translateX(-50%);
                transition: opacity 120ms ease, visibility 120ms ease;
                visibility: hidden;
                white-space: normal;
                z-index: 9999;
            }}
            .diag-tooltip-text::before {{
                border-bottom: 6px solid #0F172A;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                content: "";
                left: 50%;
                position: absolute;
                top: -6px;
                transform: translateX(-50%);
            }}
            .diag-tooltip-trigger:hover .diag-tooltip-text,
            .diag-tooltip-trigger:focus .diag-tooltip-text,
            .diag-tooltip-trigger:focus-within .diag-tooltip-text {{
                opacity: 1;
                visibility: visible;
            }}
            .diag-info {{
                color: #64748B;
                font-size: 0.72rem;
                margin-left: 0.12rem;
            }}
            .diagnostic-matrix-legend {{
                color: #64748B;
                font-size: 0.76rem;
                margin-top: 0.34rem;
            }}
            .chart-card-caption-placeholder {{
                height: 0;
                margin: 0;
                overflow: hidden;
                padding: 0;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def header(title: str, subtitle: str | None = None, page_chip: str = "NLTF Stage 1") -> None:
    st.markdown(
        "<div class='gov-header governance-shell'><div class='governance-masthead'>"
        f"<div class='brand-lockup'>{_brand_logo_html()}</div>"
        "<div>"
        f"<div class='pbi-header'>{html.escape(title)}</div>"
        f"<div class='pbi-subtle masthead-subtitle'>{html.escape(subtitle or '')}</div>"
        "</div>"
        f"<div class='page-chip'>{html.escape(page_chip)}</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )


def section_title(title: str) -> None:
    st.markdown(f'<div class="pbi-section-title">{html.escape(title)}</div>', unsafe_allow_html=True)


def info_panel(text: str) -> None:
    st.markdown(f'<div class="info-panel">{html.escape(text)}</div>', unsafe_allow_html=True)


def warning_panel(text: str) -> None:
    st.markdown(f'<div class="warning-panel">{html.escape(text)}</div>', unsafe_allow_html=True)


def page_indicator(label: str) -> None:
    st.markdown(f'<div class="pbi-subtle" style="text-align:right;font-weight:700;">{html.escape(label)}</div>', unsafe_allow_html=True)


def filter_chips(chips: Iterable[tuple[str, str]]) -> None:
    html_chips = "".join(
        f"<span class='filter-chip'>{html.escape(label)}: {html.escape(value)}</span>" for label, value in chips
    )
    st.markdown(html_chips, unsafe_allow_html=True)


def filter_summary_grid(items: Iterable[tuple[str, str]]) -> None:
    cells = []
    for label, value in items:
        cells.append(
            "<div class='gov-filter-item'>"
            f"<div class='gov-filter-label'>{html.escape(label)}</div>"
            "<div class='gov-filter-value'>"
            f"<span class='gov-filter-display'>{html.escape(label)}: {html.escape(value)}</span>"
            "<span class='gov-filter-caret'>⌄</span>"
            "</div>"
            "</div>"
        )
    st.markdown("<div class='gov-filter-grid'>" + "".join(cells) + "</div>", unsafe_allow_html=True)


def _chart_card_header_html(title: str, subtitle: str, caption: str | None, *, notes_as_tooltip: bool) -> str:
    if not notes_as_tooltip:
        return (
            f"<div class='chart-card-title'>{html.escape(title)}</div>"
            f"<div class='chart-card-subtitle'>{html.escape(subtitle)}</div>"
        )
    info_parts = [part.strip() for part in [subtitle, caption or ""] if part and part.strip()]
    if not info_parts:
        return f"<div class='chart-card-header'><div class='chart-card-title'>{html.escape(title)}</div></div>"
    info_text = "\n\n".join(info_parts)
    return (
        "<div class='chart-card-header'>"
        f"<div class='chart-card-title'>{html.escape(title)}</div>"
        "<span class='chart-info-trigger' tabindex='0' aria-label='Chart information'>?"
        f"<span class='chart-info-text' role='tooltip'>{html.escape(info_text)}</span>"
        "</span>"
        "</div>"
    )


def chart_card(
    title: str,
    subtitle: str,
    figure: Any,
    caption: str | None = None,
    *,
    notes_as_tooltip: bool = True,
) -> None:
    key = "chart_card_" + re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    if hasattr(figure, "update_layout"):
        figure.update_layout(title_text="")
    with st.container(border=True):
        st.markdown(
            "<div class='gov-chart-card chart-card'>"
            f"{_chart_card_header_html(title, subtitle, caption, notes_as_tooltip=notes_as_tooltip)}"
            "</div>",
            unsafe_allow_html=True,
        )
        st.plotly_chart(figure, width="stretch", key=key)
        if caption and not notes_as_tooltip:
            st.caption(caption)
        else:
            st.markdown("<div class='chart-card-caption-placeholder'></div>", unsafe_allow_html=True)


def html_chart_card(
    title: str,
    subtitle: str,
    body_html: str,
    caption: str | None = None,
    *,
    notes_as_tooltip: bool = True,
) -> None:
    with st.container(border=True):
        st.markdown(
            "<div class='gov-chart-card chart-card'>"
            f"{_chart_card_header_html(title, subtitle, caption, notes_as_tooltip=notes_as_tooltip)}"
            f"{body_html}"
            "</div>",
            unsafe_allow_html=True,
        )
        if caption and not notes_as_tooltip:
            st.caption(caption)
        else:
            st.markdown("<div class='chart-card-caption-placeholder'></div>", unsafe_allow_html=True)


def footer_strip(left: str, right: str) -> None:
    st.markdown(
        "<div class='footer-strip'>"
        f"<span>{html.escape(left)}</span>"
        f"<span>{html.escape(right)}</span>"
        "</div>",
        unsafe_allow_html=True,
    )


def gov_kpi_grid(cards: Iterable[tuple[str, str, str | None, str | None, str | None, str | None]]) -> None:
    html_cards = []
    for title, value, subtext, delta, tone, icon in cards:
        delta_color = {
            "good": "#00843D",
            "bad": "#B42318",
            "mixed": "#F37021",
        }.get(tone or "good", "#00843D")
        html_cards.append(
            "<div class='gov-kpi-card'>"
            f"<div class='gov-kpi-icon'>{html.escape(icon or '*')}</div>"
            "<div>"
            f"<div class='kpi-title'>{html.escape(title)}</div>"
            f"<div class='kpi-value'>{html.escape(value)}</div>"
            f"<div class='kpi-sub'>{html.escape(subtext or '')}</div>"
            f"<div class='gov-kpi-delta' style='color:{delta_color}'>{html.escape(delta or '')}</div>"
            "</div></div>"
        )
    st.markdown("<div class='gov-kpi-grid'>" + "".join(html_cards) + "</div>", unsafe_allow_html=True)


def decision_brief(title: str, narrative: str, cards: Iterable[tuple[str, str, str | None]]) -> None:
    metric_html = []
    for label, value, subtext in cards:
        metric_html.append(
            "<div class='decision-metric'>"
            f"<div class='decision-label'>{html.escape(label)}</div>"
            f"<div class='decision-value'>{html.escape(value)}</div>"
            f"<div class='decision-sub'>{html.escape(subtext or '')}</div>"
            "</div>"
        )
    st.markdown(
        "<div class='decision-brief'>"
        "<div class='decision-kicker'>Enterprise readiness view</div>"
        f"<div class='decision-title'>{html.escape(title)}</div>"
        f"<div class='decision-copy'>{html.escape(narrative)}</div>"
        "<div class='decision-grid'>"
        + "".join(metric_html)
        + "</div></div>",
        unsafe_allow_html=True,
    )


def kpi_grid(cards: Iterable[tuple[str, str, str | None]]) -> None:
    html_cards = []
    for title, value, subtext in cards:
        html_cards.append(
            "<div class='kpi-card'>"
            f"<div class='kpi-title'>{html.escape(title)}</div>"
            f"<div class='kpi-value'>{html.escape(value)}</div>"
            f"<div class='kpi-sub'>{html.escape(subtext or '')}</div>"
            "</div>"
        )
    st.markdown("<div class='kpi-grid'>" + "".join(html_cards) + "</div>", unsafe_allow_html=True)


def badge(label: str, tone: str) -> str:
    css = {"good": "badge-good", "mixed": "badge-mixed", "bad": "badge-bad"}.get(tone, "badge-mixed")
    return f"<span class='badge {css}'>{html.escape(label)}</span>"


def governance_cards(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        st.caption("No finalist governance summary is available.")
        return
    cards = []
    status_labels = {
        "Beats Schiff": "Beats Schiff specification benchmark",
        "Does not beat Schiff": "Does not beat Schiff specification benchmark",
    }
    for _, row in df.iterrows():
        stream = html.escape(str(row.get("stream_label", "Unknown")))
        model = html.escape(model_alias(row.get("winning_model", ""), 68))
        q_mape = _format_percent(row.get("quarterly_mape"))
        annual_mape = _format_percent(row.get("annual_mape"))
        schiff_status = status_labels.get(str(row.get("schiff_status", "Not verified")), str(row.get("schiff_status", "Not verified")))
        schiff = badge(schiff_status, str(row.get("schiff_tone", "mixed")))
        robustness = badge(str(row.get("robustness_status", "Not verified")), str(row.get("robustness_tone", "mixed")))
        schiff_summary = html.escape(str(row.get("schiff_summary", row.get("schiff_evidence", ""))))
        warning = html.escape(str(row.get("warning_summary", "No warning summary available.")))
        cards.append(
            "<div class='story-card'>"
            f"<div class='story-stream'>{stream}</div>"
            f"{schiff}{robustness}"
            "<div class='story-question'>Which model won?</div>"
            f"<div class='story-model'>{model}</div>"
            f"<div class='story-stat'>Quarterly MAPE {q_mape} | Annual MAPE {annual_mape}</div>"
            "<div class='story-question'>Did it beat the Schiff specification benchmark?</div>"
            f"<div class='story-stat'>{schiff_summary}</div>"
            "<div class='story-question'>Warnings</div>"
            f"<div class='story-stat'>{warning}</div>"
            "</div>"
        )
    st.markdown("<div class='story-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def dataframe_download(df: pd.DataFrame, label: str, filename: str) -> None:
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label, csv, file_name=filename, mime="text/csv")


def display_table(
    df: pd.DataFrame,
    *,
    caption: str | None = None,
    height: int | None = 360,
    max_rows: int | None = 500,
) -> None:
    """Render a tidy management-review table with consistent formatting."""
    if df is None or df.empty:
        st.caption("No rows to display.")
        return
    view = df.copy()
    was_limited = max_rows is not None and len(view) > max_rows
    if max_rows is not None:
        view = view.head(max_rows)
    for col in view.columns:
        lower = str(col).lower()
        if any(token in lower for token in ("model", "challenger", "baseline", "component")):
            view[col] = view[col].map(lambda value: _short_text(value, 96))
    column_config = {}
    for col in view.columns:
        lower = str(col).lower()
        if any(token in lower for token in ("mape", "bias", "p90", "gain", "win rate", "weight")):
            column_config[col] = st.column_config.NumberColumn(str(col), format="%.2f")
        elif lower in {"rows", "columns", "common pairs", "n_common_pairs", "n_pairs"}:
            column_config[col] = st.column_config.TextColumn(str(col))
        else:
            column_config[col] = st.column_config.TextColumn(str(col))
    if caption:
        st.markdown(f'<div class="table-caption">{html.escape(caption)}</div>', unsafe_allow_html=True)
    if was_limited:
        st.caption(f"Showing first {max_rows:,} of {len(df):,} rows. Use the download control where available for the full filtered dataset.")
    st.dataframe(
        view,
        width="stretch",
        height=height,
        hide_index=True,
        column_config=column_config,
    )


def _short_text(value: object, max_length: int) -> str:
    text = "" if value is None else str(value)
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip("_- ") + "..."


def _format_percent(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if number != number:
        return "-"
    return f"{number:.2f}%"
