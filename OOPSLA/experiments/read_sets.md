# Read Sets R(c) - auto-extracted from the pinned QUITS tree

Generated: 2026-10-09  
QUITS commit: `0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452`  
Source: `third_party/quits-0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452/src/quits`  
Method: AST static analysis; component granularity from gate_audit/protocol.md; anchors located by AST search; coordinate / artifact / sub_api attribution

> The component granularity is **not** chosen by this script: it is the pre-registered boundary of `gate_audit/protocol.md`.

`R(c)` is the **spec-coordinate** read set (what `semantics.Component.reads` denotes).  `artifact_reads` are references to another component's *artifact object* (the `QldpcCode` instance, the `stim.Circuit`, `hz`/`lx`): under the general model of PIVOT_NOTE 6.0 (`produce : Spec x predecessor artifacts -> Artifact`) those are DAG **edges**, not coordinate reads.  `reads_flat` is the arity-1 flattening of the two.

## 0. Role: cross-validation, not ground truth

This extractor's status is **cross-validation**. The ground truth is `experiments/dynamic_impact.py (runs QUITS and measures the impact surface of five real substitutions)`, which runs QUITS and *measures* the impact surface of five real substitutions.

What it claims: the read sets reported here are correct with respect to the pinned QUITS source; the dynamic experiment independently confirms the dependency structure they imply

Since decision 2 (2026-10-09) these read sets **are** the published baseline (`source_faithful`):
- read sets: auto-extracted from the pinned QUITS tree by experiments/extract_read_sets.py (READ_SETS_FROM_SOURCE)
- DAG edges: auto-derived: ARTIFACT_READS_FROM_SOURCE minus self-loops (ASSEMBLY_EDGES_FROM_SOURCE): extractor <- code, arch <- code, decoder <- (code, extractor)

Hand-modelled counterpart `experiments.cone_table.make_quits_dataflow_assembly()`: read sets = hand-declared conservative H3 model: R(extractor) contains `noise` (build_circuit bakes the error model into the circuit) and R(decoder) is everything embedded in the circuit plus its own coordinate; edges = hand-set, deliberately over-approximating: extractor <- (code, noise); decoder <- (code, extractor, arch, noise); arch <- code (added 2026-10-09 -- the dynamic measurement shows a code substitution changes `layout_positions`, so this edge is real)

Scope limits: the evidence channels are declaration/attribute/name/string/keyword/callee/argument; ambiguous names are dropped rather than guessed, so the result is a conservative *under*-approximation (PIVOT_NOTE section 8.6 item 8)

## 1. Auto-extracted read sets

| dimension | R(c) (coordinates) | artifact_reads | reads_flat | sub_api | anchors |
|---|---|---|---|---|---:|
| `code` | `code` | `code` | `code` | `code` | 10 |
| `extractor` | `code, extractor, noise` | `code` | `code, extractor, noise` | `extractor, noise` | 8 |
| `arch` | `arch` | `arch, code` | `arch, code` | `arch, code` | 7 |
| `noise` | `noise` | `noise` | `noise` | `noise` | 3 |
| `decoder` | `decoder` | `code, extractor` | `code, decoder, extractor` | `decoder` | 4 |

### Per-dimension detail

**`code`** - anchors and what each one reads:

| anchor | R(c) here | artifact reads here |
|---|---|---|
| `qldpc_code/base.py:22` `QldpcCode.__init__` | `-` | `code` |
| `qldpc_code/base.py:37` `QldpcCode.set_parity_checks` | `-` | `code` |
| `qldpc_code/base.py:52` `QldpcCode.verify_css_logicals` | `-` | `code` |
| `qldpc_code/bb.py:21` `BbCode.__init__` | `-` | `code` |
| `qldpc_code/bpc.py:17` `BpcCode.__init__` | `code` | `code` |
| `qldpc_code/hgp.py:17` `HgpCode.__init__` | `code` | `code` |
| `qldpc_code/lcs.py:26` `LcsCode.__init__` | `code` | `code` |
| `qldpc_code/mitten.py:183` `MittenCode.__init__` | `-` | `code` |
| `qldpc_code/qlp.py:17` `QlpCode.__init__` | `code` | `code` |
| `qldpc_code/qlp.py:206` `QlpPolyCode.__init__` | `code` | `code` |

