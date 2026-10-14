# QEC simulation dependency artifact

This repository contains the executable artifact for the study of dependency visibility and artifact reuse in quantum error-correction simulation software. It includes the formal model, source analyses, real-artifact checks, experiment drivers, recorded outputs, shared corpus data, pinned upstream source snapshots, and the environment files used for the reported runs.

The release contains code, experimental data, tests, reproducibility tools, and licenses. Paper sources, the manuscript PDF, reviews, writing drafts, and literature downloads are excluded.

## Layout

```text
OOPSLA/                 formal core, experiments, tests, and pinned outputs
OOPSLA/research/        supplementary source checks and saved evidence
OOPSLA/tools/           cost measurement and quantitative figure code
OOPSLA/benchmarks/      recorded cost measurements and raw evidence
shared/C0/              common code corpus used by the experiments
third_party/            read-only upstream snapshots and their licenses
scripts/                integrity checking and isolated reproduction
```

The upstream snapshots are pinned to the following commits:

| snapshot | commit | role |
| --- | --- | --- |
| `quits-0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452` | `0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452` | QUITS subject system |
| `qecc_routing-4ef18121c39492414b85ff36b3a61c83f9ebf95f` | `4ef18121c39492414b85ff36b3a61c83f9ebf95f` | second QEC software subject |

## Environment and tests

The release is verified with Python 3.11.17 and the core versions in `OOPSLA/requirements-lock.txt`. BeliefMatching 0.1.1 is included for the external decoder experiment. Historical results also include runs with Python 3.10 and 3.12; their recorded version fields and numerical results are preserved. See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for interpretation and validation details.

```bash
conda env create -f OOPSLA/environment.yml
conda activate oopsla-quits
python -m pytest OOPSLA/experiments -q
```

The tests compare the installed QUITS wheel with the pinned source tree. Set `PYTHONHASHSEED=0` for byte-stable Stim circuit text:

```bash
export PYTHONHASHSEED=0
python OOPSLA/experiments/cone_table.py
```

Experiment scripts write outputs next to themselves by default. Use `--out .reproduction/outputs` to keep recorded outputs intact. Supplemental checks have an isolated entry point:

```bash
python scripts/verify.py
python scripts/reproduce.py --only certificates symbolic consumers
```

The latter copies inputs into `.reproduction/work/` and executes checks there. Recorded JSON and Markdown paths are relative to this repository or the installed `site-packages/` directory.

## Docker

Build from the repository root:

```bash
docker build -f OOPSLA/Dockerfile -t qec-dependency-artifact .
docker run --rm qec-dependency-artifact
```

The image copies `OOPSLA/`, `shared/`, and `third_party/` into `/work`. The default command runs the experiment tests.

## Licenses

The artifact code and data written for this repository are released under the root MIT license. Each upstream snapshot remains under its own license; see the `LICENSE` file inside each `third_party/<snapshot>/` directory. The snapshots are included for measurement reproducibility and are kept unchanged.

## Reproducibility scope

The recorded outputs preserve their seeds, grids, sample counts, historical source hashes, and protocol descriptions. [REPRODUCIBILITY.md](REPRODUCIBILITY.md) records package differences, metric definitions, and release-only adaptations. [MANIFEST.json](MANIFEST.json) gives the current file hashes.
