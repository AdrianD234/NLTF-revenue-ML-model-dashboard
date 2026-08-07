# Local clean-room CI image for the NLTF revenue dashboard.
#
# Aligned with the two environments that already matter:
#   * .devcontainer/devcontainer.json  - python:1-3.11-bookworm
#   * .github/workflows/ci.yml         - actions/setup-python 3.11 on ubuntu-latest
#
# That alignment is the whole point. The developer .venv on Windows is Python
# 3.13 with different numpy/pandas builds, so it cannot settle a question about
# a governed number. This image can.
#
# Layering is deliberate: dependencies are installed from the requirements files
# alone, before any source is present, so editing a module does not reinstall
# scikit-learn. Source is never COPYed in at all - scripts/ci_local.* bind-mounts
# a disposable, byte-exact copy of the tracked tree at run time, which keeps the
# image reusable across branches and keeps the active checkout untouched.

FROM python:3.11-bookworm

# Deterministic, quiet, no stale bytecode written into the mounted copy.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1

# Single-threaded BLAS by default. The forward model is not bit-reproducible
# across differing thread counts, and a container that quietly used a different
# number of cores than the hosted runner would manufacture drift that looks like
# a code defect. Override deliberately for benchmarking, never for assurance.
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1

WORKDIR /work

# Dependency layer. Cache mounts make a warm rebuild seconds rather than minutes;
# they are a BuildKit feature, so builds must run with DOCKER_BUILDKIT=1 (the
# default for `docker buildx` and modern `docker build`).
COPY requirements.txt requirements-dev.txt ci/requirements-ci.txt /tmp/deps/
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip \
 && pip install -r /tmp/deps/requirements.txt \
 && pip install -r /tmp/deps/requirements-dev.txt \
 && pip install -r /tmp/deps/requirements-ci.txt

# Record what this image actually resolved to. The wrapper copies this out with
# every run so a local result can be compared against a hosted one without
# guessing which build produced it.
RUN python - <<'PY' > /image_environment.json
import json, sys
record = {"python": sys.version}
for module in ("numpy", "pandas", "scipy", "sklearn", "pyarrow", "statsmodels",
               "streamlit", "plotly", "pytest"):
    try:
        record[module] = __import__(module).__version__
    except Exception as exc:
        record[module] = f"unavailable: {exc}"
try:
    import threadpoolctl
    record["threadpool"] = threadpoolctl.threadpool_info()
except Exception as exc:
    record["threadpool_error"] = str(exc)
print(json.dumps(record, indent=2))
PY

# Playwright's browsers are deliberately NOT installed. pytest.ini deselects the
# e2e marker and AGENTS.md keeps the browser phase on the host, so downloading
# ~400MB of Chromium into every image would buy nothing. The pytest-playwright
# package is installed (via requirements-dev.txt) because marker deselection
# happens after collection, and collection imports the plugin.

COPY ci/entrypoint.sh /usr/local/bin/ci-entrypoint
RUN chmod +x /usr/local/bin/ci-entrypoint

ENTRYPOINT ["/usr/local/bin/ci-entrypoint"]
CMD ["fast"]
