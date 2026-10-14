# Physical impact on measured QEC quantities

Generated: 2026-10-12
Shots: 9600 per rate, 2400 per ladder point; rounds=2, W=3, F=1, seed=7
Statistics: Wilson 95% interval per rate; two-proportion z-test per comparison, on both the per-logical-bit and any-observable scales

## 0. Decoder path validation

The injected-DEM decoder reproduces the official path bitwise: **True** (0/288 entries differ).

## 1. The noise coordinate moves the rate (positive result)

| spec | errors / shots | per-logical-qubit rate | Wilson 95% | any-observable rate |
|---|---|---|---|---|
| `BB/zxcoloration/SD6` | 16168 / 115200 | 0.1403 | [0.1384, 0.1424] | 0.4789 |
| `BB/zxcoloration/SI1000` | 3662 / 115200 | 0.0318 | [0.0308, 0.0328] | 0.1183 |

- two-proportion z (per-logical-bit) = 92.90, p = 0
- two-proportion z (any-observable) = 46.29, p = 0
- intervals disjoint: **True**
- verdict: the rate moves decisively

## 2. Component substitutions (negative result)

| dimension | substitution | base rate | alt rate | Wilson intervals overlap? | z (per-bit) | p | z (any-obs) | p (any-obs) | separable? |
|---|---|---|---|---|---|---|---|---|---|
| `decoder` | `BP-OSD` -> `BP-LSD` | 0.1404 | 0.1403 | True | 0.012 | 0.99 | 0.000 | 1 | **False** |
| `extractor` | `zxcoloration` -> `custom` | 0.1404 | 0.1438 | True | -2.339 | 0.0193 | 1.113 | 0.266 | **True** |
| `arch` | `transversal` -> `toric` | 0.1403 | 0.1405 | True | -0.084 | 0.933 | -0.014 | 0.988 | **False** |

- separable substitutions (per-logical-bit): **1** of 3
- verdict: at least one substitution separates

Interpretation: BP-OSD and BP-LSD are the same algorithm family on the same syndrome with the same priors; the two extraction schedules differ only in measurement order within a round; TransversalLayout and ToricLayout produce the same circuit because ZXColorationBuilder constructs its own TransversalLayout internally. In each case the decoder's task is identical, so a rate difference is not expected. This is a negative result about the *subject*, not evidence that substitutions are safe in general.

## 3. Rate curve (not a threshold)

| noise | per-logical-qubit rate | Wilson 95% |
|---|---|---|
| `SD6-0.1x` | 0.0167 | [0.0153, 0.0182] |
| `SI1000` | 0.0326 | [0.0306, 0.0347] |
| `SD6` | 0.1331 | [0.1293, 0.1371] |
| `SD6-10x` | 0.4944 | [0.4887, 0.5002] |

- first crossing of 0.25: `{'noise': 'SD6-10x', 'rate': 0.49444444444444446, 'index': 3}`
- caveat: this is a single-code rate curve, not a thermodynamic threshold: no distance scaling is available in this subject, so the number must not be reported as a threshold estimate

