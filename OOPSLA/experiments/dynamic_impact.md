# Dynamic Impact Surface of Five Real QUITS Substitutions

Generated: 2026-10-10  
Object under test: `site-packages/quits/__init__.py` (quits 1.2.0)  
Pinned reference: `0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452`  
Baseline spec: `{'code': 'BB', 'extractor': 'zxcoloration', 'arch': 'transversal', 'noise': 'SD6', 'decoder': 'BP-OSD'}`  
Circuit: num_rounds=2, sampler seed=7, sliding window W=3 F=1; 16 shots (the `decoder_stress` probe uses 128 — see the note in section 4)

## 0. Role of this experiment, and where each compared model's modelling comes from

This file is the **ground truth**: it runs QUITS and measures. The AST read-set extractor (`extract_read_sets.py`) and the static tables (`cone_table`, `artifact_invariance`) are **cross-validation** of these measurements (PIVOT_NOTE section 4, decision 1 of 2026-10-09).

| compared model | question | assembly | read sets from | edges from |
|---|---|---|---|---|
| `source_faithful_coord` | change coordinate x (semantics.coordinate_impact) | `source_faithful` | auto-extracted from the pinned QUITS tree by experiments/extract_read_sets.py (READ_SETS_FROM_SOURCE) | auto-derived: ARTIFACT_READS_FROM_SOURCE minus self-loops (ASSEMBLY_EDGES_FROM_SOURCE): extractor <- code, arch <- code, decoder <- (code, extractor) |
| `source_faithful_cone` | replace component x (Theorem 1) | `source_faithful` | auto-extracted from the pinned QUITS tree by experiments/extract_read_sets.py (READ_SETS_FROM_SOURCE) | auto-derived: ARTIFACT_READS_FROM_SOURCE minus self-loops (ASSEMBLY_EDGES_FROM_SOURCE): extractor <- code, arch <- code, decoder <- (code, extractor) |
| `dataflow_cone` | replace component x on the hand-modelled H3 assembly | `quits_dataflow` | hand-declared conservative H3 model: R(extractor) contains `noise` (build_circuit bakes the error model into the circuit) and R(decoder) is everything embedded in the circuit plus its own coordinate | hand-set, deliberately over-approximating: extractor <- (code, noise); decoder <- (code, extractor, arch, noise); arch <- code (added 2026-10-09 -- the dynamic measurement shows a code substitution changes `layout_positions`, so this edge is real) |

## 1. What changed, per substitution

| substitution | changed artifacts | changed nodes | collateral (unmodified components whose product changed) |
|---|---|---|---|
| `code` | `code_matrices, decoder_output, detector_error_model, layout_positions, logical_observables, stim_circuit` | `arch, code, decoder, extractor` | `arch, decoder, extractor` |
| `extractor` | `decoder_output, detector_error_model, stim_circuit` | `decoder, extractor` | `decoder` |
| `arch` | `layout_positions` | `arch` | `none` |
| `noise` | `decoder_output, detector_error_model, noise_model, stim_circuit` | `decoder, extractor, noise` | `decoder, extractor` |
| `decoder` | `-` | `-` | `none` |
| `arch_none` | `layout_positions` | `arch` | `none` |
| `extractor_inadmissible` | **refused: `NotImplementedError`** | - | - |
| `decoder_stress` | `decoder_output` | `decoder` | `none` |

## 2. Prediction vs measurement

This experiment changes a **spec coordinate**, not a component, so the right predictor is `semantics.coordinate_impact(A, x)` = `{x} ∪ {u : x ∈ R(u)} ∪ ⋃ cone(v)` (readers of the coordinate, closed along the artifact DAG).  Theorem 1's `{x} ∪ cone(x)` is the *component-substitution* view and is shown for comparison; the `dataflow` column is `cone_table`'s conservative H3 model, which since decision 3 (2026-10-09) also carries the `arch <- code` edge this measurement demanded — so its `code` row is no longer an under-approximation.

| substitution | measured | `coordinate_impact` | Theorem-1 cone | dataflow cone | coord-impact covers? |
|---|---|---|---|---|---|
| `code` | `arch, code, decoder, extractor` | `arch, code, decoder, experiment, extractor` | `arch, code, decoder, experiment, extractor` | `arch, code, decoder, experiment, extractor` | **True** |
| `extractor` | `decoder, extractor` | `decoder, experiment, extractor` | `decoder, experiment, extractor` | `decoder, experiment, extractor` | **True** |
| `arch` | `arch` | `arch, experiment` | `arch, experiment` | `arch, decoder, experiment` | **True** |
| `noise` | `decoder, extractor, noise` | `decoder, experiment, extractor, noise` | `experiment, noise` | `decoder, experiment, extractor, noise` | **True** |
| `decoder` | `` | `decoder, experiment` | `decoder, experiment` | `decoder, experiment` | **True** |
| `arch_none` | `arch` | `arch, experiment` | `arch, experiment` | `arch, decoder, experiment` | **True** |
| `decoder_stress` | `decoder` | `decoder, experiment` | `decoder, experiment` | `decoder, experiment` | **True** |

