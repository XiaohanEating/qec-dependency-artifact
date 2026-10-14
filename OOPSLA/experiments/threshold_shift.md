# Threshold shift under noise-model substitution

Generated: 2026-10-12
Shots: 4000 per point; rounds=2, W=3, F=1, seed=7
Representative error rate p: sqgate_error (single-qubit gate error of the uniformly scaled model)
p_th search range: [0.0001, 0.03]; bootstrap reps: 200
Statistics: Wilson 95% per rate; threshold by grid-search least squares on log pL ~ log(p - p_th); parametric bootstrap (binomial resampling) for the threshold difference CI

## 0. Timing probe

Largest code d=6 (l=3, m=9), p=0.001, 4000 shots: **9.1s** (budget 90s, kept: **True**).

## 1. Code family and distance evidence

The requested `BbCode(l=d, m=d)` for d in {3,5,7} is degenerate for the pinned shift polynomials, so the scan uses `(l, m) = (3, 3d)`. Measured parameters (distance = minimum weight over the span of the logical-operator basis):

| distance d | (l, m) | n | k | min lz-span wt | min lx-span wt |
|---|---|---|---|---|---|
| 2 | (3, 3) | 18 | 8 | 2 | 2 |
| 4 | (3, 6) | 36 | 8 | 4 | 4 |
| 6 | (3, 9) | 54 | 8 | 6 | 6 |

Cross-check at (l, m) = (6, 6): n=72, k=12, distance=6 -- expected [[72,12,6]] bivariate bicycle code (arXiv:2308.07915): **match = True**

Evidence (pinned tree):
- `quits/qldpc_code/bb.py:30 -- construction follows arXiv:2308.07915 (the [[72,12,6]] BB code lives at l=m=6 with these polynomials)`
- `quits/qldpc_code/bb.py:36 -- self.l, self.m stored; size = l * m`
- `quits/qldpc_code/bb.py:40-60 -- A = x^3 + y + y^2, B = x + x^2 + y^3 over circulant rings of order (l, m)`
- `quits/qldpc_code/bb.py:62-63 -- hx = [A B], hz = [B^T A^T]: n = 2*l*m physical qubits`
- `quits/qldpc_code/bb.py:64 -- lz, lx = compute_lz_and_lx(hz, hx): k = len(lz) logical qubits; distance estimated as the minimum weight over the span of lz / lx`

Requested `l=m=d` probe: the brief asked for BbCode(l=d, m=d) with d in {3,5,7}; with the pinned shift polynomials that family is degenerate (d=3 encodes k=8 at distance 2; d=5 and d=7 encode k=0, i.e. there is no logical qubit to decode), so the scan uses the nearest valid family (l, m) = (3, 3d) with measured distances {2,4,6}

| l=m | n | k | min lz-span wt |
|---|---|---|---|
| 3 | 18 | 8 | 2 |
| 5 | 50 | 0 | None |
| 7 | 98 | 0 | None |

## 2. Measured points

