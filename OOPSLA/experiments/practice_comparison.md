# Declarative checking vs. real QEC re-computation practices

Generated: 2026-10-12
Steps: 12 (baseline + 11 changes), shots: 64 per prediction fingerprint, rounds=2, seed=7
Ground-truth measurement wall time: 1.83 s; calibration (s/build): {'code': 0.015, 'noise': 0.0, 'extractor': 0.1213, 'decoder': 0.0944, 'arch': 0.0001, 'shots': 64}

## Methodology — and how the circularity was removed

The previous version of this experiment defined the checker's prediction as 'recompute everything that could be affected' and reported 0 misses by construction.  Here ground truth (byte-level artifact fingerprints per step) is measured independently on the pinned QUITS tree; each strategy's rebuild set is predicted from declared information only — for the checker, the declared read sets R(c) and the artifact-DAG edges via semantics.coordinate_impact — and scored against ground truth only afterwards.  predict_checker/predict_config_diff/predict_logbook/predict_declarative_naive/predict_declarative_omniscient take specs (plus the logged intent), never the fingerprint table; this is enforced by their signatures and locked by experiments/test_practice_comparison.py.  The omniscient declarative variant uses the same declared-information channel as the checker (the source-faithful read sets), never the measured fingerprints — it models a user whose declarations happen to be perfect, not a peek at the answer.

Declared read sets used by the checker: R(code)={code}, R(extractor)={code, extractor, noise}, R(noise)={noise}, R(decoder)={decoder}, R(arch)={arch}