<details><summary>evidence</summary>

- `code`:
    - `qldpc_code/base.py:22 [attribute/artifact] reads `.all_qubits``
    - `qldpc_code/base.py:22 [attribute/artifact] reads `.check_qubits``
    - `qldpc_code/base.py:22 [attribute/artifact] reads `.data_qubits``
    - `qldpc_code/base.py:22 [attribute/artifact] reads `.hx``
    - `qldpc_code/base.py:22 [attribute/artifact] reads `.hz``
    - `qldpc_code/base.py:22 [attribute/artifact] reads `.lx``
    - `qldpc_code/base.py:22 [attribute/artifact] reads `.lz``
    - `qldpc_code/base.py:22 [attribute/artifact] reads `.xcheck_qubits``
    - `qldpc_code/base.py:22 [attribute/artifact] reads `.zcheck_qubits``
    - `qldpc_code/base.py:22 [receiver/artifact] `self` is an instance of the enclosing class`
    - `qldpc_code/base.py:37 [argument/artifact] `hx` flows into `asarray(...)``
    - `qldpc_code/base.py:37 [argument/artifact] `hx` flows into `compute_lz_and_lx(...)``
    - `qldpc_code/base.py:37 [argument/artifact] `hz` flows into `asarray(...)``
    - `qldpc_code/base.py:37 [argument/artifact] `hz` flows into `compute_lz_and_lx(...)``
    - `qldpc_code/base.py:37 [attribute/artifact] reads `.hx``
    - `qldpc_code/base.py:37 [attribute/artifact] reads `.hz``
    - `qldpc_code/base.py:37 [attribute/artifact] reads `.lx``
    - `qldpc_code/base.py:37 [attribute/artifact] reads `.lz``
    - ... 80 more

</details>

Obligation clues (candidate `contract`s) at these anchors:

- `raise` `ValueError` - `qldpc_code/base.py:42`
- `raise` `ValueError` - `qldpc_code/base.py:44`
- `raise` `ValueError` - `qldpc_code/bb.py:34`
- `raise` `ValueError` - `qldpc_code/bpc.py:64`
- `raise` `ValueError` - `qldpc_code/lcs.py:33`
- `raise` `ValueError` - `qldpc_code/mitten.py:187`

**`extractor`** - anchors and what each one reads:

| anchor | R(c) here | artifact reads here |
|---|---|---|
| `qldpc_code/base.py:115` `QldpcCode.build_circuit` | `code, extractor, noise` | `code` |
| `qldpc_code/bb.py:66` `BbCode.build_circuit` | `extractor, noise` | `code` |
| `qldpc_code/bpc.py:134` `BpcCode.build_circuit` | `extractor, noise` | `code` |
| `qldpc_code/hgp.py:87` `HgpCode.build_circuit` | `extractor, noise` | `code` |
| `qldpc_code/lcs.py:48` `LcsCode.build_circuit` | `extractor, noise` | `code` |
| `qldpc_code/mitten.py:234` `MittenCode.build_circuit` | `extractor, noise` | `code` |
| `qldpc_code/qlp.py:50` `QlpCode.build_circuit` | `extractor, noise` | `code` |
| `qldpc_code/qlp.py:269` `QlpPolyCode.build_circuit` | `extractor, noise` | `code` |

<details><summary>evidence</summary>

