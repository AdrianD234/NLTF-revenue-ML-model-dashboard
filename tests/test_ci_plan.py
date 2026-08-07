"""The change classifier's own assurance.

These tests exist because ci_plan.py is the thing that decides whether a
governed change gets tested at all. A classifier that silently returns "nothing
to run" for a promoted fitted state would be worse than no classifier, so the
cases below pin the expensive answers, not just the cheap ones.

Three families:

  * coverage    - every top-level directory currently in the repository
                  resolves to an explicit scope, so a new area cannot appear
                  without either a rule or a high-risk escalation.
  * roadmap     - the forthcoming work categories land in the lane the CI
                  design assigns them.
  * fail-safe   - unclassified, oversized and unreadable diffs escalate.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import ci_plan  # noqa: E402


@pytest.fixture(scope="module")
def config() -> dict:
    return ci_plan.load_config()


def plan_for(files, config, event="pull_request") -> dict:
    return ci_plan.plan(sorted(files), config, event=event)


# ---------------------------------------------------------------------------
# Config integrity
# ---------------------------------------------------------------------------


def test_every_test_group_path_exists(config):
    """A renamed test file must fail here, not silently select nothing."""
    missing = []
    for group, spec in config["test_groups"].items():
        for path in spec["paths"]:
            if not (REPO_ROOT / path).exists():
                missing.append(f"{group} -> {path}")
    assert not missing, "test groups reference paths that no longer exist:\n" + "\n".join(
        missing
    )


def test_every_scope_is_reachable_from_some_rule(config):
    """A scope nothing can match is dead configuration pretending to be cover."""
    reachable = {scope for rule in config["rules"] for scope in rule["scopes"]}
    # unknown_high_risk is reached by escalation, never by a pattern.
    reachable.add("unknown_high_risk")
    unreachable = set(config["scopes"]) - reachable
    assert not unreachable, f"scopes no rule can produce: {sorted(unreachable)}"


def test_all_fourteen_required_scopes_are_defined(config):
    required = {
        "docs_only",
        "dashboard_ui",
        "revenue_outlook_presentation",
        "revenue_outlook_calculation",
        "uncertainty",
        "governed_pack",
        "data_refresh",
        "model_experiment",
        "model_promotion",
        "replay_or_fitted_state",
        "dependency_or_environment",
        "ci_or_workflow",
        "databricks_bundle",
        "unknown_high_risk",
    }
    assert required <= set(config["scopes"])


# ---------------------------------------------------------------------------
# Coverage: no top-level area is unclassified by accident
# ---------------------------------------------------------------------------


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def test_every_tracked_file_resolves_to_a_scope(config):
    """No tracked file may be unclassified.

    Unclassified files still escalate to full assurance at runtime, so this is
    not a correctness hole - but an escalation that fires on ordinary committed
    content would make every change expensive, which defeats the design.
    """
    unclassified = [
        path for path in tracked_files() if not ci_plan.classify_file(path, config)
    ]
    assert not unclassified, (
        f"{len(unclassified)} tracked file(s) match no rule and would force full "
        "assurance on every change:\n" + "\n".join(sorted(unclassified)[:40])
    )


def test_every_top_level_directory_is_classified(config):
    """Each top-level directory has at least one representative that classifies."""
    tops = sorted({path.split("/")[0] for path in tracked_files() if "/" in path})
    unclassified = []
    for top in tops:
        members = [p for p in tracked_files() if p.startswith(top + "/")]
        if not any(ci_plan.classify_file(p, config) for p in members):
            unclassified.append(top)
    assert not unclassified, f"top-level directories with no classified member: {unclassified}"


# ---------------------------------------------------------------------------
# Roadmap routing
# ---------------------------------------------------------------------------


def test_docs_only_change_runs_no_model_work(config):
    result = plan_for(["docs/ARCHITECTURE.md", "README.md"], config)
    assert result["scopes"] == ["docs_only"]
    assert result["risk_level"] == "none"
    assert not result["requires_full_assurance"]
    assert not result["requires_linux_replay"]
    assert not result["requires_windows_replay"]


def test_docs_alongside_source_loses_the_cheap_lane(config):
    """The docs lane is only cheap when the diff is genuinely only docs."""
    result = plan_for(["README.md", "model_dashboard/revenue_outlook.py"], config)
    assert "docs_only" not in result["scopes"]
    assert "revenue_outlook_calculation" in result["scopes"]


@pytest.mark.parametrize(
    "changed, expected_scope",
    [
        # Nominal-rather-than-NPV default, scenario titles, captions.
        ("model_dashboard/revenue_outlook_presentation_policy.py", "revenue_outlook_presentation"),
        ("model_dashboard/ui.py", "dashboard_ui"),
        # Treasury / PREFU refresh and new actuals.
        ("data/source_workbooks/Master Copy revenue modelling workbook.xlsx", "data_refresh"),
        ("data/model_input_history/light_ruc_inputs.parquet", "data_refresh"),
        # PED calibration R-squared drift.
        ("model_dashboard/r2_ladder.py", "governance_r2"),
        ("model_dashboard/score_basis.py", "governance_r2"),
        # COVID dummies, seasonality, interactions, exports/imports, lagged GDP,
        # clean-car discount, explainable challengers, heavy-RUC consumption,
        # smoothed VKT per capita - all local experiments.
        ("experiments/configs/covid_two_year_dummy.yml", "model_experiment"),
        ("experiments/results/seasonality_drop/metrics.json", "model_experiment"),
        # Error bands excluding COVID.
        ("model_dashboard/revenue_uncertainty_draws.py", "uncertainty"),
        ("model_dashboard/revenue_uncertainty_policy.py", "uncertainty"),
        # Promoted model / fitted state.
        ("data/engine_ar1/current_revenue_outlook/state.parquet", "replay_or_fitted_state"),
        ("pipeline/ar1_engine.py", "replay_or_fitted_state"),
        ("pipeline/vnext_candidates.py", "model_promotion"),
        # Coefficients through time is research on a promoted finalist.
        ("model_dashboard/metrics.py", "governance_r2"),
        # Docs and the theoretical funding piece.
        ("docs/GOVERNANCE_RULES.md", "docs_only"),
    ],
)
def test_roadmap_item_lands_in_its_lane(config, changed, expected_scope):
    result = plan_for([changed], config)
    assert expected_scope in result["scopes"], (
        f"{changed} classified as {result['scopes']}, expected {expected_scope}"
    )


def test_model_experiment_never_demands_hosted_assurance(config):
    """Permutation work must not consume hosted minutes."""
    result = plan_for(
        [
            "experiments/configs/covid_dummy.yml",
            "experiments/configs/no_seasonality.yml",
            "experiments/results/run_001/metrics.json",
        ],
        config,
    )
    assert result["scopes"] == ["model_experiment"]
    assert not result["requires_full_assurance"]
    assert not result["requires_linux_replay"]
    assert not result["requires_windows_replay"]
    assert result["required_test_paths"] == []


def test_app_py_is_never_docs_or_ui_only(config):
    """app.py wires pages to the governed runtime; it gets integration cover."""
    result = plan_for(["app.py"], config)
    assert "dashboard_ui" in result["scopes"]
    assert "revenue_outlook_presentation" in result["scopes"]
    assert "deployment" in result["scopes"]
    assert "policy_runtime" in result["required_pack_status_checks"]


# ---------------------------------------------------------------------------
# Fail-safe escalation
# ---------------------------------------------------------------------------


def test_unknown_python_file_escalates(config):
    result = plan_for(["model_dashboard/brand_new_module.py"], config)
    assert "unknown_high_risk" in result["scopes"]
    assert result["risk_level"] == "high"
    assert result["requires_full_assurance"]
    assert result["requires_linux_replay"]
    assert result["requires_windows_replay"]


def test_unknown_data_file_escalates(config):
    result = plan_for(["data/some_new_pack/values.parquet"], config)
    assert "unknown_high_risk" in result["scopes"]
    assert result["requires_full_assurance"]


def test_unknown_top_level_file_escalates(config):
    result = plan_for(["mystery.bin"], config)
    assert "unknown_high_risk" in result["scopes"]
    assert result["requires_full_assurance"]


def test_large_diff_escalates(config):
    threshold = config["failsafe"]["large_diff_file_threshold"]
    files = [f"docs/note_{i:04d}.md" for i in range(threshold + 1)]
    result = plan_for(files, config)
    assert "unknown_high_risk" in result["scopes"]
    assert result["requires_full_assurance"]
    assert any("not worth classifying" in r for r in result["reasons"])


@pytest.mark.parametrize(
    "changed",
    [
        "requirements.txt",
        "requirements-dev.txt",
        "runtime.txt",
        "sitecustomize.py",
        ".devcontainer/devcontainer.json",
        "ci/Dockerfile",
    ],
)
def test_environment_changes_demand_full_assurance_and_both_replays(config, changed):
    result = plan_for([changed], config)
    assert result["requires_full_assurance"], changed
    assert result["requires_linux_replay"], changed
    assert result["requires_windows_replay"], changed


@pytest.mark.parametrize(
    "changed",
    [
        "data/engine_ar1/state.parquet",
        "data/revenue_outlook_replay_cache/ar1/rows.parquet",
        "model_dashboard/engine.py",
        "model_dashboard/ped_forward.py",
        "model_dashboard/heavy_ruc_forward.py",
        "pipeline/ar1_engine.py",
        "scripts/replay_parity_fingerprint.py",
    ],
)
def test_fitted_state_and_numerical_model_demand_both_replay_platforms(config, changed):
    result = plan_for([changed], config)
    assert result["requires_full_assurance"], changed
    assert result["requires_linux_replay"], changed
    assert result["requires_windows_replay"], changed


def test_governed_pack_change_requests_pack_status_checks(config):
    result = plan_for(["data/revenue_outlook_policy_runtime/ar1/manifest.json"], config)
    assert "governed_pack" in result["scopes"]
    for check in ("replay_cache", "quarterly_display", "policy_runtime"):
        assert check in result["required_pack_status_checks"]


def test_databricks_bundle_change_requests_the_bundle_job(config):
    result = plan_for(["scripts/build_databricks_app_bundle.py"], config)
    assert result["requires_databricks_bundle"]


def test_changed_test_file_always_runs_itself(config):
    """Whatever a test's subject matter is, editing it selects it."""
    result = plan_for(["tests/test_npv.py"], config)
    assert "tests/test_npv.py" in result["required_test_paths"]


