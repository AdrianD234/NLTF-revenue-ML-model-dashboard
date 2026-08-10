"""Prove a real Streamlit host process leaves the governed chart-source tree alone.

This is the host-level counterpart to ``tests/test_app_boot_read_only.py``. The
AppTest-level check runs inside pytest, which means it inherits the
``tests/conftest.py`` chart-source redirect - the very redirect that hid the
app-boot write path in the first place. This script deliberately runs *outside*
pytest: it starts a genuine ``streamlit run app.py`` server, drives it with a
real browser session (Streamlit does not execute the script until a websocket
client connects), stops it, and requires every file under
``artifacts/chart_sources`` to be byte-identical afterwards.

Usage::

    python scripts/check_app_boot_read_only.py --repo-root <path> [--json-out r.json]

Exit code 0 means the governed tree was untouched.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_SERVER_TIMEOUT = 240.0
DEFAULT_RENDER_TIMEOUT = 420.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", required=True, help="Checkout whose app.py is started.")
    parser.add_argument("--python", default=sys.executable, help="Interpreter used to run Streamlit.")
    parser.add_argument("--port", type=int, default=0, help="0 picks a free port.")
    parser.add_argument("--json-out", default=None, help="Where to write the machine-readable report.")
    parser.add_argument(
        "--cache-warmer",
        choices=("default", "off"),
        default="default",
        help="'default' preserves normal local startup (warmer on). 'off' sets REVENUE_OUTLOOK_CACHE_WARMER=0.",
    )
    parser.add_argument("--engine-default", default=None, help="Value for DASHBOARD_ENGINE_DEFAULT (unset by default).")
    parser.add_argument("--server-timeout", type=float, default=DEFAULT_SERVER_TIMEOUT)
    parser.add_argument("--render-timeout", type=float, default=DEFAULT_RENDER_TIMEOUT)
    parser.add_argument("--label", default="host-process", help="Label recorded in the report.")
    parser.add_argument(
        "--log-dir",
        default=None,
        help=(
            "Where the Streamlit server log is written. Defaults to a system temp directory, "
            "deliberately OUTSIDE --repo-root: this check also probes the Databricks bundle, whose "
            "manifest re-verification fails if the probe leaves files behind."
        ),
    )
    return parser.parse_args(argv)


# --------------------------------------------------------------------------- #
# Governed-tree snapshots
# --------------------------------------------------------------------------- #


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def snapshot_chart_sources(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Hash every file under artifacts/chart_sources, not just the R2 ladder."""
    chart_dir = repo_root / "artifacts" / "chart_sources"
    snapshot: dict[str, dict[str, Any]] = {}
    if not chart_dir.is_dir():
        return snapshot
    for path in sorted(chart_dir.rglob("*")):
        if path.is_file():
            snapshot[path.relative_to(repo_root).as_posix()] = {
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
    return snapshot


def git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "modified": sorted(name for name in set(before) & set(after) if before[name]["sha256"] != after[name]["sha256"]),
    }


# --------------------------------------------------------------------------- #
# Server lifecycle
# --------------------------------------------------------------------------- #