- `code`:
    - `qldpc_code/base.py:115 [attribute/coordinate] reads `.supported_strategies``
    - `qldpc_code/base.py:115 [receiver/artifact] `self` is an instance of the enclosing class`
    - `qldpc_code/bb.py:66 [receiver/artifact] `self` is an instance of the enclosing class`
    - `qldpc_code/bpc.py:134 [receiver/artifact] `self` is an instance of the enclosing class`
    - `qldpc_code/hgp.py:87 [receiver/artifact] `self` is an instance of the enclosing class`
    - `qldpc_code/lcs.py:48 [receiver/artifact] `self` is an instance of the enclosing class`
    - `qldpc_code/mitten.py:234 [receiver/artifact] `self` is an instance of the enclosing class`
    - `qldpc_code/qlp.py:269 [receiver/artifact] `self` is an instance of the enclosing class`
    - `qldpc_code/qlp.py:50 [receiver/artifact] `self` is an instance of the enclosing class`
- `extractor`:
    - `qldpc_code/base.py:115 [argument/coordinate] `strategy` flows into `get_builder(...)``
    - `qldpc_code/base.py:115 [callee/sub_api] calls `get_builder(...)``
    - `qldpc_code/base.py:115 [declaration/coordinate] parameter `strategy``
    - `qldpc_code/base.py:115 [name/coordinate] reads `strategy``
    - `qldpc_code/base.py:115 [name/sub_api] reads `get_builder``
    - `qldpc_code/base.py:115 [string/coordinate] string literal `cardinalNSmerge``
    - `qldpc_code/base.py:115 [string/coordinate] string literal `cardinal``
    - `qldpc_code/base.py:115 [string/coordinate] string literal `custom``
    - `qldpc_code/base.py:115 [string/coordinate] string literal `zxcoloration``
    - `qldpc_code/base.py:115 [string/sub_api] keyword `circuit_build_options=``
    - `qldpc_code/base.py:115 [string/sub_api] string literal `circuit_build_options``
    - `qldpc_code/bb.py:66 [argument/coordinate] `strategy` flows into `build_circuit(...)``
    - `qldpc_code/bb.py:66 [argument/sub_api] `CircuitBuildOptions` flows into `isinstance(...)``
    - `qldpc_code/bb.py:66 [argument/sub_api] `circuit_build_options` flows into `get_coloration_circuit(...)``
    - `qldpc_code/bb.py:66 [argument/sub_api] `circuit_build_options` flows into `get_custom_circuit(...)``
    - `qldpc_code/bb.py:66 [argument/sub_api] `circuit_build_options` flows into `isinstance(...)``
    - `qldpc_code/bb.py:66 [callee/sub_api] calls `CircuitBuildOptions(...)``
    - `qldpc_code/bb.py:66 [callee/sub_api] calls `get_builder(...)``
    - ... 123 more
- `noise`:
    - `qldpc_code/base.py:115 [string/coordinate] keyword `error_model=``
    - `qldpc_code/base.py:115 [string/coordinate] string literal `error_model``
    - `qldpc_code/bb.py:66 [argument/coordinate] `error_model` flows into `get_coloration_circuit(...)``
    - `qldpc_code/bb.py:66 [argument/coordinate] `error_model` flows into `get_custom_circuit(...)``
    - `qldpc_code/bb.py:66 [callee/sub_api] calls `ErrorModel(...)``
    - `qldpc_code/bb.py:66 [declaration/coordinate] parameter `error_model``
    - `qldpc_code/bb.py:66 [name/coordinate] reads `error_model``
    - `qldpc_code/bb.py:66 [name/sub_api] reads `ErrorModel``
    - `qldpc_code/bb.py:66 [string/coordinate] keyword `error_model=``
    - `qldpc_code/bpc.py:134 [argument/coordinate] `error_model` flows into `_build_cardinal_circuit(...)``
    - `qldpc_code/bpc.py:134 [argument/coordinate] `error_model` flows into `get_coloration_circuit(...)``
    - `qldpc_code/bpc.py:134 [callee/sub_api] calls `ErrorModel(...)``
    - `qldpc_code/bpc.py:134 [declaration/coordinate] parameter `error_model``
    - `qldpc_code/bpc.py:134 [name/coordinate] reads `error_model``
    - `qldpc_code/bpc.py:134 [name/sub_api] reads `ErrorModel``
    - `qldpc_code/bpc.py:134 [string/coordinate] keyword `error_model=``
    - `qldpc_code/hgp.py:87 [argument/coordinate] `error_model` flows into `_build_cardinal_circuit(...)``
    - `qldpc_code/hgp.py:87 [argument/coordinate] `error_model` flows into `get_coloration_circuit(...)``
    - ... 34 more

