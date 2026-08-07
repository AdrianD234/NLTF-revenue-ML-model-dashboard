"""Run ONE probe case exactly as the bundle validator would, recording raw evidence.

The validator's ``run_isolated_probe`` raises on any non-zero exit and discards
the return code, which is correct for a gate and useless for a diagnosis. This
driver invokes the very same code path - the clone's own validator module, the
same workspace construction, the same ``subprocess.run`` - but captures the raw
process result by wrapping ``subprocess.run`` inside the validator module, so
the recorded command is the exact command, not a reconstruction.

Usage (cwd must be the checkout under test):
    python ci/probe_matrix_driver.py --target source  --out <dir> --tag <label>
    python ci/probe_matrix_driver.py --target bundle --bundle-dir build/databricks_app/app \
        --out <dir> --tag <label>

Always exits 0 itself; the verdict lives in <out>/<tag>.json. A diagnostic that
crashes on the crash it is diagnosing records nothing.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
import traceback

ABORT_SIGNATURE = "terminate called without an active exception"


def load_validator() -> object:
    spec = importlib.util.spec_from_file_location(
        "vdb", pathlib.Path("scripts/validate_databricks_app_bundle.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["source", "bundle"], required=True)
    parser.add_argument("--bundle-dir", default="build/databricks_app/app")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    record: dict = {"tag": args.tag, "target": args.target}

    vdb = load_validator()

    # Capture the probe subprocess's raw result from inside the validator, so
    # the command, environment and workspace are exactly what the gate runs.
    captured: dict = {}
    original_run = vdb.subprocess.run

    def capturing_run(*call_args, **call_kwargs):
        result = original_run(*call_args, **call_kwargs)
        captured["argv"] = list(call_args[0]) if call_args else call_kwargs.get("args")
        captured["returncode"] = result.returncode
        captured["stdout"] = result.stdout or ""
        captured["stderr"] = result.stderr or ""
        return result

    vdb.subprocess.run = capturing_run

    source_root = pathlib.Path(".").resolve()
    try:
        if args.target == "source":
            report = vdb.run_isolated_probe(
                source_root, vdb.tracked_relatives(source_root), "source"
            )
        else:
            bundle_root = pathlib.Path(args.bundle_dir).resolve()
            report = vdb.run_isolated_probe(
                bundle_root, vdb.walk_files(bundle_root), "bundle"
            )
        record["validator_raised"] = False
        record["probe_errors"] = report.get("errors")
    except Exception as exc:  # includes BundleValidationError
        record["validator_raised"] = True
        record["exception_type"] = type(exc).__name__
        record["exception_text"] = str(exc)[:2000]
        record["traceback"] = traceback.format_exc()[-2000:]

    stdout = captured.get("stdout", "")
    stderr = captured.get("stderr", "")
    record["returncode"] = captured.get("returncode")
    record["json_complete"] = (
        "===PROBE-JSON-BEGIN===" in stdout and "===PROBE-JSON-END===" in stdout
    )
    record["abort_present"] = ABORT_SIGNATURE in stderr
    record["stderr_last_line"] = stderr.strip().splitlines()[-1] if stderr.strip() else ""

    (args.out / f"{args.tag}.stdout.txt").write_text(stdout, encoding="utf-8")
    (args.out / f"{args.tag}.stderr.txt").write_text(stderr, encoding="utf-8")
    (args.out / f"{args.tag}.json").write_text(
        json.dumps(record, indent=2, default=str), encoding="utf-8"
    )

    print(
        f"{args.tag}: returncode={record['returncode']} "
        f"json_complete={record['json_complete']} abort={record['abort_present']} "
        f"raised={record['validator_raised']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
