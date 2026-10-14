# Semantically different substitutions, measured with confidence

Generated: 2026-10-12
Shots: 12000; rounds=2, W=3, F=1, seed=7
Statistics: Wilson 95% per rate; two-proportion z per comparison on both the per-logical-bit and any-observable scales
Decoder path verified bitwise against the official implementation: **True**

## 1. Code families (not a like-for-like substitution)

| family | n | k | detectors | per-logical-qubit rate | Wilson 95% |
|---|---|---|---|---|---|
| `BB` | 72 | 12 | 144 | 0.1377 | [0.1359, 0.1395] |
| `HGP` | 13 | 1 | 24 | 0.0212 | [0.0187, 0.0239] |
| `QLP` | 120 | 5 | 192 | 0.1150 | [0.1125, 0.1176] |

the three families have different distances and logical-qubit counts, so their rates are not comparable as a substitution measurement; a like-for-like comparison needs a fixed distance, which this subject does not expose

## 2. Substitutions with a rate comparison

| dimension | substitution | artifact changed? | structure changed? | base rate | alt rate | z (per-bit) | p | z (any-obs) | p (any-obs) | rate separable? |
|---|---|---|---|---|---|---|---|---|---|---|
| `extractor` | `base` -> `alt` | True | True | 0.1378 | 0.1445 | -5.191 | 2.09e-07 | -0.673 | 0.501 | **True** |
| `arch` | `base` -> `alt` | False | False | 0.1377 | 0.1377 | -0.032 | 0.974 | 0.026 | 0.979 | **False** |
| `noise` | `base` -> `alt` | True | False | 0.1377 | 0.0319 | 101.888 | 0 | 59.623 | 0 | **True** |
| `decoder` | `BP-OSD` -> `BP-LSD` | False | False | 0.1376 | 0.1378 | -0.157 | 0.875 | -0.013 | 0.99 | **False** |

- artifact-changing substitutions: **3 of 5**
- rate-separable substitutions (per-logical-bit): **2 of 4**; any-observable scale: **1 of 4**
- verdict: artifact changes and rate changes are different questions: 3 of 5 substitutions change an artifact, but only 2 of 4 comparable rate comparisons separate (per-logical-bit scale; 1 separate on the any-observable scale)

### Per-substitution notes

- **code**: the three families have different distances and logical-qubit counts, so their rates are not comparable as a substitution measurement; a like-for-like comparison needs a fixed distance, which this subject does not expose
- **arch**: the layout changes but the circuit does not: ZXColorationBuilder constructs its own TransversalLayout internally, so the arch coordinate does not reach the artifact
- **noise**: the noise coordinate is baked into the circuit: changing it changes the circuit text and the detector error model, which is the audit's third observation (extractor reads noise)
- **decoder**: both decoders run on identical circuits and identical sampled syndromes; the only difference is the inner decoder class

## 3. Interpretation

an artifact-level substitution is not automatically a rate-level substitution. The noise coordinate changes both, because it is baked into the circuit. The decoder substitution changes no artifact and no rate, because the decoder's task is unchanged. The extractor substitution is scale-dependent: it changes the circuit and moves the per-logical-bit rate (the two extraction schedules distribute the same physical errors differently across the 12 observables), while the any-observable failure rate is unchanged. A study that substitutes a decoder and reports 'no significant difference' is reporting a real property of the substitution, not a null result about the software.