Where each model is *conservative* (demanded a rerun that the measurement showed was unnecessary):

- `code`: coordinate-impact `experiment`; dataflow cone `experiment`
- `extractor`: coordinate-impact `experiment`; dataflow cone `experiment`
- `arch`: coordinate-impact `experiment`; dataflow cone `decoder, experiment`
- `noise`: coordinate-impact `experiment`; dataflow cone `experiment`
- `decoder`: coordinate-impact `decoder, experiment`; dataflow cone `decoder, experiment`
- `arch_none`: coordinate-impact `experiment`; dataflow cone `decoder, experiment`
- `decoder_stress`: coordinate-impact `experiment`; dataflow cone `experiment`

## 3. QUITS-internal modules actually triggered

| substitution | modules executed (baseline) | after | added | removed |
|---|---:|---:|---|---|
| `code` | 18 | 18 | `quits.qldpc_code.qlp` | `quits.qldpc_code.bb` |
| `extractor` | 18 | 17 | `quits.qldpc_code.circuit_construction.custom` | `quits.qldpc_code.circuit_construction.edge_coloration, quits.qldpc_code.circuit_construction.zxcoloration` |
| `arch` | 18 | 21 | `quits.layout.toric, quits.layout.toric_bb, quits.layout.toric_common` | `-` |
| `noise` | 18 | 18 | `-` | `-` |
| `decoder` | 18 | 18 | `quits.decoder.bplsd` | `quits.decoder.bposd` |
| `arch_none` | 18 | 17 | `-` | `quits.layout.__init__` |
| `decoder_stress` | 18 | 18 | `quits.decoder.bplsd` | `quits.decoder.bposd` |

### Modules executed per pipeline stage (baseline)

| stage | quits modules executed |
|---|---|
| `code` | `quits.gf2_util.css, quits.gf2_util.lifted_product, quits.gf2_util.linalg, quits.qldpc_code.base, quits.qldpc_code.bb` |
| `arch` | `quits.layout.__init__, quits.layout.base, quits.layout.transversal` |
| `noise` | `quits.noise.error_model` |
| `extractor` | `quits.circuit, quits.layout.base, quits.layout.transversal, quits.noise.error_model, quits.qldpc_code.base, quits.qldpc_code.bb, quits.qldpc_code.circuit_construction.__init__, quits.qldpc_code.circuit_construction.circuit_build_options, quits.qldpc_code.circuit_construction.edge_coloration, quits.qldpc_code.circuit_construction.zxcoloration` |
| `dem` | `` |
| `observables` | `` |
| `decoder` | `quits.decoder.base, quits.decoder.bposd, quits.decoder.sliding_window, quits.simulation` |

## 4. H1 / H3 checks

- **H3** a noise substitution is **not** circuit-preserving: **True** (True = the stim circuit and its DEM change although only the `noise` coordinate was substituted)
- **H1** an inadmissible extractor substitution is refused by QUITS: **True**
- **H1** the semantic layer refuses the same `(code, extractor)` pair: **True**

At the nominal SD6 operating point BP-OSD and BP-LSD agree on all 16 sampled shots, so the `decoder` row of section 1 is empty; the `decoder_stress` probe repeats the swap at 10x the error rate with 128 shots, where the two decoders diverge. The stress probe needs more shots because the circuit text itself depends on `PYTHONHASHSEED` (see below), and at 16 shots the two decoders agree on every sample for some circuits; the probe is not a locality claim, so the extra shots cost nothing in the substitution rows.

Inadmissible probe detail:

- `BbCode.build_circuit(strategy='cardinal')` -> **refused** (NotImplementedError)
- family whitelist `BbCode.supported_strategies` = `['custom', 'zxcoloration']`
- global builder registry keys (semantics `DOMAIN['extractor']`) = `['cardinal', 'cardinalNSmerge', 'custom', 'hook_error_free', 'zxcoloration']`
- message: `Error: strategy='cardinal' is not supported for BbCode. Supported strategies: custom, zxcoloration.`
- `get_layout()` default: `None`

### Reproducibility of the stim-circuit artifact