Reproducibility constraint: Ground truth is byte-level, so every step must decode reproducibly.  The SD6-10x noise setting is excluded from the log because at that saturated operating point both QUITS decoders give different outputs on identical inputs across calls (unseeded randomness inside ldpc's OSD/LSD tie-breaking); SD6 / SI1000 / SD6-0.1x are verified deterministic for both decoders on every code family used.

## 1. The research log (deterministic)

| step | intent | code | extractor | arch | noise | decoder | changed dims | note |
|---|---|---|---|---|---|---|---|---|
| 0 | - | BB | zxcoloration | transversal | SD6 | BP-OSD | (baseline) | baseline run |
| 1 | noise | BB | zxcoloration | transversal | SI1000 | BP-OSD | noise | noise model sweep |
| 2 | noise | BB | zxcoloration | transversal | SD6-0.1x | BP-OSD | noise | noise model sweep |
| 3 | noise | BB | zxcoloration | transversal | SD6 | BP-OSD | noise | noise model sweep |
| 4 | noise | BB | zxcoloration | transversal | SI1000 | BP-OSD | noise | noise model sweep |
| 5 | decoder | BB | zxcoloration | transversal | SI1000 | BP-LSD | decoder | decoder swap |
| 6 | extractor | BB | custom | transversal | SI1000 | BP-LSD | extractor | extraction schedule swap |
| 7 | noise | BB | custom | transversal | SD6-0.1x | BP-LSD | noise | noise model sweep |
| 8 | noise | BB | custom | transversal | SD6 | BP-LSD | noise | noise model sweep |
| 9 | code | HGP | zxcoloration | transversal | SD6 | BP-LSD | code, extractor | code family change; extractor reset to zxcoloration (H1: custom is not in HgpCode.supported_strategies) |
| 10 | arch | HGP | zxcoloration | toric | SD6 | BP-LSD | arch | architecture swap (QUITS build does not route arch into the circuit products -- expected to change only the layout artifact) |
| 11 | noise | HGP | zxcoloration | toric | SI1000 | BP-LSD | noise | noise model sweep |

## 2. Ground truth: which artifacts actually changed

Byte-level fingerprints per step (C = changed vs previous step).

| step | code matrices | noise model | stim circuit | detector error model | decoder predictions | layout positions |
|---|---|---|---|---|---|---|
| 0 | C | C | C | C | C | C |
| 1 | . | C | C | C | C | . |
| 2 | . | C | C | C | C | . |
| 3 | . | C | C | C | C | . |
| 4 | . | C | C | C | C | . |
| 5 | . | . | . | . | . | . |
| 6 | . | . | C | C | C | . |
| 7 | . | C | C | C | C | . |
| 8 | . | C | C | C | C | . |
| 9 | C | . | C | C | C | C |
| 10 | . | . | . | . | . | C |
| 11 | . | C | C | C | C | . |

## 3. Per-strategy metrics

| strategy | missed artifacts | miss rate | over-rebuilds | builds | est. wall-clock (s) |
|---|---|---|---|---|---|
| full_rerun | **0** | 0.0000 | 29 | 72 | 2.77 |
| config_diff | **24** | 0.5581 | 1 | 20 | 0.58 |
| declarative_naive | **21** | 0.4884 | 1 | 23 | 0.77 |
| declarative_omniscient | **0** | 0.0000 | 1 | 44 | 2.28 |
| logbook | **26** | 0.6047 | 1 | 18 | 0.46 |
| checker | **0** | 0.0000 | 1 | 44 | 2.28 |

missed = artifact changed by ground truth but not rebuilt (stale artifact in use); over-rebuilds = rebuilt but byte-identical (wasted compute, still correct).

## 4. Missed artifacts per step (the dangerous column)

| step | intent | changed artifacts | full_rerun | config_diff | declarative_naive | declarative_omniscient | logbook | checker |
|---|---|---|---|---|---|---|---|---|
| 0 | - | code_matrices, noise_model, stim_circuit, detector_error_model, decoder_predictions, layout_positions | — | — | — | — | — | — |
| 1 | noise | noise_model, stim_circuit, detector_error_model, decoder_predictions | — | decoder_predictions, detector_error_model, stim_circuit | decoder_predictions, detector_error_model, stim_circuit | — | decoder_predictions, detector_error_model, stim_circuit | — |
| 2 | noise | noise_model, stim_circuit, detector_error_model, decoder_predictions | — | decoder_predictions, detector_error_model, stim_circuit | decoder_predictions, detector_error_model, stim_circuit | — | decoder_predictions, detector_error_model, stim_circuit | — |
| 3 | noise | noise_model, stim_circuit, detector_error_model, decoder_predictions | — | decoder_predictions, detector_error_model, stim_circuit | decoder_predictions, detector_error_model, stim_circuit | — | decoder_predictions, detector_error_model, stim_circuit | — |
| 4 | noise | noise_model, stim_circuit, detector_error_model, decoder_predictions | — | decoder_predictions, detector_error_model, stim_circuit | decoder_predictions, detector_error_model, stim_circuit | — | decoder_predictions, detector_error_model, stim_circuit | — |
| 5 | decoder | — | — | — | — | — | — | — |
| 6 | extractor | stim_circuit, detector_error_model, decoder_predictions | — | decoder_predictions | — | — | decoder_predictions | — |
| 7 | noise | noise_model, stim_circuit, detector_error_model, decoder_predictions | — | decoder_predictions, detector_error_model, stim_circuit | decoder_predictions, detector_error_model, stim_circuit | — | decoder_predictions, detector_error_model, stim_circuit | — |
| 8 | noise | noise_model, stim_circuit, detector_error_model, decoder_predictions | — | decoder_predictions, detector_error_model, stim_circuit | decoder_predictions, detector_error_model, stim_circuit | — | decoder_predictions, detector_error_model, stim_circuit | — |
| 9 | code | code_matrices, stim_circuit, detector_error_model, decoder_predictions, layout_positions | — | decoder_predictions, layout_positions | — | — | decoder_predictions, detector_error_model, layout_positions, stim_circuit | — |
| 10 | arch | layout_positions | — | — | — | — | — | — |
| 11 | noise | noise_model, stim_circuit, detector_error_model, decoder_predictions | — | decoder_predictions, detector_error_model, stim_circuit | decoder_predictions, detector_error_model, stim_circuit | — | decoder_predictions, detector_error_model, stim_circuit | — |

Over-rebuilds (rebuilt but byte-identical): full_rerun: 29; config_diff: 1; declarative_naive: 1; declarative_omniscient: 1; logbook: 1; checker: 1

## 5. Conclusion — declarative checking vs. git-diff, logbook and declarative-build practices

| practice | missed artifacts | miss rate | vs checker |
|---|---|---|---|
| config_diff | 24 | 0.5581 | worse |
| declarative_naive | 21 | 0.4884 | worse |
| logbook | 26 | 0.6047 | worse |
| full_rerun | 0 | 0.0000 | equal |
| declarative_omniscient (perfect declarations) | 0 | 0.0000 | equal |
| checker (declared R(c)) | 0 | 0.0000 | — |

- On every **noise-only** step, `config_diff`, `logbook` and `declarative_naive` keep using the extractor's stale circuit/DEM/predictions: the declared spec diff shows only `noise`, and the runtime read (extractor -> noise, finding H3) is invisible to a config diff **and un-declarable for a make/snakemake user** — `build_circuit` takes the error model inside the component call, so the pipeline's file DAG has no edge to declare.  The checker's declared read set R(extractor) = {code, extractor, noise} catches exactly these steps.
- The declarative-build practice is NOT the git-diff practice, and the gap is measurable: an honest snakemake user wires the pipeline's visible file flow (decoder consumes the circuit, layout consumes the code), so `declarative_naive` closes every miss that comes from that wiring — on this log it misses 21 artifacts vs. 24 for `config_diff` — while paying almost nothing in extra over-rebuilds (1 vs. 1).  What no honest declaration can close is the intra-component read: on the noise-only steps `declarative_naive` misses exactly what `config_diff` misses.
- The upper bound confirms where the increment lives: `declarative_omniscient` — a user whose declared coordinate sets are the true ones — rebuilds exactly the checker's set (44 builds, 0 misses on this log).  Perfect declarations and the checker's extracted read sets carry the same information; source-level extraction is the way to obtain them without omniscience.  This is the empirical answer to 'what is an increment': the increment is the runtime read set, which neither a spec diff nor an honest file-level declaration recovers.
- The checker's cost is close to `config_diff`'s blind spot-free ideal: it rebuilds only the impacted artifacts, so its over-rebuild count is 1 (vs. 29 for the full re-run baseline) while missing 0.
- Honest negatives: the decoder swap (BP-OSD -> BP-LSD) changes no byte of the 64-shot predictions on this subject — consistent with physical_impact's negative result — so every strategy that rebuilds predictions there over-rebuilds, none misses. The arch swap changes only the layout artifact: QUITS' build does not route arch into the circuit products, which is exactly the 'changed in the spec, unchanged in the circuit products' case, and no strategy is fooled by it.

