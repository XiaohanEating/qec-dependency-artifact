# Quantitative Evidence for H1-H3 (pinned QUITS tree)

Generated: 2026-10-09  
QUITS commit: `0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452`  
Source: `third_party/quits-0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452/src/quits`  
Method: ast-based static extraction + execution of the pinned tree

## 0. What these numbers are, and what they feed

These counts are statements about **the pinned QUITS source itself (not about any semantic-layer assembly)** — they do not depend on any semantic-layer assembly. What the tables *feed* does, and which modelling is the published baseline does too, so the provenance is recorded here.

- published baseline assembly: **`source_faithful`**
- baseline read sets: auto-extracted from the pinned QUITS tree by experiments/extract_read_sets.py (READ_SETS_FROM_SOURCE)
- baseline DAG edges: auto-derived: ARTIFACT_READS_FROM_SOURCE minus self-loops (ASSEMBLY_EDGES_FROM_SOURCE): extractor <- code, arch <- code, decoder <- (code, extractor)

| hypothesis | what it feeds |
|---|---|
| **H1** | the family whitelists become `semantics.FAMILY_STRATEGIES`, which is the faithful extractor's `contract`: an inadmissible (code, extractor) pair is refused as a *stated obligation* by `semantics.inadmissible_pairs()` instead of a runtime raise.  It is also the `quits_faithful` counterexample's mechanism. |
| **H2** | the absence of any abstract interface in decoder/ is why the semantic layer must *check* R(c) rather than infer it like an effect system (PIVOT_NOTE section 8.5). |
| **H3** | noise being baked into the circuit is the `noise` coordinate in R(extractor) of every faithful assembly; its coordinate impact is {noise, extractor, decoder, experiment}. |

Hand-modelled counterpart (`quits_dataflow`): read sets = hand-declared conservative H3 model: R(extractor) contains `noise` (build_circuit bakes the error model into the circuit) and R(decoder) is everything embedded in the circuit plus its own coordinate; edges = hand-set, deliberately over-approximating: extractor <- (code, noise); decoder <- (code, extractor, arch, noise); arch <- code (added 2026-10-09 -- the dynamic measurement shows a code substitution changes `layout_positions`, so this edge is real)

Dynamic cross-check: experiments/dynamic_impact.json measures H1 and H3 by executing QUITS; that measurement is the ground truth, this file and extract_read_sets.py are the static cross-validation of it.

## H1 — admissibility is a hidden cross-component relation

- files declaring a `supported_strategies` whitelist: **8**
- concrete code families: **7**
- `QldpcCode` default whitelist: `['zxcoloration']`
- families whose whitelist differs from the base default: **7** (BbCode, BpcCode, HgpCode, LcsCode, MittenCode, QlpCode, QlpPolyCode)
- **distinct whitelists: 3**
- **inconsistent family pairs: 11/21** (52%)
- global registry keys (`_BUILDERS`, resolved through `BuilderClass.name`): `cardinal, cardinalNSmerge, custom, zxcoloration`
- enforcement: `NotImplementedError` raised at `qldpc_code/base.py:[131]` — a *runtime* raise, not a type
- strategies whitelisted by some family but **absent from the global builder registry**: `hook_error_free` (1) — handled ad hoc inside that family's own `build_circuit`

Per-class whitelists:

| file:line | class | supported_strategies |
|---|---|---|
| `qldpc_code/base.py:20` | `QldpcCode` | `{zxcoloration}` |
| `qldpc_code/bb.py:19` | `BbCode` | `{custom, zxcoloration}` |
| `qldpc_code/bpc.py:15` | `BpcCode` | `{cardinal, cardinalNSmerge, zxcoloration}` |
| `qldpc_code/hgp.py:15` | `HgpCode` | `{cardinal, cardinalNSmerge, zxcoloration}` |
| `qldpc_code/lcs.py:24` | `LcsCode` | `{cardinal, cardinalNSmerge, zxcoloration}` |
| `qldpc_code/mitten.py:181` | `MittenCode` | `{custom, hook_error_free, zxcoloration}` |
| `qldpc_code/qlp.py:15` | `QlpCode` | `{cardinal, cardinalNSmerge, zxcoloration}` |
| `qldpc_code/qlp.py:204` | `QlpPolyCode` | `{cardinal, cardinalNSmerge, zxcoloration}` |

Strategy acceptance matrix (H1 in one table):

| strategy | families accepting | n |
|---|---|---:|
| `cardinal` | BpcCode, HgpCode, LcsCode, QlpCode, QlpPolyCode | 5/7 |
| `cardinalNSmerge` | BpcCode, HgpCode, LcsCode, QlpCode, QlpPolyCode | 5/7 |
| `custom` | BbCode, MittenCode | 2/7 |
| `hook_error_free` | MittenCode | 1/7 |
| `zxcoloration` | BbCode, BpcCode, HgpCode, LcsCode, MittenCode, QlpCode, QlpPolyCode | 7/7 |

