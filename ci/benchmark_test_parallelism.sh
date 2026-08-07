#!/usr/bin/env bash
# Clean sequential xdist benchmark.
#
# Protocol, per the owner's instruction:
#   * one run must finish completely before the next starts (enforced by this
#     script being a plain sequential loop with no backgrounding);
#   * each run gets a FRESH disposable git worktree at a fixed commit, so no
#     leftover scratch from a previous run can influence the next;
#   * no source edits while any run is in flight;
#   * no pack builders, no other pytest process, no Docker work;
#   * captures everything needed to judge determinism, not just duration.
#
# Usage:  bash clean_xdist_benchmark.sh <repo> <sha> <label> <outdir> <nworkers> <dist> [runs]

set -uo pipefail

REPO="$1"; SHA="$2"; LABEL="$3"; OUT="$4"; NWORKERS="$5"; DIST="$6"; RUNS="${7:-2}"
PY="C:/Users/Adrian Desilvestro/Repos/NLTF-revenue-ML-model-dashboard/.venv/Scripts/python.exe"

mkdir -p "$OUT"

# Refuse to start if any pytest is already running: a contended benchmark is
# not a benchmark. This is the exact failure mode being guarded against.
if command -v powershell.exe >/dev/null 2>&1; then
  RUNNING=$(powershell.exe -NoProfile -Command \
    "(Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | Where-Object { \$_.CommandLine -match 'pytest' }).Count" 2>/dev/null | tr -d '\r')
  if [ "${RUNNING:-0}" -gt 0 ] 2>/dev/null; then
    echo "REFUSING TO START: $RUNNING pytest process(es) already running." >&2
    exit 2
  fi
fi

hash_tree() {
  # Hash every governed pack file and every tracked file, so a same-path
  # content change is caught even where git ignores the path.
  local root="$1" dest="$2"
  "$PY" - "$root" "$dest" <<'PY'
import hashlib, json, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
targets = [p for p in (root / "data").rglob("*") if p.is_file()]
tracked = subprocess.run(["git", "-C", str(root), "ls-files"],
                         capture_output=True, text=True).stdout.split()
targets += [root / t for t in tracked if (root / t).is_file()]
out = {}
for p in sorted(set(targets)):
    try:
        out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception as exc:
        out[p.relative_to(root).as_posix()] = f"err:{exc}"
pathlib.Path(sys.argv[2]).write_text(json.dumps(out, indent=0), encoding="utf-8")
print(f"hashed {len(out)} files")
PY
}

for RUN in $(seq 1 "$RUNS"); do
  TAG="${LABEL}_run${RUN}"
  WT="/tmp/nltf-bench-${LABEL}-${RUN}-$$"

  echo ""
  echo "############ $TAG ############"

  git -C "$REPO" worktree add --detach --quiet "$WT" "$SHA" || { echo "worktree failed"; exit 2; }

  # Byte-exactness check: refuse to benchmark a tree that does not match the
  # commit, because a timing from an unknown tree is not evidence.
  DRIFT=$(git -C "$WT" status --porcelain)
  if [ -n "$DRIFT" ]; then
    echo "FATAL: fresh worktree is dirty:"; echo "$DRIFT"
    git -C "$REPO" worktree remove --force "$WT"; exit 2
  fi

  ( cd "$WT" && "$PY" scripts/regenerate_curated_data_from_pack.py > "$OUT/${TAG}_curated.log" 2>&1 )
  ( cd "$WT" && "$PY" scripts/audit_gdp_sign_guard_bindings.py > "$OUT/${TAG}_gdpguard.log" 2>&1 )

  hash_tree "$WT" "$OUT/${TAG}_hashes_before.json"
  git -C "$WT" status --porcelain > "$OUT/${TAG}_gitstatus_before.txt"

  CMD=("$PY" -m pytest -q -m "not e2e and not requires_local_scratch")
  if [ "$NWORKERS" != "0" ]; then CMD+=(-n "$NWORKERS" --dist="$DIST"); fi
  CMD+=(--junitxml="$OUT/${TAG}_junit.xml" -rf)

  printf '%q ' "${CMD[@]}" > "$OUT/${TAG}_command.txt"; echo >> "$OUT/${TAG}_command.txt"

  START=$(date +%s)
  ( cd "$WT" && "${CMD[@]}" ) > "$OUT/${TAG}.log" 2>&1
  CODE=$?
  ELAPSED=$(( $(date +%s) - START ))

  git -C "$WT" status --porcelain > "$OUT/${TAG}_gitstatus_after.txt"
  hash_tree "$WT" "$OUT/${TAG}_hashes_after.json"

  ( cd "$WT" && "$PY" scripts/plan_governed_pack_rebuilds.py --format json \
      > "$OUT/${TAG}_packstatus.json" 2>"$OUT/${TAG}_packstatus.err" )

  "$PY" - "$OUT/${TAG}_hashes_before.json" "$OUT/${TAG}_hashes_after.json" \
          "$OUT/${TAG}_hash_diff.txt" <<'PY'
import json, pathlib, sys
before = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
after = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
moved = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
added = sorted(after.keys() - before.keys())
removed = sorted(before.keys() - after.keys())
lines = [f"content changed: {len(moved)}", *[f"  M {p}" for p in moved[:50]],
         f"added: {len(added)}", *[f"  + {p}" for p in added[:20]],
         f"removed: {len(removed)}", *[f"  - {p}" for p in removed[:20]]]
pathlib.Path(sys.argv[3]).write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines[:6]))
PY

  {
    echo "tag=$TAG"
    echo "sha=$SHA"
    echo "workers=$NWORKERS"
    echo "dist=$DIST"
    echo "exit_code=$CODE"
    echo "elapsed_seconds=$ELAPSED"
    echo "elapsed_hms=$((ELAPSED/60))m$((ELAPSED%60))s"
    echo "summary=$(grep -oE '[0-9]+ passed[^=]*' "$OUT/${TAG}.log" | tail -1)"
    echo "failed_count=$(grep -cE '^FAILED' "$OUT/${TAG}.log")"
  } > "$OUT/${TAG}_result.txt"

  echo "--- $TAG result ---"; cat "$OUT/${TAG}_result.txt"
  echo "--- failures ---"; grep -E '^FAILED' "$OUT/${TAG}.log" || echo "  (none)"

  git -C "$REPO" worktree remove --force "$WT" 2>/dev/null || rm -rf "$WT"
  git -C "$REPO" worktree prune 2>/dev/null
done

echo ""
echo "############ BENCHMARK COMPLETE: $LABEL ############"