def test_classifier_failure_escalates_rather_than_returning_empty(config, monkeypatch):
    """An unreadable diff must demand everything, not select nothing."""

    def explode(*_args, **_kwargs):
        raise ci_plan.PlannerError("simulated: base ref missing from shallow clone")

    monkeypatch.setattr(ci_plan, "changed_files", explode)
    captured: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: captured.append(" ".join(map(str, a))))
    ci_plan.main(["--base", "nope", "--head", "HEAD", "--format", "json"])
    result = json.loads("".join(captured))
    assert result["requires_full_assurance"]
    assert result["requires_linux_replay"]
    assert result["requires_windows_replay"]
    assert result["scopes"] == ["unknown_high_risk"]


# ---------------------------------------------------------------------------
# Output contracts the workflow depends on
# ---------------------------------------------------------------------------


def test_github_output_emits_every_key_the_workflow_branches_on(config):
    result = plan_for(["model_dashboard/ui.py"], config)
    text = ci_plan.render_github_output(result)
    keys = {line.split("=", 1)[0] for line in text.splitlines()}
    assert {
        "requires_full_assurance",
        "requires_linux_replay",
        "requires_windows_replay",
        "requires_browser",
        "requires_databricks_bundle",
        "risk_level",
        "scopes",
        "test_paths",
        "pack_checks",
        "plan_json",
    } <= keys


def test_github_output_booleans_are_lowercase_yaml_truthy(config):
    """`if:` comparisons in the workflow are string equality against 'true'."""
    result = plan_for(["data/engine_ar1/state.parquet"], config)
    text = ci_plan.render_github_output(result)
    line = next(l for l in text.splitlines() if l.startswith("requires_full_assurance="))
    assert line == "requires_full_assurance=true"


def test_plan_json_round_trips(config):
    result = plan_for(["app.py"], config)
    text = ci_plan.render_github_output(result)
    blob = next(l for l in text.splitlines() if l.startswith("plan_json="))
    assert json.loads(blob.split("=", 1)[1])["scopes"] == result["scopes"]
