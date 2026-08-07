#!/usr/bin/env bash
# Phase 1 of the bundle-probe abort diagnosis: the four-case A/B matrix.
#
#   e14654a (last good)   x  source probe, bundle probe
#   5e9d2d2 (merge, bad)  x  source probe, bundle probe
#
# each case at least twice, in a container that reproduces the PUBLISH job's
# environment (python:3.11-bookworm + requirements.txt ONLY - the nltf-ci image
# has extra wheels and pinned BLAS threading, either of which could move a
# native teardown crash, so it is deliberately not used here).
#
# Each SHA is probed by ITS OWN validator code, exactly as the publish workflow
# at that SHA would have done. The driver is copied into each disposable clone
# untracked; it reads code, never writes tracked content.
#
# What the matrix decides:
#   only 5e9d2d2 bundle fails          -> packaging / bundle-only content
#   5e9d2d2 source AND bundle fail     -> runtime source change or dep interaction
#   e14654a also fails here            -> environment drift, not the merge
#   only 5e9d2d2 fails (both probes)   -> commit-level isolation next
#
# No governed pack is rebuilt or altered. Clones are disposable and discarded.
#
# Usage: bash ci/hotfix_probe_matrix.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EV="$REPO_ROOT/artifacts/ci_optimisation/probe_matrix"
mkdir -p "$EV"

GOOD_SHA="e14654ab9ea99c5de8ce33ee5b810c99ba7b9b6a"
BAD_SHA="5e9d2d2840050c8ff0f063f8567030791d6950ef"
RUNS_PER_CASE=2

banner() { printf '\n\n############ %s ############\n' "$*"; }

# Refuse to run while anything else heavy is running: a native crash diagnosis
# contaminated by resource contention is worse than none.
if [ "$(pgrep -fc 'pytest' 2>/dev/null || true)" != "0" ] && [ -n "$(pgrep -f 'pytest' 2>/dev/null)" ]; then
  echo "REFUSING: pytest is running." >&2
  exit 2
fi

banner "Building the publish-environment image (requirements.txt only)"
DOCKER_BUILDKIT=1 docker build -f "$REPO_ROOT/ci/Dockerfile.publish-probe" \
  -t nltf-publish-probe:local "$REPO_ROOT" > "$EV/image_build.log" 2>&1 \
  || { tail -5 "$EV/image_build.log"; echo "image build failed"; exit 2; }

docker run --rm --entrypoint cat nltf-publish-probe:local /publish_env_python.txt \
  > "$EV/probe_env_python.txt"
docker run --rm --entrypoint cat nltf-publish-probe:local /publish_env_freeze.txt \
  > "$EV/probe_env_freeze.txt"
echo "environment: $(head -1 "$EV/probe_env_python.txt")"

in_probe_env() {
  local clone="$1"; shift
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$clone:/work" -w /work --entrypoint python nltf-publish-probe:local "$@"
}

SUMMARY="$EV/matrix_summary.txt"
: > "$SUMMARY"

for SHA in "$GOOD_SHA" "$BAD_SHA"; do
  SHORT="${SHA:0:7}"
  CLONE="/tmp/nltf-probe-$SHORT-$$"

  banner "SHA $SHORT: disposable clone"
  git clone --quiet --local "$REPO_ROOT" "$CLONE" || exit 2
  if [ -e "$CLONE/.git/objects/info/alternates" ]; then
    echo "clone borrows objects; git would not work in the container" >&2; exit 2
  fi
  git -C "$CLONE" checkout --quiet --detach "$SHA" || exit 2
  [ -z "$(git -C "$CLONE" status --porcelain)" ] || { echo "clone dirty"; exit 2; }

  # The driver is new on the hotfix branch; older SHAs do not carry it. It is
  # copied in untracked - it reads the clone's validator, never tracked content.
  cp "$REPO_ROOT/ci/probe_matrix_driver.py" "$CLONE/probe_matrix_driver.py"

  banner "SHA $SHORT: building the bundle (its own builder)"
  in_probe_env "$CLONE" scripts/build_databricks_app_bundle.py \
    --source . --output build/databricks_app/app --clean \
    > "$EV/${SHORT}_bundle_build.log" 2>&1
  build_code=$?
  echo "bundle build exit=$build_code" | tee -a "$SUMMARY"
  [ "$build_code" -eq 0 ] || { tail -5 "$EV/${SHORT}_bundle_build.log"; exit 2; }

  for TARGET in source bundle; do
    for RUN in $(seq 1 "$RUNS_PER_CASE"); do
      TAG="${SHORT}_${TARGET}_run${RUN}"
      banner "case $TAG"
      in_probe_env "$CLONE" probe_matrix_driver.py \
        --target "$TARGET" --out "/work/probe_out" --tag "$TAG" \
        | tee -a "$SUMMARY"
      cp "$CLONE/probe_out/$TAG.json" "$EV/" 2>/dev/null
      cp "$CLONE/probe_out/$TAG.stderr.txt" "$EV/" 2>/dev/null
      cp "$CLONE/probe_out/$TAG.stdout.txt" "$EV/" 2>/dev/null
    done
  done

  rm -rf "$CLONE"
done

banner "MATRIX"
cat "$SUMMARY"
