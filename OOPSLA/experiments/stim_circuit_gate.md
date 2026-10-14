# Real-Artifact Gate for the Toy Model

Generated: 2026-10-12  
Object under test: `third_party/quits-0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452/src/quits/__init__.py` (quits 1.2.0)  
Pinned reference: `0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452`  
Mode: **default**  
Baseline assembly: **`source_faithful`**  
Semantic verdicts read from: `experiments/artifact_invariance.run(48)`  
Circuit: num_rounds=2, sampler seed=7, 16 shots, sliding window W=3 F=1

## 0. What this experiment is

The semantic layer's ``produce`` functions are a toy model: they return dicts and strings.  This file rebuilds the same assembly with **real** QUITS artifacts (a real ``stim.Circuit``, a real detector error model, real code matrices, a real layout mapping, a real decoder prediction) and asks whether the semantic layer's verdicts survive.  The verdict itself is not recomputed here: it is read from the published ``artifact_invariance`` experiment, so the two levels are compared on identical input.

Per (configuration, dimension) the gate substitutes an alternative implementation that is **pointwise equal on ``R(x)``** but reached through a different QUITS call path, and compares, byte for byte:

| compared quantity | how |
|---|---|
| stim circuit text | ``str(circuit_before) == str(circuit_after)`` |
| detector error model | ``str(dem_before) == str(dem_after)`` |
| code matrices / layout / decoder | per-node artifact equality |
| Theorem 1 worksheet | every node outside ``{x} ∪ cone(x)`` must be equal |

## 1. The gate, per configuration

| config | dim | semantic verdict | circuit text equal | DEM equal | all unchanged nodes equal | gate agrees |
|---|---|---|---|:---:|:---:|:---:|:---:|
| `BB/free/zxcoloration/SD6/BP-OSD` | `code` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `BB/free/zxcoloration/SD6/BP-OSD` | `extractor` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `BB/free/zxcoloration/SD6/BP-OSD` | `arch` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `BB/free/zxcoloration/SD6/BP-OSD` | `noise` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `BB/free/zxcoloration/SD6/BP-OSD` | `decoder` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `BB/free/zxcoloration/SI1000/BP-LSD` | `code` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `BB/free/zxcoloration/SI1000/BP-LSD` | `extractor` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `BB/free/zxcoloration/SI1000/BP-LSD` | `arch` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `BB/free/zxcoloration/SI1000/BP-LSD` | `noise` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `BB/free/zxcoloration/SI1000/BP-LSD` | `decoder` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `HGP/free/cardinal/SD6/BP-OSD` | `code` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `HGP/free/cardinal/SD6/BP-OSD` | `extractor` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `HGP/free/cardinal/SD6/BP-OSD` | `arch` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `HGP/free/cardinal/SD6/BP-OSD` | `noise` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `HGP/free/cardinal/SD6/BP-OSD` | `decoder` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `HGP/free/zxcoloration/SI1000/BP-LSD` | `code` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `HGP/free/zxcoloration/SI1000/BP-LSD` | `extractor` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `HGP/free/zxcoloration/SI1000/BP-LSD` | `arch` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `HGP/free/zxcoloration/SI1000/BP-LSD` | `noise` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `HGP/free/zxcoloration/SI1000/BP-LSD` | `decoder` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `QLP/free/cardinal/SD6/BP-OSD` | `code` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `QLP/free/cardinal/SD6/BP-OSD` | `extractor` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `QLP/free/cardinal/SD6/BP-OSD` | `arch` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `QLP/free/cardinal/SD6/BP-OSD` | `noise` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `QLP/free/cardinal/SD6/BP-OSD` | `decoder` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `QLP/free/zxcoloration/SI1000/BP-LSD` | `code` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `QLP/free/zxcoloration/SI1000/BP-LSD` | `extractor` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `QLP/free/zxcoloration/SI1000/BP-LSD` | `arch` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `QLP/free/zxcoloration/SI1000/BP-LSD` | `noise` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |
| `QLP/free/zxcoloration/SI1000/BP-LSD` | `decoder` | applicable=True invariance_ok=True | **True** | **True** | **True** | **True** |

## 2. Baselines (the artifacts both sides must agree on)

| config | circuit sha256 | DEM sha256 | circuit chars | code-family | CSS commutes |
|---|---|---|---:|---|---|
| `BB/free/zxcoloration/SD6/BP-OSD` | `1c97770338298ecc` | `845e907ae31e425f` | 30992 | BbCode | True |
| `BB/free/zxcoloration/SI1000/BP-LSD` | `d5e28d9ebee631eb` | `1f2379056f13a08b` | 30997 | BbCode | True |
| `HGP/free/cardinal/SD6/BP-OSD` | `99be5bfaee0e2086` | `56438c8e4501e55f` | 3127 | HgpCode | True |
| `HGP/free/zxcoloration/SI1000/BP-LSD` | `c0c335d7428e4fda` | `59cdfcb483700003` | 4410 | HgpCode | True |
| `QLP/free/cardinal/SD6/BP-OSD` | `03fb90b99faba185` | `e394289326083578` | 35026 | QlpCode | True |
| `QLP/free/zxcoloration/SI1000/BP-LSD` | `048363cbec88f710` | `da966592ae46b7d9` | 42595 | QlpCode | True |

