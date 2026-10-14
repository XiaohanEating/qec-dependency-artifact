# OOPSLA artifact — reproducible Docker image
#
# Build:
#     docker build -f OOPSLA/Dockerfile -t oopsla-quits .
# Run the test suite:
#     docker run --rm oopsla-quits
# Run the experiments:
#     docker run --rm oopsla-quits python /work/OOPSLA/experiments/cone_table.py
#
# The build context is the REPOSITORY ROOT (that is where `third_party/` lives),
# which is why every COPY uses a path relative to it and the image copies both
# `OOPSLA/` and the read-only pinned QUITS tree into `/work/`.
#
# Why a pinned tree and not `pip install quits`: `experiments/quant_evidence.py`
# imports the tree under `third_party/` and *asserts* the imported module comes
# from there, so the pinned snapshot must be on disk (see OOPSLA/README.md §2).

FROM python:3.11-slim

# --- build/runtime dependencies --------------------------------------------
# stim / ldpc / qldpc need a BLAS + LAPACK implementation and a C++ toolchain
# is NOT needed (all wheels are manylinux), but libgomp / libstdc++ are.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        libstdc++6 \
        libquadmath0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work

# --- pinned Python environment ---------------------------------------------
# `requirements-lock.txt` pins the reference packages used for release checks.
# Historical output versions are recorded separately. It is copied first so Docker
# caches the (slow) dependency layer independently of the source tree.
COPY OOPSLA/requirements-lock.txt /work/OOPSLA/requirements-lock.txt
RUN pip install --no-cache-dir \
        -r /work/OOPSLA/requirements-lock.txt

# --- the artifact and the read-only pinned QUITS tree -----------------------
COPY OOPSLA/ /work/OOPSLA/
COPY third_party/ /work/third_party/
# The experiment hygiene tests inspect the workflow configuration.
COPY .github/ /work/.github/
# `shared/` holds the C0 corpus that `src/abstraction.py` loads via
# `CORPUS_PATH = Path(__file__).resolve().parents[2] / "shared" / "C0" / "corpus.json"`,
# which resolves to `/work/shared/C0/corpus.json` inside the image.
COPY shared/ /work/shared/

# The pinned tree is ground truth and must stay byte-identical.
ENV PYTHONHASHSEED=0

# `dynamic_impact.py` and `stim_circuit_gate.py` re-exec themselves with
# PYTHONHASHSEED=0 already; pinning it here makes the whole image reproducible.
RUN python -c "import quits, sys; print('quits from', quits.__file__)"

WORKDIR /work

# Default: the test suite.  Override with `docker run --rm <img> <cmd>`.
CMD ["python", "-m", "pytest", "/work/OOPSLA/experiments", "-q"]
