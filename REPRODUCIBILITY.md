# Reproduction and recorded evidence

This release studies dependency visibility and artifact reuse in QEC simulation software. QUITS is one of the subject systems; the release also includes qecc_routing source checks and Stim/sinter experiments.

## Validation on 2026-10-14

The exported copy was checked on Windows with Python 3.11.17, NumPy 2.4.6, SciPy 1.17.1, Stim/sinter 1.16.0, ldpc 2.4.1, qldpc 0.4.1, PyMatching 2.4.0, QUITS 1.2.0, and BeliefMatching 0.1.1. Adding BeliefMatching left all previously installed package versions unchanged; `python -m pip check` passed.

| Check | Result |
| --- | --- |
| `python -m pytest OOPSLA/experiments -q -ra` | 220 passed in 96.27 s; two ldpc legacy-API warnings |
| Consumer-relation tests | 29 passed in 0.76 s |
| `python scripts/reproduce.py --only certificates symbolic consumers native` | All 15 scripts completed successfully in a scratch copy |
| `python scripts/reproduce.py --only costs` | Seven measurement repetitions completed in a scratch copy |
| Figure data loader | Four input hashes, event counts, and Wilson intervals checked |

Run the consumer tests separately, with their source directory on the import path:

```bash
PYTHONPATH=OOPSLA/research/consumer-contracts-2026-10-11/src \
  python -m pytest OOPSLA/research/consumer-contracts-2026-10-11/tests -q
```

Use `PYTHONHASHSEED=0` for all reproduction commands. The isolated entry point sets it for its subprocesses. It copies published inputs into `.reproduction/work/` and saves script logs under `.reproduction/logs/`. Reproduction outputs are excluded from version control and do not replace the historical records.

The `native` group checks the Python-level simulation relation and the routing threshold path against the pinned producer. A separate optional C++ routing executable requires its own build and input instance. Supply both `--native-executable PATH` and `--native-instance PATH` to `OOPSLA/research/substitution-validation-2026-10-10/src/run_qecc.py` to request that check. The saved historical C++ invocation failed with return code 3221225781. This release did not build or validate that external executable.

The Dockerfile is supplied for Linux reproduction. Docker was unavailable on the release machine, so an actual image build was not run. The GitHub workflow runs the experiment tests, deterministic formal-output comparisons, and consumer tests on Ubuntu with the pinned requirements.

## Historical environments and metrics

Recorded results retain their original package versions, seeds, sample counts, grids, and protocol fields. Some external-decoder and Stim/sinter records use Python 3.10, Stim 1.14, and PyMatching 2.2. The recorded cost measurements use Python 3.12.14. The validation above checks the exported code in the release environment; stochastic results and timings can differ from historical runs.

Several historical experiment labels use `LER` or `logical_error_rate`. In the QUITS sampling path used here, the helper retains decoder predictions but discards the sampled true observables. Those counts measure the frequency of predicted flips. A logical failure rate requires comparing predictions with true observables from the same shots. The figure data loader checks counts and intervals without changing the saved values.

The architecture-label substitution in the corresponding physical comparison does not change the extractor's circuit because that extractor constructs its own layout. The historical `SD6-10x` cache-comparison label corresponds to an actual 30-fold noise multiplier. Decoder randomness in that historical comparison was not controlled. These records should be interpreted with those protocol details.

## Export adaptations and hashes

The original project and manuscript were left unchanged. The release copy has these packaging adaptations:

- Source, results, tests, corpus data, and fixed upstream snapshots are arranged under one repository root. Cost and figure tools were moved out of the paper directory.
- Local machine paths in recorded JSON and Markdown were replaced with repository-relative or environment-relative paths. Numerical results and protocol fields were preserved.
- Imports and workflow paths were adapted to this layout. Source-certificate output directories can be created in a fresh checkout. The optional native executable is selected through explicit command-line arguments.
- BeliefMatching 0.1.1 was added to the dependency files. The stale-DEM prediction-difference regression uses 9600 shots, matching the historical protocol, because 200 shots can miss the rare prediction differences. Its assertions are unchanged.
- The Docker install command and copied workflow path were corrected. The image runs the experiment test suite by default.

Historical source and evidence hashes describe the original runs. Files adapted for this export, including records with normalized path strings, have different current bytes; some historical nested evidence hashes therefore refer to the original records. `MANIFEST.json` lists the SHA-256 and size of each current distributed file, excluding itself. Run `python scripts/verify.py` to check the distributed bytes and parse all distributed Python files.

The two third-party source trees retain the bytes from their pinned source archives, their licenses, and their author notices. Interpreter caches and source archives are excluded. Upstream notebooks may retain paths printed by their original authors.