- fingerprints by `PYTHONHASHSEED`: `{'0': 'ebd3d7b56e09206a', '1': '09b5194d018246bc', '12345': '6b45af3a173966af'}`
- distinct fingerprints: **3** (deterministic: **False**)
- networkx hopcroft_karp_matching iterates over a set, so the circuit text depends on PYTHONHASHSEED; the experiment re-execs itself with PYTHONHASHSEED=0 so the fingerprints in this file are reproducible.

## 5. Alignment with the static QUITS_CALL_SITES model

| dimension | real site | static modelling | measured | aligned |
|---|---|---|---|---|
| `extractor` | `circuit_construction/__init__.py:9-14,17-23` | hidden-dependency 探测报 observed ⊄ declared → cone unbounded | changed=decoder_output,detector_error_model,stim_circuit, collateral=decoder, modules=17 | **True** |
| `decoder` | `simulation.py:50-56` | 义务写成 contract 可检查（syndrome 语义保持） | changed=decoder_output, collateral=none, modules=18 | **True** |
| `noise` | `noise/error_model.py:37-42` | contract = circuit builder 依赖的性质，而非形状 | changed=decoder_output,detector_error_model,noise_model,stim_circuit, collateral=decoder,extractor, modules=18 | **True** |
| `code` | `qldpc_code/__init__.py:3-10, base.py:30-50` | contract = CSS 对易（hz·hxᵀ ≡ hx·hzᵀ） | changed=code_matrices,decoder_output,detector_error_model,layout_positions,logical_observables,stim_circuit, collateral=arch,decoder,extractor, modules=18 | **True** |
| `arch` | `layout/base.py:22; qldpc_code/base.py:55-57` | 读集合显式包含 arch 坐标 | changed=layout_positions, collateral=none, modules=17 | **True** |
- **extractor**: H1: the substituted strategy is on the family whitelist, so the assembly succeeds; the inadmissible variant is measured separately (see `inadmissible_probe`).
- **decoder**: the decoder artifact changes but no upstream artifact does: decoder substitution is the most local of the five.
- **noise**: H3 confirmed: replacing only the noise model changes the stim circuit and its DEM, i.e. the extractor artifact, so a noise substitution is NOT circuit-preserving.
- **code**: the code artifact feeds arch (Layout(code)), the extractor (build_circuit is a QldpcCode method) and the decoder (hz/lz); the measured collateral matches the auto-extracted edges exactly.
- **arch**: layout substitution changes only the layout artifact: the extractor builds its own TransversalLayout internally, so swapping the arch coordinate is circuit-preserving.

## 6. Modelling corrections demanded by the measurement

| model | verdict | what the measurement says | action |
|---|---|---|---|
| `semantics._mk_components()` hand-declared `R(extractor)` | **under-approximates** | a noise substitution changes the stim circuit | **fixed**: `READ_SETS_FROM_SOURCE` adds `noise` (derived by `extract_read_sets.py`, locked by pytest) |
| `semantics._mk_components()` `arch` / `decoder` read sets | **need re-classification, not repair** | `Layout(code)` and `get_codecap_pL(code, ...)` are artifact flows, not coordinate reads | **fixed**: split into `READ_SETS_FROM_SOURCE` (coordinates) + `ARTIFACT_READS_FROM_SOURCE` (DAG edges) |
| `build_circuit` receiver (`self`) | **not modelled** | `build_circuit` is a `QldpcCode` method, so replacing the code component changes the extractor artifact | **fixed**: the extractor now resolves `self` to the code artifact, giving the edge `extractor <- code` |
| Theorem 1's `cone(x)` as a predictor of a *coordinate* change | **wrong question** | changing `noise` changes the extractor artifact, but `cone(noise)` does not contain it | **fixed**: added `semantics.coordinate_impact(A, x)`, which closes the coordinate readers along the DAG |
| `cone_table.make_quits_dataflow_assembly()` | **one edge too few** | the `code` substitution changes `layout_positions`, but that assembly had no `arch <- code` edge | **fixed** (decision 3, 2026-10-09): the edge is added, so `cone(code) = {extractor, arch, decoder, experiment}`; this file's `dataflow cone` column is regenerated from the corrected assembly |

## 7. Summary

- substitutions: **8** (measured 7, refused 1)
- `coordinate_impact` covers every measured impact set: **True**
- Theorem-1 cone (component substitution) covers every measured impact set: **False**
- `cone_table`'s dataflow cone covers every measured impact set: **True**
- collateral nodes per dimension: `{'code': ['arch', 'decoder', 'extractor'], 'extractor': ['decoder'], 'arch': [], 'noise': ['decoder', 'extractor'], 'decoder': []}`