| d | (l, m) | noise | p (sqgate) | scale s | errors / shots | per-qubit rate | Wilson 95% |
|---|---|---|---|---|---|---|---|
| 2 | (3, 3) | SD6 | 0.0004 | 0.4 | 181 / 32000 | 0.0057 | [0.0049, 0.0065] |
| 2 | (3, 3) | SD6 | 0.0006 | 0.6 | 280 / 32000 | 0.0088 | [0.0078, 0.0098] |
| 2 | (3, 3) | SD6 | 0.0008 | 0.8 | 356 / 32000 | 0.0111 | [0.0100, 0.0123] |
| 2 | (3, 3) | SD6 | 0.001 | 1 | 477 / 32000 | 0.0149 | [0.0136, 0.0163] |
| 2 | (3, 3) | SD6 | 0.0014 | 1.4 | 601 / 32000 | 0.0188 | [0.0174, 0.0203] |
| 2 | (3, 3) | SD6 | 0.002 | 2 | 825 / 32000 | 0.0258 | [0.0241, 0.0276] |
| 2 | (3, 3) | SD6 | 0.0035 | 3.5 | 1339 / 32000 | 0.0418 | [0.0397, 0.0441] |
| 2 | (3, 3) | SD6 | 0.006 | 6 | 1951 / 32000 | 0.0610 | [0.0584, 0.0636] |
| 2 | (3, 3) | SD6 | 0.012 | 12 | 2763 / 32000 | 0.0863 | [0.0833, 0.0895] |
| 2 | (3, 3) | SD6 | 0.02 | 20 | 1646 / 32000 | 0.0514 | [0.0491, 0.0539] |
| 2 | (3, 3) | SI1000 | 0.0004 | 2 | 170 / 32000 | 0.0053 | [0.0046, 0.0062] |
| 2 | (3, 3) | SI1000 | 0.0006 | 3 | 279 / 32000 | 0.0087 | [0.0078, 0.0098] |
| 2 | (3, 3) | SI1000 | 0.0008 | 4 | 358 / 32000 | 0.0112 | [0.0101, 0.0124] |
| 2 | (3, 3) | SI1000 | 0.001 | 5 | 449 / 32000 | 0.0140 | [0.0128, 0.0154] |
| 2 | (3, 3) | SI1000 | 0.0014 | 7 | 615 / 32000 | 0.0192 | [0.0178, 0.0208] |
| 2 | (3, 3) | SI1000 | 0.002 | 10 | 824 / 32000 | 0.0257 | [0.0241, 0.0275] |
| 2 | (3, 3) | SI1000 | 0.0035 | 17.5 | 1346 / 32000 | 0.0421 | [0.0399, 0.0443] |
| 2 | (3, 3) | SI1000 | 0.006 | 30 | 2008 / 32000 | 0.0628 | [0.0601, 0.0655] |
| 2 | (3, 3) | SI1000 | 0.012 | 60 | 2810 / 32000 | 0.0878 | [0.0848, 0.0910] |
| 2 | (3, 3) | SI1000 | 0.02 | 100 | 1529 / 32000 | 0.0478 | [0.0455, 0.0502] |
| 4 | (3, 6) | SD6 | 0.0004 | 0.4 | 996 / 32000 | 0.0311 | [0.0293, 0.0331] |
| 4 | (3, 6) | SD6 | 0.0006 | 0.6 | 1398 / 32000 | 0.0437 | [0.0415, 0.0460] |
| 4 | (3, 6) | SD6 | 0.0008 | 0.8 | 1863 / 32000 | 0.0582 | [0.0557, 0.0608] |
| 4 | (3, 6) | SD6 | 0.001 | 1 | 2286 / 32000 | 0.0714 | [0.0687, 0.0743] |
| 4 | (3, 6) | SD6 | 0.0014 | 1.4 | 3207 / 32000 | 0.1002 | [0.0970, 0.1036] |
| 4 | (3, 6) | SD6 | 0.002 | 2 | 4225 / 32000 | 0.1320 | [0.1284, 0.1358] |
| 4 | (3, 6) | SD6 | 0.0035 | 3.5 | 6643 / 32000 | 0.2076 | [0.2032, 0.2121] |
| 4 | (3, 6) | SD6 | 0.006 | 6 | 9394 / 32000 | 0.2936 | [0.2886, 0.2986] |
| 4 | (3, 6) | SD6 | 0.012 | 12 | 13121 / 32000 | 0.4100 | [0.4047, 0.4154] |
| 4 | (3, 6) | SD6 | 0.02 | 20 | 14619 / 32000 | 0.4568 | [0.4514, 0.4623] |
| 4 | (3, 6) | SI1000 | 0.0004 | 2 | 985 / 32000 | 0.0308 | [0.0289, 0.0327] |
| 4 | (3, 6) | SI1000 | 0.0006 | 3 | 1400 / 32000 | 0.0437 | [0.0416, 0.0460] |
| 4 | (3, 6) | SI1000 | 0.0008 | 4 | 1851 / 32000 | 0.0578 | [0.0553, 0.0605] |
| 4 | (3, 6) | SI1000 | 0.001 | 5 | 2317 / 32000 | 0.0724 | [0.0696, 0.0753] |
| 4 | (3, 6) | SI1000 | 0.0014 | 7 | 3195 / 32000 | 0.0998 | [0.0966, 0.1032] |
| 4 | (3, 6) | SI1000 | 0.002 | 10 | 4300 / 32000 | 0.1344 | [0.1307, 0.1382] |
| 4 | (3, 6) | SI1000 | 0.0035 | 17.5 | 6660 / 32000 | 0.2081 | [0.2037, 0.2126] |
| 4 | (3, 6) | SI1000 | 0.006 | 30 | 9306 / 32000 | 0.2908 | [0.2859, 0.2958] |
| 4 | (3, 6) | SI1000 | 0.012 | 60 | 13101 / 32000 | 0.4094 | [0.4040, 0.4148] |
| 4 | (3, 6) | SI1000 | 0.02 | 100 | 14762 / 32000 | 0.4613 | [0.4559, 0.4668] |
| 6 | (3, 9) | SD6 | 0.0004 | 0.4 | 1417 / 32000 | 0.0443 | [0.0421, 0.0466] |
| 6 | (3, 9) | SD6 | 0.0006 | 0.6 | 1955 / 32000 | 0.0611 | [0.0585, 0.0638] |
| 6 | (3, 9) | SD6 | 0.0008 | 0.8 | 2637 / 32000 | 0.0824 | [0.0794, 0.0855] |
| 6 | (3, 9) | SD6 | 0.001 | 1 | 3203 / 32000 | 0.1001 | [0.0969, 0.1034] |
| 6 | (3, 9) | SD6 | 0.0014 | 1.4 | 4310 / 32000 | 0.1347 | [0.1310, 0.1385] |
| 6 | (3, 9) | SD6 | 0.002 | 2 | 5679 / 32000 | 0.1775 | [0.1733, 0.1817] |
| 6 | (3, 9) | SD6 | 0.0035 | 3.5 | 8545 / 32000 | 0.2670 | [0.2622, 0.2719] |
| 6 | (3, 9) | SD6 | 0.006 | 6 | 11590 / 32000 | 0.3622 | [0.3569, 0.3675] |
| 6 | (3, 9) | SD6 | 0.012 | 12 | 14790 / 32000 | 0.4622 | [0.4567, 0.4677] |
| 6 | (3, 9) | SD6 | 0.02 | 20 | 15564 / 32000 | 0.4864 | [0.4809, 0.4919] |
| 6 | (3, 9) | SI1000 | 0.0004 | 2 | 1420 / 32000 | 0.0444 | [0.0422, 0.0467] |
| 6 | (3, 9) | SI1000 | 0.0006 | 3 | 1960 / 32000 | 0.0612 | [0.0587, 0.0639] |
| 6 | (3, 9) | SI1000 | 0.0008 | 4 | 2647 / 32000 | 0.0827 | [0.0798, 0.0858] |
| 6 | (3, 9) | SI1000 | 0.001 | 5 | 3208 / 32000 | 0.1003 | [0.0970, 0.1036] |
| 6 | (3, 9) | SI1000 | 0.0014 | 7 | 4315 / 32000 | 0.1348 | [0.1311, 0.1386] |
| 6 | (3, 9) | SI1000 | 0.002 | 10 | 5681 / 32000 | 0.1775 | [0.1734, 0.1818] |
| 6 | (3, 9) | SI1000 | 0.0035 | 17.5 | 8528 / 32000 | 0.2665 | [0.2617, 0.2714] |
| 6 | (3, 9) | SI1000 | 0.006 | 30 | 11546 / 32000 | 0.3608 | [0.3556, 0.3661] |
| 6 | (3, 9) | SI1000 | 0.012 | 60 | 14759 / 32000 | 0.4612 | [0.4558, 0.4667] |
| 6 | (3, 9) | SI1000 | 0.02 | 100 | 15665 / 32000 | 0.4895 | [0.4841, 0.4950] |