</details>

Obligation clues (candidate `contract`s) at these anchors:

- `isinstance` `CircuitBuildOptions` - `qldpc_code/bb.py:90`
- `isinstance` `CircuitBuildOptions` - `qldpc_code/bpc.py:158`
- `isinstance` `CircuitBuildOptions` - `qldpc_code/hgp.py:111`
- `isinstance` `CircuitBuildOptions` - `qldpc_code/lcs.py:72`
- `isinstance` `CircuitBuildOptions` - `qldpc_code/mitten.py:260`
- `isinstance` `CircuitBuildOptions` - `qldpc_code/qlp.py:293`
- `isinstance` `CircuitBuildOptions` - `qldpc_code/qlp.py:74`
- `raise` `NotImplementedError` - `qldpc_code/base.py:131`
- `raise` `TypeError` - `qldpc_code/bb.py:91`
- `raise` `TypeError` - `qldpc_code/bpc.py:159`
- `raise` `TypeError` - `qldpc_code/hgp.py:112`
- `raise` `TypeError` - `qldpc_code/lcs.py:73`
- `raise` `TypeError` - `qldpc_code/mitten.py:261`
- `raise` `TypeError` - `qldpc_code/qlp.py:294`
- `raise` `TypeError` - `qldpc_code/qlp.py:75`

**`arch`** - anchors and what each one reads:

| anchor | R(c) here | artifact reads here |
|---|---|---|
| `layout/base.py:23` `Layout.__init__` | `-` | `arch, code` |
| `layout/base.py:39` `Layout.node_positions` | `arch` | `arch, code` |
| `layout/toric.py:13` `ToricLayout.__new__` | `-` | `code` |
| `layout/toric_bb.py:14` `BbToricLayout.__init__` | `-` | `arch, code` |
| `layout/toric_common.py:14` `AbstractToricLayout.__init__` | `arch` | `arch, code` |
| `layout/transversal.py:11` `TransversalLayout.__init__` | `arch` | `arch, code` |
| `layout/transversal.py:34` `TransversalLayout._build_mapping` | `arch` | `arch, code` |

<details><summary>evidence</summary>

- `arch`:
    - `layout/base.py:23 [receiver/artifact] `self` is an instance of the enclosing class`
    - `layout/base.py:39 [attribute/coordinate] reads `.data``
    - `layout/base.py:39 [attribute/coordinate] reads `.xcheck``
    - `layout/base.py:39 [attribute/coordinate] reads `.zcheck``
    - `layout/base.py:39 [name/sub_api] reads `Coordinate``
    - `layout/base.py:39 [receiver/artifact] `self` is an instance of the enclosing class`
    - `layout/base.py:39 [string/coordinate] string literal `data``
    - `layout/toric.py:13 [argument/sub_api] `_TORIC_LAYOUT_ERROR` flows into `ValueError(...)``
    - `layout/toric.py:13 [callee/sub_api] calls `BbToricLayout(...)``
    - `layout/toric.py:13 [name/sub_api] reads `BbToricLayout``
    - `layout/toric.py:13 [name/sub_api] reads `Layout``
    - `layout/toric.py:13 [name/sub_api] reads `_TORIC_LAYOUT_ERROR``
    - `layout/toric_bb.py:14 [argument/sub_api] `_BB_TORIC_LAYOUT_ERROR` flows into `ValueError(...)``
    - `layout/toric_bb.py:14 [name/sub_api] reads `_BB_TORIC_LAYOUT_ERROR``
    - `layout/toric_bb.py:14 [receiver/artifact] `self` is an instance of the enclosing class`
    - `layout/toric_common.py:14 [attribute/coordinate] reads `._a_terms``
    - `layout/toric_common.py:14 [attribute/coordinate] reads `._b_terms``
    - `layout/toric_common.py:14 [attribute/coordinate] reads `._left_size``
    - ... 39 more