**H1 verdict: True**

## H2 — a substituter has no obligation it can state

| package | files | LOC | classes | ABC | Protocol | @abstractmethod |
|---|---:|---:|---:|---:|---:|---:|
| `decoder/` | 5 | 591 | 0 | 0 | 0 | 0 |
| `layout/` | 6 | 444 | 6 | 2 | 0 | 5 |
| `noise/` | 2 | 85 | 1 | 0 | 0 | 0 |

- **`decoder/` declares 0 abstract interfaces across 5 files / 591 LOC**; `layout/` declares 2 (Layout, AbstractToricLayout).
- implicit interface actually used at `simulation.py:31-61`: **1 attribute(s)** ['decode'], plus a constructor call [{'callee': 'decoder', 'positional': ['parity_check_matrix'], 'star_kwargs': True, 'explicit_kwargs': []}]
- `decoder/` public API is entirely free functions (no class to inherit from)

**H2 verdict: True**

## H3 — 'reuse the rest unchanged' has no a-priori statement

- `build_circuit` definitions found: **8** in **7** files
- files whose `build_circuit` **signature** names an error/noise parameter: **6/7**
- files that depend on noise **by any channel** (explicit parameter or `**opts` lookup): **7/7** (100%)
- files forwarding noise into the builder call: **7**
- files using opaque `**opts` (untyped parameter contract): `qldpc_code/base.py`, `qldpc_code/bb.py`, `qldpc_code/bpc.py`, `qldpc_code/hgp.py`, `qldpc_code/lcs.py`, `qldpc_code/mitten.py`, `qldpc_code/qlp.py`

| file:line | noise params | opaque **opts | noise via **opts | forwards noise |
|---|---|:--:|:--:|:--:|
| `qldpc_code/base.py:115` | - | yes | yes | yes |
| `qldpc_code/bb.py:66` | `error_model` | yes | no | yes |
| `qldpc_code/bpc.py:134` | `error_model` | yes | no | yes |
| `qldpc_code/hgp.py:87` | `error_model` | yes | no | yes |
| `qldpc_code/lcs.py:48` | `error_model` | yes | no | yes |
| `qldpc_code/mitten.py:234` | `error_model` | yes | no | yes |
| `qldpc_code/qlp.py:50` | `error_model` | yes | no | yes |
| `qldpc_code/qlp.py:269` | `error_model` | yes | no | yes |

**H3 verdict: True**

> Reading: the noise coordinate is a parameter of *every* `build_circuit` signature, so the noise model is an input to the circuit artifact. Replacing noise therefore changes the circuit artifact — i.e. it is not circuit-preserving — and nothing in the source says so in advance.

## P2-3 — extractor domain coverage

- semantics `DOMAIN['extractor']`: `['cardinal', 'cardinalNSmerge', 'custom', 'hook_error_free', 'zxcoloration']`
- union of per-family whitelists in the source tree: `['cardinal', 'cardinalNSmerge', 'custom', 'hook_error_free', 'zxcoloration']`
- missing from domain: `none`
- covers source union: **True**
- per-dimension exhaustiveness flag (`DOMAIN_EXHAUSTIVE`): `code`=EXHAUSTIVE, `extractor`=EXHAUSTIVE, `arch`=PARTIAL, `noise`=PARTIAL, `decoder`=PARTIAL

## P2-2 — automatic verification of QUITS_CALL_SITES

| dimension | verified | static | runtime |
|---|:--:|---|---|
| extraction | yes | 3 distinct whitelists over 7 families; 11/21 pairs inconsistent | BbCode(3,3).supported_strategies=['custom', 'zxcoloration']; build_circuit -> {'cardinal': 'NotImplementedErro |
| decoder | yes | decoder/: 0 classes, 0 ABC, 0 Protocol (layout/: 2 ABC); implicit interface = ['decode'] | quits.decoder.__all__ exposes 10 names, 0 classes; a duck-typed decoder (no ABC/Protocol) ran through get_code |
| noise | yes | ErrorModel.__post_init__ body =     self._validate_single_or_pauli1('idle_error', self.idl | structurally-valid but semantically-bogus ErrorModel values are accepted (no property obligation): {'prob_gt_1 |
| code | yes | 8 class-level supported_strategies declarations, all subclasses of QldpcCode | BbCode(3,3): CSS commutation hz.hx^T == hx.hz^T mod 2 holds=True; verify_css_logicals=True |
| architecture | yes | layout/: ['layout/base.py:22:Layout', 'layout/toric_common.py:11:AbstractToricLayout']; de | issubclass(Layout, abc.ABC)=True; Layout.__abstractmethods__=['mapping']; QldpcCode().get_layout() is None=Tru |

runtime-verified: **5/5**; verified (static or runtime): **5/5**
