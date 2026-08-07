"""Assurance for the two CI safety components that have already produced bugs.

Both of these are now load-bearing, and both were wrong on their first real run:

  * ``scripts/assert_governed_tree_unchanged.py`` initially compared absolute
    git state rather than the delta, so it failed on any branch that was already
    dirty - a gate that cries wolf gets switched off.

  * ``scripts/plan_governed_pack_rebuilds.py`` imported
    ``bridge_vintage_id_from_manifest`` from the wrong module, and treated the
    uncertainty manifest's ``source_files`` as a hash map when its values are
    provenance prose. That second bug reported a clean pack as STALE, which with
    ``--fail-on-stale`` in the hosted fast lane would have failed every CI run.

So they get tests. The cleanliness gate in particular is the only thing standing
between a silent governed-value mutation and a green build - see
``artifacts/ci_optimisation/xdist_benchmark.md`` for the incident that produced
it.

These tests are deliberately fast and hermetic: the gate tests build throwaway
git repositories in tmp_path rather than mutating this checkout, because a test
for a mutation detector must not itself mutate anything.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import assert_governed_tree_unchanged as gate  # noqa: E402
import plan_governed_pack_rebuilds as packs  # noqa: E402


# ===========================================================================
# scripts/assert_governed_tree_unchanged.py
# ===========================================================================


def _git(repo: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return result.stdout


@pytest.fixture
def sandbox(tmp_path: pathlib.Path) -> pathlib.Path:
    """A throwaway git repo shaped like this one: tracked files plus data/."""
    repo = tmp_path / "repo"
    (repo / "data" / "pack").mkdir(parents=True)
    (repo / "artifacts").mkdir()
    (repo / "model_dashboard").mkdir()

    (repo / "tracked.txt").write_text("original\n", encoding="utf-8")
    (repo / "model_dashboard" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "artifacts" / "governed.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    # Gitignored but governed: exactly the content a tracked-only check misses.
    (repo / "data" / "pack" / "values.parquet").write_bytes(b"\x00governed-bytes")
    (repo / ".gitignore").write_text("data/**\n", encoding="utf-8")

    _git(repo.parent, "init", "-q", str(repo))
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "initial")
    return repo


def snapshot_to(repo: pathlib.Path, path: pathlib.Path) -> None:
    assert gate.main(["--repo-root", str(repo), "--snapshot", str(path)]) == 0


def verify(repo: pathlib.Path, path: pathlib.Path) -> int:
    return gate.main(["--repo-root", str(repo), "--verify", str(path)])


def test_clean_lane_passes(sandbox, tmp_path):
    before = tmp_path / "before.json"
    snapshot_to(sandbox, before)
    assert verify(sandbox, before) == 0


def test_preexisting_dirt_does_not_create_a_false_failure(sandbox, tmp_path):
    """A developer's already-modified branch is not a test failure.

    This is the bug the gate shipped with. A gate that fails on every working
    branch is a gate that gets disabled, and then it protects nothing.
    """
    (sandbox / "tracked.txt").write_text("developer edit\n", encoding="utf-8")

    before = tmp_path / "before.json"
    snapshot_to(sandbox, before)  # snapshot taken WITH the dirt already present
    assert verify(sandbox, before) == 0, (
        "pre-existing modifications must not be reported as caused by this lane"
    )


def test_new_tracked_file_modification_is_detected(sandbox, tmp_path, capsys):
    before = tmp_path / "before.json"
    snapshot_to(sandbox, before)

    (sandbox / "model_dashboard" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    assert verify(sandbox, before) == 1
    err = capsys.readouterr().err
    assert "GOVERNED TREE MUTATED" in err
    assert "model_dashboard/module.py" in err


def test_gitignored_governed_data_file_is_detected(sandbox, tmp_path, capsys):
    """data/ is mostly gitignored, and is exactly where a pack would move.

    A tracked-only check would pass here, which is why the gate hashes data/
    whether git is watching it or not.
    """
    before = tmp_path / "before.json"
    snapshot_to(sandbox, before)

    (sandbox / "data" / "pack" / "values.parquet").write_bytes(b"\x00moved-bytes")

    assert verify(sandbox, before) == 1
    err = capsys.readouterr().err
    assert "data/pack/values.parquet" in err
    # git itself sees nothing here - the hash map is the only detector.
    assert "data/pack/values.parquet" not in _git(sandbox, "status", "--porcelain")


def test_same_path_content_movement_reports_before_and_after_hashes(
    sandbox, tmp_path, capsys
):
    """The incident was a same-path rewrite, not an added or deleted file."""
    before = tmp_path / "before.json"
    snapshot_to(sandbox, before)

    original = json.loads(before.read_text(encoding="utf-8"))["hashes"][
        "artifacts/governed.csv"
    ]
    (sandbox / "artifacts" / "governed.csv").write_text("a,b\n1,3\n", encoding="utf-8")

    assert verify(sandbox, before) == 1
    err = capsys.readouterr().err
    assert "artifacts/governed.csv" in err
    assert "before" in err and "after" in err
    assert original[:16] in err, "the diagnostic must name the hash it expected"


def test_deleted_governed_file_is_detected(sandbox, tmp_path, capsys):
    before = tmp_path / "before.json"
    snapshot_to(sandbox, before)

    (sandbox / "data" / "pack" / "values.parquet").unlink()

    assert verify(sandbox, before) == 1
    assert "values.parquet" in capsys.readouterr().err


def test_writing_to_an_allowed_scratch_path_is_not_a_failure(sandbox, tmp_path):
    """Tiers legitimately write results; those paths must not trip the gate."""
    before = tmp_path / "before.json"
    snapshot_to(sandbox, before)

    scratch = sandbox / "artifacts" / "ci_local" / "abc123"
    scratch.mkdir(parents=True)
    (scratch / "result_full.json").write_text("{}", encoding="utf-8")
    (sandbox / "test-output").mkdir()
    (sandbox / "test-output" / "tmp.txt").write_text("scratch", encoding="utf-8")

    assert verify(sandbox, before) == 0


def test_curated_data_rebuild_is_allowed(sandbox, tmp_path):
    """Every tier regenerates curated data before running; that is by design."""
    before = tmp_path / "before.json"
    snapshot_to(sandbox, before)

    curated = sandbox / "artifacts" / "curated_data"
    curated.mkdir(parents=True)
    (curated / "finalist_accuracy.csv").write_text("x\n1\n", encoding="utf-8")

    assert verify(sandbox, before) == 0


def test_snapshot_records_git_state_for_delta_comparison(sandbox, tmp_path):
    before = tmp_path / "before.json"
    snapshot_to(sandbox, before)
    payload = json.loads(before.read_text(encoding="utf-8"))
    assert "hashes" in payload and "git" in payload, (
        "the snapshot must carry git state, or pre-existing dirt cannot be "
        "distinguished from dirt this lane caused"
    )


# ===========================================================================
# scripts/plan_governed_pack_rebuilds.py
# ===========================================================================


@pytest.fixture(scope="module")
def live_plan() -> dict:
    """The plan for the committed checkout. Read-only; rebuilds nothing."""
    return packs.build_plan(REPO_ROOT)


def test_all_five_packs_are_reported(live_plan):
    assert set(live_plan["packs"]) == {
        "replay_cache",
        "quarterly_display",
        "uncertainty",
        "policy_runtime",
        "databricks_bundle",
    }


def test_committed_checkout_reports_every_pack_current(live_plan):
    """The committed packs must be current, and the planner must say so.

    This is the test that would have caught the provenance-prose bug: it
    reported `uncertainty` stale on a clean tree, which with --fail-on-stale in
    the hosted fast lane would have failed every single CI run.
    """
    not_ok = {
        name: record["status"]
        for name, record in live_plan["packs"].items()
        if record["status"] not in ("ok", "not affected")
    }
    assert not not_ok, f"packs unexpectedly not current on the committed tree: {not_ok}"
    assert not live_plan["any_stale"]
    assert live_plan["required_rebuilds"] == []


def test_status_check_that_raises_is_reported_as_corrupt_not_ok(monkeypatch):
    """A status check that cannot run must never be mistaken for a pass."""

    def explode(_root):
        raise RuntimeError("simulated: manifest unreadable")

    monkeypatch.setattr(packs, "status_replay_cache", explode)
    plan = packs.build_plan(REPO_ROOT)
    assert plan["packs"]["replay_cache"]["status"] == "corrupt"
    assert plan["any_stale"]
    assert "replay_cache" in plan["required_rebuilds"]


def test_missing_pack_manifest_reports_missing(tmp_path):
    """A repository root with no packs must report missing, not ok."""
    empty = tmp_path / "empty"
    (empty / "data").mkdir(parents=True)
    assert packs.status_quarterly_display(empty)["status"] == "missing"
    assert packs.status_uncertainty(empty)["status"] == "missing"


def test_uncertainty_never_infers_staleness_from_provenance_prose(tmp_path):
    """source_files values are descriptions, not paths or hashes.

    e.g. "data/current_revenue_outlook (line reconciliation, current_basecase)".
    Treating them as paths made every clean tree look stale.
    """
    root = tmp_path / "repo"
    pack = root / "data" / "revenue_outlook_uncertainty"
    pack.mkdir(parents=True)
    (pack / "manifest.json").write_text(
        json.dumps(
            {
                "scenario_key_digest": "b5ce7ab7a3ef0000",
                "band_rows": 1000,
                "source_files": {
                    "june_year_errors": "artifacts/long_horizon_validation/x.csv",
                    "central_path": "data/current_revenue_outlook (line reconciliation)",
                },
            }
        ),
        encoding="utf-8",
    )
    record = packs.status_uncertainty(root)
    assert record["status"] == "ok", (
        "prose source_files must not be read as missing files: " + record["detail"]
    )
    assert "policy_runtime" in record["detail"], (
        "the record must say where freshness is actually enforced, so an 'ok' "
        "here is not mistaken for an independent freshness proof"
    )


def test_uncertainty_without_a_chainable_digest_is_corrupt_not_ok(tmp_path):
    """Its 'ok' is only meaningful because policy_runtime chains this digest.

    With no digest to chain, policy_runtime cannot detect a regenerated
    uncertainty pack, so reporting ok here would be a false negative on the one
    dependency the status relies on.
    """
    root = tmp_path / "repo"
    pack = root / "data" / "revenue_outlook_uncertainty"
    pack.mkdir(parents=True)
    (pack / "manifest.json").write_text(json.dumps({"band_rows": 10}), encoding="utf-8")

    record = packs.status_uncertainty(root)
    assert record["status"] == "corrupt"
    assert "scenario_key_digest" in record["detail"]


def test_rebuild_order_is_the_dependency_chain():
    assert packs.REBUILD_ORDER == [
        "replay_cache",
        "quarterly_display",
        "uncertainty",
        "policy_runtime",
        "databricks_bundle",
    ]


def test_a_stale_upstream_pack_cascades_to_everything_downstream(monkeypatch):
    """Rebuilding replay_cache invalidates every pack whose digest chains it."""

    monkeypatch.setattr(
        packs, "status_replay_cache", lambda _root: {"status": "stale", "detail": "test"}
    )
    plan = packs.build_plan(REPO_ROOT)
    assert plan["required_rebuilds"] == packs.REBUILD_ORDER, (
        "a stale replay cache must cascade through the whole chain"
    )
    orders = [plan["packs"][n]["order"] for n in packs.REBUILD_ORDER]
    assert orders == sorted(orders), "rebuild order must follow the dependency chain"


def test_a_late_stale_pack_does_not_rebuild_its_upstreams(monkeypatch):
    """Only affected packs rebuild. A nearby change is not a reason."""

    monkeypatch.setattr(
        packs,
        "status_policy_runtime",
        lambda _root: {"status": "stale", "detail": "test"},
    )
    plan = packs.build_plan(REPO_ROOT)
    assert plan["required_rebuilds"] == ["policy_runtime", "databricks_bundle"]
    for upstream in ("replay_cache", "quarterly_display", "uncertainty"):
        assert not plan["packs"][upstream]["required"], (
            f"{upstream} is upstream of policy_runtime and must not be rebuilt"
        )


def test_databricks_bundle_is_blocked_while_any_upstream_pack_is_not_ok(monkeypatch):
    """Publishing a bundle built on stale packs would ship stale content."""

    monkeypatch.setattr(
        packs, "status_uncertainty", lambda _root: {"status": "stale", "detail": "test"}
    )
    plan = packs.build_plan(REPO_ROOT)
    bundle = plan["packs"]["databricks_bundle"]
    assert bundle["status"] == "affected"
    assert "uncertainty" in bundle["detail"]


def test_no_second_idempotency_build_by_default(live_plan):
    assert live_plan["second_idempotency_build_required"] is False
    assert "builder code" in live_plan["second_build_reason"]


def test_fail_on_stale_exits_zero_when_packs_are_current():
    assert packs.main(["--fail-on-stale", "--format", "json"]) == 0


# ===========================================================================
# Wiring: the gate must actually be attached to every lane
# ===========================================================================


def test_hosted_post_test_cleanliness_steps_use_if_always():
    """A verify step that is skipped when the suite fails proves nothing.

    A failing suite is exactly when half-written scratch is most likely to be
    left behind, so the check has to run then too.
    """
    import yaml

    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    checked = 0
    for job_name, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            if "assert_governed_tree_unchanged.py --verify" in str(step.get("run", "")):
                assert step.get("if") == "always()", (
                    f"{job_name}: the cleanliness verify step must use if: always()"
                )
                checked += 1
    assert checked >= 3, (
        f"expected the gate in fast, affected and full-assurance; found {checked}"
    )


def test_every_hosted_job_that_runs_pytest_also_snapshots_and_verifies():
    import yaml

    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    for job_name, job in workflow["jobs"].items():
        runs = " ".join(str(step.get("run", "")) for step in job.get("steps", []))
        if "pytest" not in runs:
            continue
        assert "--snapshot" in runs, f"{job_name} runs pytest without snapshotting"
        assert "--verify" in runs, f"{job_name} runs pytest without verifying"


def test_local_entrypoint_verifies_on_every_exit_path():
    """The container gate is an EXIT trap, not a call after the suite.

    An explicit post-suite call would miss the steps that run after it - and in
    the full tier those include a materialisation step that writes packs.
    """
    text = (REPO_ROOT / "ci" / "entrypoint.sh").read_text(encoding="utf-8")
    assert "trap gate_on_exit EXIT" in text
    assert "gate_arm" in text
    # A mutated lane must not report success...
    assert "exit 3" in text
    # ...but must not mask a genuine test failure either.
    assert 'exit "$original"' in text


def test_local_powershell_wrapper_checks_in_finally():
    text = (REPO_ROOT / "scripts" / "ci_local.ps1").read_text(encoding="utf-8")
    finally_block = text.split("finally {", 1)[1]
    assert "status --porcelain" in finally_block, (
        "the mutation check must survive an interrupted or crashed run"
    )
    assert "$ExitCode = 3" in finally_block


@pytest.mark.parametrize(
    "relative",
    [
        "ci/entrypoint.sh",
        "ci/install_docker_engine_wsl.sh",
        "ci/benchmark_test_parallelism.sh",
        "scripts/ci_local.sh",
    ],
)
def test_shell_scripts_use_lf_line_endings(relative):
    """A CRLF shell script cannot run in the container at all.

    .gitattributes pins `* -text`, so git stores whatever bytes it is given and
    will not normalise this on the way out. A script authored or rewritten on
    Windows therefore reaches Linux with CRLF, and the kernel tries to execute
    an interpreter literally named "bash\\r":

        /usr/bin/env: 'bash\\r': No such file or directory

    That is not a subtle failure, but it is an easy one to reintroduce - it
    happened here when a maintenance edit used Python's text-mode write.
    """
    data = (REPO_ROOT / relative).read_bytes()
    assert b"\r\n" not in data, (
        f"{relative} has CRLF line endings and will not execute in the Linux "
        "container. Convert it to LF."
    )