## 3. Alternative implementations (one per dimension)

| dimension | alternative call path |
|---|---|
| `code` | the same family constructor, invoked with a different spelling of the construction arguments (BB: power lists vs tuples; HGP/QLP: int vs uint8 base matrices) |
| `extractor` | the builder is reached directly through the strategy registry (``get_builder``) instead of through ``QldpcCode.build_circuit``'s dispatch, or the default ``CircuitBuildOptions`` is materialised by the caller instead of the callee |
| `arch` | the layout is constructed with every optional argument spelled out (``TransversalLayout`` explicit defaults, or the concrete ``BbToricLayout`` instead of the ``ToricLayout`` factory) |
| `noise` | ``ErrorModel`` is constructed positionally instead of by keyword |
| `decoder` | the generic ``sliding_window_circuit_mem`` entry point is called with an explicit inner-decoder class and parameter dicts, instead of the ``sliding_window_bposd_circuit_mem`` convenience wrapper |

## 4. Negative controls

### 4.1 noise coordinate change (SD6 -> SI1000) (coordinate change, not a component substitution)

- circuit text equal: **False** (`1c97770338298ecc` -> `d5e28d9ebee631eb`)
- DEM text equal: **False** (`845e907ae31e425f` -> `1f2379056f13a08b`)
- changed nodes: `decoder, extractor`
- H3 confirmed on the real artifact: the noise coordinate is baked into the circuit, so changing it is NOT circuit-preserving -- while substituting the noise *component* (an equal-valued ErrorModel built by a different call path) is.

### 4.2 H1: BB + cardinal is inadmissible

- family whitelist: `['custom', 'zxcoloration']`
- global registry: `['cardinal', 'cardinalNSmerge', 'custom', 'hook_error_free', 'zxcoloration']`
- QUITS outcome: **refused** (NotImplementedError)
- semantic layer outcome (before assembly): **refused**

### 4.3 arch = grid2d on a non-BB family

| family | QUITS outcome | semantic contract | n_positions |
|---|:---:|:---:|---:|
| `BB` | **assembled** | True | 72 |
| `HGP` | **refused** | False | - |
| `QLP` | **refused** | False | - |

- a second hidden cross-component dependency of exactly the H1 shape: whether a layout can be used is a property of the code component, checked by QUITS at run time and by the semantic layer's arch contract before assembly

### 4.4 decoder value swap (BP-OSD -> BP-LSD) (a substitution that is NOT pointwise equal on R(x))

- checker ``applicable``: **False** (cone: `experiment`)
- (C4) ``pointwise_equal_on_reads``: **False** -- this is the side condition that fails, and it is why the checker refuses
- the checker's job is to refuse here, and it does: (C4) fails, so no 'cone 外不变' claim is made

## 5. Summary

- configurations: **6**, substitutions: **30**
- stim circuit text equal on every substitution: **True** (30/30)
- DEM text equal on every substitution: **True** (30/30)
- every provably-unchanged node equal: **30/30**
- **gate agrees with the semantic verdict on every row: True** (30/30)

| dimension | substitutions | circuit equal | DEM equal | gate agrees |
|---|---:|---:|---:|---:|
| `code` | 6 | 6 | 6 | 6 |
| `extractor` | 6 | 6 | 6 | 6 |
| `arch` | 6 | 6 | 6 | 6 |
| `noise` | 6 | 6 | 6 | 6 |
| `decoder` | 6 | 6 | 6 | 6 |

- **H3** a noise *coordinate* change is not local (real circuit text differs): **True**
- **H1** an inadmissible pair is refused by QUITS (True) and the semantic layer refuses the same pair before assembly (True)
- **H1 (second instance)** ``arch = grid2d`` on a non-BB family is refused: **True**
- a non-(C4) substitution is refused by the checker: **True** (pointwise equality holds: False)

## 6. What the gate does and does not narrow

**Narrowed.** The artifacts are no longer dicts: the assembly layer produces real stim circuits and detector error models, and Theorem 1's "unchanged outside `{x} ∪ cone(x)`" holds byte-for-byte on them for these configurations.  The toy-model boundary moves from "the artifacts are toy" to "the artifacts are real, on these configurations, via these five call paths".

**Not narrowed.** (a) ``--full`` sweeps all 48 configurations; the default run is the six listed above.  (b) A *distinct* second implementation of a code family does not exist in QUITS -- the family constructor is the only path -- so the ``code`` row is a spelling variant, which is direct evidence for PIVOT_NOTE §8.6 claim 2 ("(C4) is not a practical substitution condition").  (c) The stim circuit is not a stable artifact: ``dynamic_impact.py`` measured that its text depends on ``PYTHONHASHSEED``, so this script re-executes itself with ``PYTHONHASHSEED=0`` and the fingerprints here are reproducible only under that pin.