- `code`:
    - `layout/base.py:23 [attribute/artifact] reads `.code``
    - `layout/base.py:23 [declaration/artifact] parameter `code``
    - `layout/base.py:23 [name/artifact] reads `code``
    - `layout/base.py:23 [string/sub_api] string literal `QldpcCode``
    - `layout/base.py:39 [argument/artifact] `data_qubits` flows into `_node_positions_for_role(...)``
    - `layout/base.py:39 [argument/artifact] `data_qubits` flows into `update(...)``
    - `layout/base.py:39 [argument/artifact] `xcheck_qubits` flows into `_node_positions_for_role(...)``
    - `layout/base.py:39 [argument/artifact] `xcheck_qubits` flows into `update(...)``
    - `layout/base.py:39 [argument/artifact] `zcheck_qubits` flows into `_node_positions_for_role(...)``
    - `layout/base.py:39 [argument/artifact] `zcheck_qubits` flows into `update(...)``
    - `layout/base.py:39 [declaration/artifact] parameter `data_qubits``
    - `layout/base.py:39 [declaration/artifact] parameter `xcheck_qubits``
    - `layout/base.py:39 [declaration/artifact] parameter `zcheck_qubits``
    - `layout/base.py:39 [name/artifact] reads `data_qubits``
    - `layout/base.py:39 [name/artifact] reads `xcheck_qubits``
    - `layout/base.py:39 [name/artifact] reads `zcheck_qubits``
    - `layout/toric.py:13 [argument/artifact] `code` flows into `BbToricLayout(...)``
    - `layout/toric.py:13 [argument/artifact] `code` flows into `isinstance(...)``
    - ... 24 more

</details>

Obligation clues (candidate `contract`s) at these anchors:

- `isinstance` `BbCode` - `layout/toric.py:17`
- `isinstance` `BbCode` - `layout/toric_bb.py:15`
- `raise` `ValueError` - `layout/toric.py:19`
- `raise` `ValueError` - `layout/toric_bb.py:16`
- `raise` `ValueError` - `layout/toric_bb.py:23`
- `raise` `ValueError` - `layout/toric_common.py:20`
- `raise` `ValueError` - `layout/transversal.py:22`
- `raise` `ValueError` - `layout/transversal.py:24`

**`noise`** - anchors and what each one reads:

| anchor | R(c) here | artifact reads here |
|---|---|---|
| `noise/error_model.py:37` `ErrorModel.__post_init__` | `noise` | `noise` |
| `noise/error_model.py:45` `ErrorModel._validate_single_or_pauli1` | `-` | `-` |
| `noise/error_model.py:60` `ErrorModel._validate_single_or_pauli2` | `-` | `-` |

<details><summary>evidence</summary>

- `noise`:
    - `noise/error_model.py:37 [attribute/coordinate] reads `.idle_error``
    - `noise/error_model.py:37 [attribute/coordinate] reads `.spam_error``
    - `noise/error_model.py:37 [attribute/coordinate] reads `.sqgate_error``
    - `noise/error_model.py:37 [attribute/coordinate] reads `.tqgate_error``
    - `noise/error_model.py:37 [receiver/artifact] `self` is an instance of the enclosing class`
    - `noise/error_model.py:37 [string/coordinate] string literal `idle_error``
    - `noise/error_model.py:37 [string/coordinate] string literal `sqgate_error``
    - `noise/error_model.py:37 [string/coordinate] string literal `tqgate_error``
    - `noise/error_model.py:45 [callee/sub_api] calls `_is_real_sequence(...)``
    - `noise/error_model.py:45 [name/sub_api] reads `_is_real_sequence``
    - `noise/error_model.py:60 [callee/sub_api] calls `_is_real_sequence(...)``
    - `noise/error_model.py:60 [name/sub_api] reads `_is_real_sequence``

