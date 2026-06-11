"""NLTF Stage 1 vNext production model pipeline.

Forecast-ready, fit-and-save finalist pipeline for the PED and Heavy RUC
streams (with Light RUC re-export), built on the canonical repo input
history at ``data/model_input_history``.

Modules:
    vnext_core        deterministic feature engineering, backtest engine, metrics
    vnext_candidates  governed candidate grids (locked-spec refits + challengers)
    vnext_run         CLI orchestrator (search -> select -> finalize -> forecast -> evidence)
    vnext_forward     fixed-finalist forward scorer for future assumption workbooks
"""

PIPELINE_VERSION = "vnext-pipeline-v1.0"