def free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def port_is_free(port: int) -> bool:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def build_env(args: argparse.Namespace) -> dict[str, str]:
    env = dict(os.environ)
    # Normal application configuration: the test-only redirect must not be set,
    # or this check would prove nothing.
    env.pop("NLTF_CHART_SOURCE_OUTPUT_DIR", None)
    env.pop("NLTF_CHART_SOURCE_OUTPUT_DIR_AUTOSET", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    env.pop("PYTEST_XDIST_WORKER", None)
    if args.engine_default is None:
        env.pop("DASHBOARD_ENGINE_DEFAULT", None)
    else:
        env["DASHBOARD_ENGINE_DEFAULT"] = args.engine_default
    if args.cache_warmer == "off":
        env["REVENUE_OUTLOOK_CACHE_WARMER"] = "0"
    else:
        env.pop("REVENUE_OUTLOOK_CACHE_WARMER", None)
    env["PYTHONIOENCODING"] = "utf-8"
    # Same convention as scripts/validate_databricks_app_bundle.py and
    # ci/Dockerfile.publish-probe: this check also probes the Databricks bundle,
    # and __pycache__ written into it fails the manifest re-verification. A
    # read-only check must not itself mutate what it is inspecting.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def start_server(args: argparse.Namespace, repo_root: Path, port: int, log_path: Path) -> subprocess.Popen:
    command = [
        args.python,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.port",
        str(port),
        "--server.address",
        "127.0.0.1",
        "--server.headless",
        "true",
        "--server.fileWatcherType",
        "none",
        "--browser.gatherUsageStats",
        "false",
        "--global.developmentMode",
        "false",
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8", errors="replace")
    return subprocess.Popen(
        command,
        cwd=str(repo_root),
        env=build_env(args),
        stdout=handle,
        stderr=subprocess.STDOUT,
    )


def wait_for_health(port: int, timeout: float, process: subprocess.Popen) -> None:
    url = f"http://127.0.0.1:{port}/_stcore/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Streamlit exited early with code {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - fixed localhost URL
                if response.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            time.sleep(1.0)
    raise TimeoutError(f"Streamlit health endpoint never answered within {timeout}s")


def stop_server(process: subprocess.Popen) -> int:
    if process.poll() is not None:
        return int(process.returncode)
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=30)
    return int(process.returncode)


# --------------------------------------------------------------------------- #
# Browser session
# --------------------------------------------------------------------------- #


def drive_browser(port: int, render_timeout: float, steps: list[str]) -> list[str]:
    """Boot, navigate, rerun and switch engine.

    ``steps`` is filled in place so a partial session still tells the caller how
    far the app got before failing.
    """
    from playwright.sync_api import sync_playwright

    timeout_ms = int(render_timeout * 1000)

    def settle(page, label: str) -> None:
        # Streamlit marks the running script with data-test-script-state.
        page.wait_for_selector('[data-testid="stApp"]', timeout=timeout_ms)
        try:
            page.wait_for_selector(
                '[data-testid="stApp"][data-test-script-state="notRunning"]',
                timeout=timeout_ms,
            )
        except Exception:
            # Older/newer Streamlit builds vary on this attribute; fall back to
            # waiting for the network to go quiet.
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
        page.wait_for_timeout(1500)
        steps.append(label)

    def click_radio(page, text: str, label: str) -> bool:
        """Click a Streamlit radio option.

        The <input type=radio> itself is visually hidden and sits outside the
        viewport, so Playwright refuses to click it. The clickable target is the
        surrounding <label>.
        """
        for locator in (
            page.locator("label").filter(has_text=text),
            page.get_by_text(text, exact=False),
        ):
            count = locator.count()
            for index in range(min(count, 4)):
                candidate = locator.nth(index)
                try:
                    candidate.scroll_into_view_if_needed(timeout=15_000)
                    candidate.click(timeout=15_000)
                except Exception:
                    continue
                settle(page, label)
                return True
        return False

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": 1600, "height": 1200})
            page = context.new_page()
            page.set_default_timeout(timeout_ms)
            page.goto(f"http://127.0.0.1:{port}", wait_until="domcontentloaded", timeout=timeout_ms)
            settle(page, "initial_boot")

            click_radio(page, "Revenue Outlook", "revenue_outlook_page")

            # A normal Streamlit rerun.
            page.keyboard.press("KeyR")
            settle(page, "rerun")

            # Engine switch, then back to the default engine.
            if click_radio(page, "ML ensemble", "engine_switch_to_ensemble"):
                click_radio(page, "AR(1) model", "engine_switch_back_to_ar1")

            # The Governance & Reproducibility page is the one that reads the
            # chart-source directory (it counts the CSVs for a status card).
            click_radio(page, "Governance", "governance_page")

            context.close()
        finally:
            browser.close()
    return steps


# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    if not (repo_root / "app.py").is_file():
        raise SystemExit(f"No app.py under {repo_root}")

    port = args.port or free_port()
    if not port_is_free(port):
        raise SystemExit(f"Port {port} is already in use; pick another with --port.")

    before = snapshot_chart_sources(repo_root)
    status_before = git(repo_root, "status", "--porcelain")

    log_dir = Path(args.log_dir) if args.log_dir else Path(tempfile.gettempdir()) / "nltf_app_boot_read_only"
    log_path = log_dir / f"streamlit-{port}.log"
    process = start_server(args, repo_root, port, log_path)
    steps: list[str] = []
    error: str | None = None
    try:
        wait_for_health(port, args.server_timeout, process)
        drive_browser(port, args.render_timeout, steps)
    except Exception as exc:  # noqa: BLE001 - the report needs the reason
        error = f"{type(exc).__name__}: {exc}"
    finally:
        exit_code = stop_server(process)

    after = snapshot_chart_sources(repo_root)
    status_after = git(repo_root, "status", "--porcelain")
    delta = diff_snapshots(before, after)
    unchanged = not any(delta.values())
    clean = status_after == status_before

    report = {
        "label": args.label,
        "repo_root": str(repo_root),
        "head_sha": git(repo_root, "rev-parse", "HEAD"),
        "port": port,
        "cache_warmer": args.cache_warmer,
        "engine_default_env": args.engine_default,
        "steps_exercised": steps,
        "server_exit_code": exit_code,
        "error": error,
        "files_before": len(before),
        "files_after": len(after),
        "delta": delta,
        "git_status_before": status_before,
        "git_status_after": status_after,
        "chart_sources_unchanged": unchanged,
        "git_status_unchanged": clean,
        "before": before,
        "after": after,
    }
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    summary = {k: v for k, v in report.items() if k not in {"before", "after"}}
    print(json.dumps(summary, indent=2))

    if error is not None:
        print(f"FAIL the browser session did not complete: {error}")
        return 2
    if not steps:
        print("FAIL the app was never rendered, so nothing was proven.")
        return 2
    if not unchanged:
        print("FAIL a real Streamlit host process modified artifacts/chart_sources:")
        for name in delta["modified"]:
            print(f"  modified {name}")
        for name in delta["added"]:
            print(f"  added    {name}")
        for name in delta["removed"]:
            print(f"  removed  {name}")
        return 1
    if not clean:
        print("FAIL git status changed across app startup.")
        return 1
    print(f"PASS {len(before)} chart-source file(s) byte-identical after {len(steps)} browser step(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
