# External substitutions and statistical follow-ups

Generated: 2026-10-12
Shots: decoder=12000, family=12000, power=12000; rounds=2, W=3, F=1, seed=7
PyMatching: 2.2.0
Statistics: Wilson 95% per rate; two-proportion z per comparison; McNemar-style discordant counts for paired samples; MDE = z*sqrt(2 p(1-p)/n)
Decoder path verified bitwise against the official implementation: **True**

## 1. External decoder (PyMatching) on the same artifact

### SD6 (BB/zxcoloration, 12000 paired shots)

- direct load: decodable = **False** (`No perfect matching could be found. This likely means that the syndrome has odd parity in `)
- graphlike fragment keeps 36 of 432 mechanisms (25.0% of probability mass); observable-carrying graphlike mechanisms: **0**
- stim graphlike decomposition exists: **False**
- per-shot agreement QUITS vs fragment-MWPM: 0.5287 (baseline disagreement, not a bug: different models, and the fragment is logically blind)
- LER any-observable: QUITS 0.4713 vs fragment 0.0000; z = 86.023, p = 0
- discordant pairs: QUITS-fails-only 5656, fragment-fails-only 0

### SI1000 (BB/zxcoloration, 12000 paired shots)

- direct load: decodable = **False** (`No perfect matching could be found. This likely means that the syndrome has odd parity in `)
- graphlike fragment keeps 36 of 432 mechanisms (25.0% of probability mass); observable-carrying graphlike mechanisms: **0**
- stim graphlike decomposition exists: **False**
- per-shot agreement QUITS vs fragment-MWPM: 0.8804 (baseline disagreement, not a bug: different models, and the fragment is logically blind)
- LER any-observable: QUITS 0.1196 vs fragment 0.0000; z = 39.067, p = 0
- discordant pairs: QUITS-fails-only 1435, fragment-fails-only 0

Verdict: no: the artifact is outside PyMatching's fragment. Direct loading silently ignores ~3/4 of the error-model probability mass and crashes on real syndromes; stim cannot decompose the circuit into a graphlike DEM; a repaired fragment graph decodes but is logically blind (zero observable-carrying mechanisms) and disagrees with the subject decoder on every failing shot. The hidden coupling is at the interface level, not the rate level.

## 1b. External decoder (BeliefMatching, hypergraph-capable)

Import order: import ldpc BEFORE beliefmatching (ldpc's __init__ back-imports beliefmatching; reversed order is a circular import)

### SD6 (BB/zxcoloration, 12000 paired shots)

- BP converged: 11898/12000; fallback crashes (decoder failures): 101 (0.84%)
- per-shot agreement: 0.9999; entry agreement: 0.9995 (baseline disagreement, not a bug)
- LER any-observable over the paired (both-decoded) subset: QUITS 0.4684 vs BeliefMatching 0.4683 (strict, decoder failures counted: 0.4728); z = 0.013, p = 0.99
- discordant pairs: QUITS-fails-only 1, BeliefMatching-fails-only 0

### SI1000 (BB/zxcoloration, 12000 paired shots)

- BP converged: 11992/12000; fallback crashes (decoder failures): 8 (0.07%)
- per-shot agreement: 0.9999; entry agreement: 0.9998 (baseline disagreement, not a bug)
- LER any-observable over the paired (both-decoded) subset: QUITS 0.1192 vs BeliefMatching 0.1192 (strict, decoder failures counted: 0.1197); z = 0.020, p = 0.984
- discordant pairs: QUITS-fails-only 1, BeliefMatching-fails-only 0

Verdict: BeliefMatching decodes the artifact that PyMatching cannot: BP converges on >98% of shots and its predictions agree with the subject decoder on 99-100% of them. A semantically different implementation, again near-identical behaviour; the residual discordance is confined to converged-BP shots the sliding window resolves differently, and ~1% of shots are undecodable because the MWPM fallback hits the same boundary-less fragment.

## 2. Code families on a normalised scale

| family | n physical | k logical | raw LER | Wilson 95% | per-logical-bit | Wilson 95% (scaled) |
|---|---|---|---|---|---|---|
| `BB` | 72 | 12 | 0.4713 | [0.4624, 0.4803] | 0.03928 | [0.03853, 0.04002] |
| `HGP` | 13 | 1 | 0.0217 | [0.0192, 0.0244] | 0.02167 | [0.01921, 0.02443] |
| `QLP` | 120 | 5 | 0.4432 | [0.4344, 0.4522] | 0.08865 | [0.08688, 0.09043] |

raw any-observable LER across families is not comparable (a shot fails if ANY of k observables flips); the per-logical-bit scale divides by k_logical so a failure is attributed per logical qubit

## 3. Extractor difference: detection or power bound

- shots per extractor: **12000** (144000 bit-trials per arm)
- per-logical-bit rates: zxcoloration 0.13728, custom 0.14454
- z = -5.602, p = 2.12e-08, significant at 95%: **True**
- MDE at this n: 0.00254; observed difference: 0.00726; detectable: **True**
- formula: MDE = z_0.975 * sqrt(2 * p_bar * (1 - p_bar) / n), z_0.975 = 1.959964