## 3. Threshold fits (pL = A (p - p_th)^nu)

| model | p_th | A | nu | R^2 | n points | at range boundary | valid |
|---|---|---|---|---|---|---|---|
| SD6 | 0.006612 | 0.1278 | -0.131 | 0.0043 | 6 | False | True |
| SI1000 | 0.006156 | 0.1086 | -0.166 | 0.0058 | 6 | False | True |

## 4. Threshold difference (SD6 - SI1000), parametric bootstrap

- p_th(SD6)  bootstrap mean: 0.00658 (200/200 fits valid)
- p_th(SI1000) bootstrap mean: 0.006314 (200/200 fits valid)
- difference mean: 0.000266
- 95% CI of the difference: [-0.002658, 0.004333]
- **verdict: thresholds NOT separable at 95% (CI includes 0)**

Note: SI1000 is exactly 0.2x SD6 on every noise parameter, so the two parameterisations define the same circuit family in absolute error-rate units and a genuine threshold separation is *not* expected; the interval above measures whether the finite-size fit artificially invents one.

## 5. Caveats

num_rounds=2 throughout: the fitted p_th is a two-round pseudo-threshold, a finite-size estimate that must not be reported as the thermodynamic threshold of the BB family. The fit pools distances without the d-dependent prefactor of true critical scaling, and at the top of the grid the windowed decoder saturates (predictions collapse toward no-error as the syndrome becomes uninformative).

Design adjustments from the brief, for the record:

- l=m=d in {3,5,7} is degenerate for the pinned polynomials (k=0 for d=5,7; [[18,8,2]] for d=3); scan uses (l,m)=(3,3d), measured distances {2,4,6}; see code_evidence
- sweep anchored on a shared absolute sqgate_error grid (4e-4..2e-2) instead of a per-model scale factor s, because SI1000 is exactly 0.2x SD6 and threshold comparison needs absolute units; for SD6 this equals s in {0.4..20} on its baseline
- error-rate grid and p_th search range extended above the brief (s>2, range [1e-4,5e-3]) because a calibration probe showed the 2-round pseudo-threshold region lies above 2e-3 sqgate_error (d=4/d=6 curves cross near s=12)

