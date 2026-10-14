# Subject system 3: Stim + sinter + PyMatching

Generated: 2026-10-12
Versions: stim 1.14.0, sinter 1.14.0, pymatching 2.2.0
Statistics: Wilson 95% interval per rate; two-proportion z-test per comparison (qec_measure)

## 1. Registry audit (Q1)

| package | .py scanned | name registries | registry dispatch | getattr dispatch | auto-discovery | ABC classes | abstract methods | Protocols |
|---|---|---|---|---|---|---|---|---|
| sinter | 36 | 2 | 7 | 2 | 0 | 4 | 4 | 0 |
| pymatching | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| stim | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

- name-keyed registries found: **2** (both in sinter; see evidence below)
- auto-discovery (entry_points/importlib/pluggy): **0**

Registry evidence (file:line):

- `_decoding_all_built_in_decoders.py:12` — `BUILT_IN_DECODERS: Dict[str, Decoder] = {`
- `_decoding_all_built_in_decoders.py:22` — `BUILT_IN_SAMPLERS: Dict[str, Union[Decoder, Sampler]] = {`

Verdict: sinter HAS a name-keyed component registry (BUILT_IN_DECODERS / BUILT_IN_SAMPLERS) and explicit ABCs (sinter.Decoder, sinter.CompiledDecoder, sinter.Sampler, sinter.CompiledSampler) — the '0 registries / 0 abstract interfaces' expectation is FALSIFIED for this ecosystem.  What is absent is the QUITS pattern: the registry is closed (built-in only, no entry-point auto-discovery), dispatch is by an explicit string at the call site (decoder='pymatching' in sinter.Task / sinter.collect), and the substitutable component has a stated obligation (the Decoder ABC).  No component reaches around its call site to read ambient configuration: a stim.Circuit is a self-contained immutable artifact with the noise compiled in, the DEM is derived by an explicit circuit.detector_error_model() call, and the decoder is named explicitly.  Hidden cross-component reads — the QUITS core finding — do not exist here.

## 2. Swap impact (Q2)

| distance | dimension | before -> after | changed | detail |
|---|---|---|---|---|
| 3 | `noise_parameter` | after_clifford_depolarization=0.001 -> after_clifford_depolarization=0.003 | **True** | `{"num_detectors_before": 24, "num_detectors_after": 24, "num_observables_before": 1, "num_observables_after": 1}` |
| 3 | `noise_parameter` | after_clifford_depolarization=0.003 -> after_clifford_depolarization=0.01 | **True** | `{"num_detectors_before": 24, "num_detectors_after": 24, "num_observables_before": 1, "num_observables_after": 1}` |
| 3 | `export_option` | decompose_errors=True -> decompose_errors=False | **True** | `{"num_errors_decomposed": 285, "num_errors_undecomposed": 218, "structure_identical": false}` |
| 3 | `decoder_prior` | prior from p=0.001 -> prior from p=0.01 (10x, same structure) | **False** | `{"shots": 2000, "structure_identical": true, "differing_predictions": 0, "total_predictions": 2000, "note": "num_neighbours is a deprecated no-op in PyMatching v2, so the prior dimension is measured through the matching graph weights"}` |
| 5 | `noise_parameter` | after_clifford_depolarization=0.001 -> after_clifford_depolarization=0.003 | **True** | `{"num_detectors_before": 72, "num_detectors_after": 72, "num_observables_before": 1, "num_observables_after": 1}` |
| 5 | `noise_parameter` | after_clifford_depolarization=0.003 -> after_clifford_depolarization=0.01 | **True** | `{"num_detectors_before": 72, "num_detectors_after": 72, "num_observables_before": 1, "num_observables_after": 1}` |
| 5 | `export_option` | decompose_errors=True -> decompose_errors=False | **True** | `{"num_errors_decomposed": 1028, "num_errors_undecomposed": 860, "structure_identical": false}` |
| 5 | `decoder_prior` | prior from p=0.001 -> prior from p=0.01 (10x, same structure) | **False** | `{"shots": 2000, "structure_identical": true, "differing_predictions": 0, "total_predictions": 2000, "note": "num_neighbours is a deprecated no-op in PyMatching v2, so the prior dimension is measured through the matching graph weights"}` |

- fingerprints moved: **6/8**
- decoder prior: the decoder-prior swap did NOT move any prediction at this operating point: shifting every edge weight by the common prior factor (log-odds of a 10x noise rescale) leaves the minimum-weight perfect matching unchanged on every sampled shot.  This mirrors QUITS' stale-DEM finding (BP-OSD is prior-robust at low error rates) and is recorded as an honest negative, not a counterexample to visibility — the priors still enter only through the explicit Matching.from_detector_error_model(dem) call.
- conclusion: 6/8 one-component changes moved the artifact fingerprint.  The noise parameter is compiled into the circuit text (dimension 'noise_parameter') and the export option changes the DEM at fixed circuit ('export_option'); the decoder-prior dimension is an honest negative (see decoder_prior_note).  Every dependency appears at the call site — circuit(p) for noise, detector_error_model(decompose_errors=...) for the DEM, Matching.from_detector_error_model(dem) for the decoder's priors.  No hidden cross-component read was observed; had a fingerprint moved without a corresponding call-site change, it would have been recorded here as a counterexample.

## 3. Decoder LER (Q4, small)

| p | errors / shots | LER | Wilson 95% |
|---|---|---|---|
| 0.001 | 1 / 4000 | 0.0003 | [0.0000, 0.0014] |
| 0.003 | 10 / 4000 | 0.0025 | [0.0014, 0.0046] |

- two-proportion z = -2.72, p = 0.00662
- intervals disjoint: **False**; direction consistent (p up -> LER up): **True**
- verdict: noise moves the LER in the same direction as QUITS and the difference is significant at 95%

