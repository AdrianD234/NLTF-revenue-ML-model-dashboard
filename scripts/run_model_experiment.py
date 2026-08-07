"""Run one model-specification experiment locally and record it reproducibly.

The roadmap is a long list of specification questions: a two-year COVID dummy,
COVID trend and coefficient permutations, dropping seasonality dummies,
exports/imports and lagged GDP, the clean-car discount, explainable challengers,
heavy-RUC consumption variables, smoothed VKT-per-capita variants, and error
bands that exclude the COVID period.

Each of those is several runs, and most of them will be discarded. Running them
through GitHub Actions would be the single most expensive possible way to answer
a question that does not need a clean room at all — the answer is a comparison
between candidates on the same machine, not a cross-platform guarantee.

So: experiments run here. Only a selected finalist enters model-promotion CI.

What this script guarantees is that a discarded candidate can still be
reconstructed later. Every run records the source SHA, the input-data hashes,
the seed, the configuration and the resulting metrics. An experiment whose
inputs cannot be identified is an anecdote.

This script NEVER promotes. It does not write to data/, does not rebuild a
governed pack, and does not touch a manifest. Promotion is a separate,
deliberate act under AGENTS.md mode C.

Usage:
    python scripts/run_model_experiment.py --config experiments/configs/covid_dummy.yml
    python scripts/run_model_experiment.py --config <path> --dry-run
    python scripts/run_model_experiment.py --list
    python scripts/run_model_experiment.py --compare exp_0001 exp_0002
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import platform
import subprocess
import sys
import time

try:
    import yaml
except ImportError:  # pragma: no cover
    print("run_model_experiment.py needs PyYAML (pip install pyyaml)", file=sys.stderr)
    raise

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EXPERIMENTS = REPO_ROOT / "experiments"
CONFIGS = EXPERIMENTS / "configs"
RESULTS = EXPERIMENTS / "results"

REQUIRED_CONFIG_KEYS = ("experiment_id", "stream", "seed", "description")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=REPO_ROOT, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def load_config(path: pathlib.Path) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
    if missing:
        raise SystemExit(
            f"{path} is missing required key(s): {', '.join(missing)}.\n"
            "An experiment without an id, stream, seed and description cannot be "
            "reproduced or compared, which defeats the point of recording it."
        )
    return config


def hash_inputs(config: dict) -> dict[str, str]:
    """Hash every declared input so a result can be tied to the data it used."""
    hashes: dict[str, str] = {}
    for relative in config.get("input_files") or []:
        path = REPO_ROOT / relative
        hashes[relative] = sha256_file(path) if path.is_file() else "absent"
    return dict(sorted(hashes.items()))


def provenance(config: dict) -> dict:
    dirty = bool(git("status", "--porcelain"))
    return {
        "source_sha": git("rev-parse", "HEAD"),
        "source_dirty": dirty,
        "source_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "input_hashes": hash_inputs(config),
        "python": sys.version,
        "platform": platform.platform(),
        "seed": config["seed"],
        "config_sha256": hashlib.sha256(
            json.dumps(config, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest(),
    }


def run_experiment(config: dict, dry_run: bool) -> dict:
    """Execute the configured experiment entry point and collect its metrics.

    The entry point is named by the config rather than hard-coded, because the
    roadmap's experiments touch different parts of the model. What is fixed is
    the *contract*: the callable takes the config and returns a metrics dict.
    """
    entry = config.get("entry_point")
    if not entry:
        raise SystemExit(
            "config declares no entry_point.\n"
            "Set entry_point to 'module.path:function'. The function receives the "
            "config dict and must return a dict of metrics."
        )

    if dry_run:
        return {"dry_run": True, "note": "entry point not executed"}

    module_name, _, function_name = entry.partition(":")
    if not function_name:
        raise SystemExit(f"entry_point '{entry}' must be 'module.path:function'")

    import importlib

    module = importlib.import_module(module_name)
    function = getattr(module, function_name)

    started = time.time()
    metrics = function(config)
    elapsed = time.time() - started

    if not isinstance(metrics, dict):
        raise SystemExit(
            f"{entry} returned {type(metrics).__name__}, expected a dict of metrics"
        )
    metrics = dict(metrics)
    metrics.setdefault("runtime_seconds", round(elapsed, 2))
    return metrics


def record(config: dict, metrics: dict, prov: dict) -> pathlib.Path:
    experiment_id = str(config["experiment_id"])
    out_dir = RESULTS / experiment_id
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "experiment_id": experiment_id,
        "description": config["description"],
        "stream": config["stream"],
        "specification_changes": config.get("specification_changes", []),
        "train_window": config.get("train_window"),
        "validation_windows": config.get("validation_windows"),
        "seed": config["seed"],
        "provenance": prov,
        "metrics": metrics,
        # Promotion is never automatic. This field is set by a human, in a
        # separate commit, after comparing candidates.
        "promotion_status": config.get("promotion_status", "candidate"),
    }
    payload["output_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    result_path = out_dir / "result.json"
    result_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return result_path


def list_experiments() -> int:
    if not RESULTS.exists():
        print("No experiments recorded yet.")
        return 0
    rows = []
    for path in sorted(RESULTS.glob("*/result.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rows.append(
            (
                data["experiment_id"],
                data.get("stream", ""),
                data.get("promotion_status", ""),
                data.get("metrics", {}).get("mape", ""),
                data.get("description", "")[:50],
            )
        )
    if not rows:
        print("No experiments recorded yet.")
        return 0
    print(f"{'id':<14} {'stream':<12} {'status':<12} {'mape':<10} description")
    for row in rows:
        print(f"{row[0]:<14} {row[1]:<12} {row[2]:<12} {str(row[3]):<10} {row[4]}")
    return 0


def compare(ids: list[str]) -> int:
    payloads = []
    for experiment_id in ids:
        path = RESULTS / experiment_id / "result.json"
        if not path.exists():
            print(f"No such experiment: {experiment_id}", file=sys.stderr)
            return 1
        payloads.append(json.loads(path.read_text(encoding="utf-8")))

    keys: list[str] = []
    for payload in payloads:
        for key in payload.get("metrics", {}):
            if key not in keys:
                keys.append(key)

    width = max(len(k) for k in keys) if keys else 10
    header = f"{'metric':<{width}}" + "".join(f"  {p['experiment_id']:>16}" for p in payloads)
    print(header)
    print("-" * len(header))
    for key in keys:
        line = f"{key:<{width}}"
        for payload in payloads:
            value = payload.get("metrics", {}).get(key, "")
            line += f"  {str(value):>16}"
        print(line)

    # A comparison across differing inputs is not a comparison.
    input_sets = {
        json.dumps(p["provenance"]["input_hashes"], sort_keys=True) for p in payloads
    }
    if len(input_sets) > 1:
        print(
            "\nWARNING: these experiments did not use identical inputs. The metric "
            "differences above conflate specification change with data change.",
            file=sys.stderr,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, help="experiment config YAML")
    parser.add_argument("--dry-run", action="store_true",
                        help="record provenance without executing the entry point")
    parser.add_argument("--list", action="store_true", help="list recorded experiments")
    parser.add_argument("--compare", nargs="+", metavar="ID",
                        help="compare recorded experiments side by side")
    args = parser.parse_args(argv)

    if args.list:
        return list_experiments()
    if args.compare:
        return compare(args.compare)
    if not args.config:
        parser.error("one of --config, --list or --compare is required")

    config = load_config(args.config)
    prov = provenance(config)

    if prov["source_dirty"]:
        print(
            "NOTE: the working tree is dirty. The recorded source SHA does not fully "
            "describe this run; commit before an experiment you intend to cite.",
            file=sys.stderr,
        )

    metrics = run_experiment(config, args.dry_run)
    path = record(config, metrics, prov)
    print(f"Recorded {config['experiment_id']} -> {path}")
    for key, value in sorted(metrics.items()):
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