</details>

Obligation clues (candidate `contract`s) at these anchors:

- `isinstance` `Real` - `noise/error_model.py:41`
- `isinstance` `Real` - `noise/error_model.py:53`
- `isinstance` `Real` - `noise/error_model.py:68`
- `raise` `TypeError` - `noise/error_model.py:42`
- `raise` `TypeError` - `noise/error_model.py:57`
- `raise` `TypeError` - `noise/error_model.py:72`

**`decoder`** - anchors and what each one reads:

| anchor | R(c) here | artifact reads here |
|---|---|---|
| `decoder/base.py:134` `spacetime` | `-` | `code, extractor` |
| `decoder/bplsd.py:54` `sliding_window_bplsd_circuit_mem` | `-` | `code, extractor` |
| `decoder/bposd.py:54` `sliding_window_bposd_circuit_mem` | `-` | `code, extractor` |
| `simulation.py:31` `get_codecap_pL` | `decoder` | `code` |

<details><summary>evidence</summary>

- `code`:
    - `decoder/base.py:134 [declaration/artifact] parameter `hz``
    - `decoder/base.py:134 [name/artifact] reads `hz``
    - `decoder/bplsd.py:54 [argument/artifact] `hz` flows into `sliding_window_circuit_mem(...)``
    - `decoder/bplsd.py:54 [argument/artifact] `lz` flows into `sliding_window_circuit_mem(...)``
    - `decoder/bplsd.py:54 [declaration/artifact] parameter `hz``
    - `decoder/bplsd.py:54 [declaration/artifact] parameter `lz``
    - `decoder/bplsd.py:54 [name/artifact] reads `hz``
    - `decoder/bplsd.py:54 [name/artifact] reads `lz``
    - `decoder/bposd.py:54 [argument/artifact] `hz` flows into `sliding_window_circuit_mem(...)``
    - `decoder/bposd.py:54 [argument/artifact] `lz` flows into `sliding_window_circuit_mem(...)``
    - `decoder/bposd.py:54 [declaration/artifact] parameter `hz``
    - `decoder/bposd.py:54 [declaration/artifact] parameter `lz``
    - `decoder/bposd.py:54 [name/artifact] reads `hz``
    - `decoder/bposd.py:54 [name/artifact] reads `lz``
    - `simulation.py:31 [attribute/artifact] reads `.hx``
    - `simulation.py:31 [attribute/artifact] reads `.hz``
    - `simulation.py:31 [attribute/artifact] reads `.lx``
    - `simulation.py:31 [attribute/artifact] reads `.lz``
    - ... 2 more
- `decoder`:
    - `decoder/base.py:134 [callee/sub_api] calls `detector_error_model_to_matrix(...)``
    - `decoder/base.py:134 [name/sub_api] reads `detector_error_model_to_matrix``
    - `decoder/bplsd.py:54 [callee/sub_api] calls `sliding_window_circuit_mem(...)``
    - `decoder/bplsd.py:54 [name/sub_api] reads `sliding_window_circuit_mem``
    - `decoder/bposd.py:54 [callee/sub_api] calls `sliding_window_circuit_mem(...)``
    - `decoder/bposd.py:54 [name/sub_api] reads `sliding_window_circuit_mem``
    - `simulation.py:31 [callee/coordinate] calls `decoder(...)``
    - `simulation.py:31 [declaration/coordinate] parameter `decoder``
    - `simulation.py:31 [name/coordinate] reads `decoder``
