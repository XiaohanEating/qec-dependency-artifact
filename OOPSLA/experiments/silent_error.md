# Do stale artifacts silently corrupt a measurement?

Generated: 2026-10-12
Shots: 9600; rounds=2, W=3, F=1, seed=7
Statistics: Wilson 95% per rate; two-proportion z per comparison

## 0. Decoder path validation

The injected-DEM decoder reproduces the official path bitwise on a fresh DEM: **True** (0/288). Every number below is measured on this verified path.

## 1. Two granularities, one definition

Silent error (no error raised; output looks like a plausible measurement; result differs from a full clean rerun at the same spec):
every scenario is reported at the **prediction level** (how many individual decoder predictions change) and the **aggregate level** (whether the reported rate moves outside its Wilson interval).  A scenario can corrupt half the predictions yet leave the headline number untouched; both facts are in the tables below.

## 2. Stale DEM scenarios (derived artifact)

| scenario | structurally different? | fresh rate | stale rate | predictions changed | z | p | silent on rate? |
|---|---|---|---|---|---|---|---|
| zxcoloration circuit, stale DEM from 'custom' schedule | True | 0.1392 | 0.1392 | 307/115200 | -0.030 | 0.976 | **False** |
| SI1000 circuit, stale DEM from 'SD6' | False | 0.0310 | 0.0309 | 5/115200 | 0.036 | 0.971 | **False** |
| SD6-10x circuit, stale DEM from SD6-0.1x | False | 0.4970 | 0.4996 | 57453/115200 | -1.254 | 0.21 | **False** |
| 5-round zxcoloration circuit, stale DEM from 'custom' | n/a | 0.2275 | 0.2284 | 720/115200 | -0.477 | 0.634 | **False** |

- scenarios where the rate moves outside its interval: **0 of 4** (but prediction-level changes are large in all of them: 0.3%, 0.0%, 49.9%, 0.6%)
- verdict: no stale DEM moves the aggregate rate outside its Wilson interval in any of the tested scenarios

### Why each scenario is what it is

- **zxcoloration circuit, stale DEM from 'custom' schedule**: the two schedules produce the same DEM shape (144 detectors, 12 observables, 1152 fault columns) but a different nonzero pattern, so the decoder is solving a slightly different problem
- **SI1000 circuit, stale DEM from 'SD6'**: same DEM structure; only the prior vector differs (SI1000 priors are ~10x smaller than SD6's)
- **SD6-10x circuit, stale DEM from SD6-0.1x**: the largest prior mismatch available in this subject; mean prior differs by ~287x
- **5-round zxcoloration circuit, stale DEM from 'custom'**: longer experiment: more windows, more accumulated priors

## 3. Stale circuit scenarios (primary artifact)

| scenario | declared rate | consumed stale rate | predictions changed | z | p | silent on rate? |
|---|---|---|---|---|---|---|
| declared 5-round circuit, stale 2-round circuit from cache | 0.2277 | 0.1391 | 15332/115200 | 54.984 | 0 | **True** |

- scenarios where the rate moves outside its interval: **1 of 1**
- verdict: a stale primary circuit DOES corrupt the reported rate: the consumed artifact's rate is reported for the declared spec

- **declared 5-round circuit, stale 2-round circuit from cache**: a rounds sweep that does not invalidate the cached circuit reports the previous step's rate for the current spec; the two circuits have different detector counts (252 vs 144), which is in principle detectable, but nothing raises and the number looks normal

## 4. A cache keyed without the noise coordinate

decoder cache keyed on (code, decoder) only

- a cache that omits the noise coordinate returns a stale rate for a new spec; this is the failure the audit predicts, and unlike the DEM cases the rate *does* separate

- cached (SD6) rate: 0.1391
- correct (SI1000) rate: 0.0309
- two-proportion z = 93.08, p = 0
- silent error on rate: **True**

This is the same class as the stale-circuit cases: the cache key omits a coordinate the artifact actually depends on, so a stale primary result is reported for a new spec.

## 5. Interpretation

the aggregate logical error rate is robust to a stale DEM in every scenario tested, even when half the individual predictions change. This does not make stale artifacts harmless: the detector error matrix, the priors and the per-shot predictions all change, and a study that compares decoders on a stale DEM compares them on a model that does not describe its own circuit.  But the failure mode that corrupts the headline number is a stale *primary* artifact (the circuit, or a cache keyed without the noise coordinate), not a stale derived model.