- `extractor`:
    - `decoder/base.py:134 [argument/artifact] `model` flows into `detector_error_model_to_matrix(...)``
    - `decoder/base.py:134 [declaration/artifact] parameter `circuit``
    - `decoder/base.py:134 [name/artifact] reads `circuit``
    - `decoder/base.py:134 [name/artifact] reads `model``
    - `decoder/bplsd.py:54 [argument/artifact] `circuit` flows into `sliding_window_circuit_mem(...)``
    - `decoder/bplsd.py:54 [declaration/artifact] parameter `circuit``
    - `decoder/bplsd.py:54 [name/artifact] reads `circuit``
    - `decoder/bposd.py:54 [argument/artifact] `circuit` flows into `sliding_window_circuit_mem(...)``
    - `decoder/bposd.py:54 [declaration/artifact] parameter `circuit``
    - `decoder/bposd.py:54 [name/artifact] reads `circuit``

</details>

Obligation clues (candidate `contract`s) at these anchors:

- `raise` `ValueError` - `decoder/base.py:150`
- `raise` `ValueError` - `decoder/base.py:162`
- `raise` `ValueError` - `simulation.py:48`

## 2. Diff against the hand-declared model

`hand` = `semantics._mk_components()`; `dataflow` = `cone_table.make_quits_dataflow_assembly()` (the assembly used for the H3 dataflow experiment).

### 2a. R(c) proper (spec coordinates only)

| dimension | auto | hand | verdict | in auto not in hand |
|---|---|---|---|---|
| `code` | `code` | `code` | **agreement** | `-` |
| `extractor` | `code, extractor, noise` | `code, extractor` | **manual_under_approximates** | `noise` |
| `arch` | `arch` | `arch` | **agreement** | `-` |
| `noise` | `noise` | `noise` | **agreement** | `-` |
| `decoder` | `decoder` | `decoder` | **agreement** | `-` |

### 2b. Flattened (coordinates + artifact objects)

| dimension | auto | hand | verdict | in auto not in hand |
|---|---|---|---|---|
| `code` | `code` | `code` | **agreement** | `-` |
| `extractor` | `code, extractor, noise` | `code, extractor` | **manual_under_approximates** | `noise` |
| `arch` | `arch, code` | `arch` | **manual_under_approximates** | `code` |
| `noise` | `noise` | `noise` | **agreement** | `-` |
| `decoder` | `code, decoder, extractor` | `decoder` | **manual_under_approximates** | `code, extractor` |

### 2c. vs the dataflow assembly (R(c) proper)

| dimension | auto | dataflow | verdict | in auto not in dataflow |
|---|---|---|---|---|
| `code` | `code` | `code` | **agreement** | `-` |
| `extractor` | `code, extractor, noise` | `code, extractor, noise` | **agreement** | `-` |
| `arch` | `arch` | `arch` | **agreement** | `-` |
| `noise` | `noise` | `noise` | **agreement** | `-` |
| `decoder` | `decoder` | `arch, code, decoder, extractor, noise` | **manual_over_approximates** | `-` |

## 3. Vocabulary sanity check

A name published by 2 or more dimensions is ambiguous and is dropped from every vocabulary (2 names):

`__all__`, `code`

Identifiers shorter than 3 characters are treated as non-API (loop counters / shift exponents).

Generic identifiers excluded from attribution: `name`.

| dimension | package entries | files | published names | api | state |
|---|---:|---:|---:|---:|---:|
| `code` | 7 | 7 | 29 | 13 | 16 |
| `extractor` | 1 | 9 | 23 | 16 | 7 |
| `arch` | 1 | 6 | 22 | 10 | 12 |
| `noise` | 1 | 2 | 6 | 2 | 4 |
| `decoder` | 1 | 5 | 10 | 10 | 0 |
| `assembly` | 4 | 4 | 16 | 8 | 8 |
