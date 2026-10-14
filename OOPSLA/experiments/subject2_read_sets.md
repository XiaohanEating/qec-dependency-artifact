# Subject 2 read sets — AST extraction vs the hand model

Generated: 2026-10-12  
commit: `4ef18121c39492414b85ff36b3a61c83f9ebf95f`  
source: `src_py/bivariate-bicycle/general.py`  
Method: AST static analysis of the pinned tree; component granularity = the 11 nodes of subject2_qecc; coordinate-carrier / artifact / sub_api attribution (same channels as experiments/extract_read_sets.py)

> Components are **line ranges of one module** (qecc_routing has no packages); every range is sentinel-verified against the pinned file.  `artifact_reads` are references to another component's module-level product (a DAG edge, the `reads_flat` channel of `extract_read_sets.py`), not coordinate reads.

## 1. Component × read-set comparison

| component | regions | hand R(c) | AST coordinates | AST artifacts | verdict |
|---|---|---|---|---|---|
| `circuit` | 270-306, 325-334, 348-352 | `code, embedding` | `noise` | `code, embedding, sr_lr_split` | **hidden_read_hand_missed** |
| `code` | 43-68 | `code` | `code` | `code` | **agreement** |
| `decoder` | 473-486 | `decoder` | `decoder` | `-` | **agreement** |
| `embedding` | 156-224 | `code, embedding` | `code` | `code, embedding` | **carrier_sharing** |
| `geometry` | 226-233 | `embedding` | `-` | `code, embedding, geometry` | **artifact_only** |
| `idle` | 414-414, 422-422 | `code` | `code, noise` | `embedding` | **hidden_read_detected** |
| `logicals` | 73-149 | `code` | `-` | `code` | **artifact_only** |
| `schedule` | 309-323, 336-346, 354-375, 378-407, 410-413, 415-421, 423-438 | `code, routing` | `routing` | `code, embedding, sr_lr_split, succ_probs` | **artifact_only** |
| `sink` | 448-496 | `code, decoder, embedding, noise, routing` | `code, decoder, noise, routing` | `code, sr_lr_split` | **carrier_sharing** |
| `sr_lr_split` | 235-238, 243-250, 255-262, 267-267 | `code, embedding` | `-` | `code, embedding, geometry, sr_lr_split` | **aggregate_visible_at_file_level** |
| `succ_probs` | 240-241, 252-253, 264-265 | `code` | `noise` | `code, succ_probs` | **hidden_read_detected** |

### Disagreements, one by one

- **`circuit`** — hidden_read_hand_missed
  - AST-only coordinates: `['noise']`; hand-only: `['code', 'embedding']`
  - the measure_* builders read the global `muls001` noise table when scale=True (general.py:280,295) -- a hidden noise read the hand model did NOT declare: hand R(circuit) omitted it
- **`embedding`** — carrier_sharing
  - AST-only coordinates: `none`; hand-only: `['embedding']`
  - the embedding coordinate has no global of its own: its values are code[8:12], carried by the `code` list (general.py:204). AST sees one carrier; the hand model names the semantic view
- **`geometry`** — artifact_only
  - AST-only coordinates: `none`; hand-only: `['embedding']`
  - the real source reads only predecessor *artifacts* (embedding never appears as a coordinate carrier here); the hand toy produce used the coordinate directly
- **`idle`** — hidden_read_detected
  - AST-only coordinates: `['noise']`; hand-only: `none`
  - AST finds the hidden `['noise']` read the hand model declares as faithful-but-wrong (g / e / n / e / r / a / l / . / p / y / : / 4 / 1 / 4 / , / 4 / 2 / 2 /   / ` / 0 / . / 0 / 0 / 1 / + / 2 / * / c / o / d / e / [ / 1 / 2 / ] / * / i / d / l / e / _ / e / r / r / o / r / ` /   / - / - /   / n / o / i / s / e /   / m / u / l / t / i / p / l / i / e / d /   / b / y /   / a /   / c / o / d / e /   / p / o / l / y / n / o / m / i / a / l)
- **`logicals`** — artifact_only
  - AST-only coordinates: `none`; hand-only: `['code']`
  - the real source reads only predecessor *artifacts* (code never appears as a coordinate carrier here); the hand toy produce used the coordinate directly
- **`schedule`** — artifact_only
  - AST-only coordinates: `none`; hand-only: `['code']`
  - simulate's code contact is via module state (m, ell, the split and succ-prob arrays) and the two idle sites, which this extractor attributes to the `idle` component; no direct `code` coordinate read remains in the schedule body
- **`sink`** — carrier_sharing
  - AST-only coordinates: `none`; hand-only: `['embedding']`
  - the sink consumes every artifact; the embedding coordinate reaches it only through the shared `code` carrier (general.py:489-490), there is no separate embedding global
- **`sr_lr_split`** — aggregate_visible_at_file_level
  - AST-only coordinates: `none`; hand-only: `['code', 'embedding']`
  - the split decision is `min(x_rs)+np.std(x_rs)` over the WHOLE radius vector (general.py:247,259): AST sees the aggregate read of the geometry artifact, the hand model names the coordinates behind it.  File-level visible; the coordinate-keyed probe stays blind because aggregate and coordinate move together (subject_system2.md §2.3)
- **`succ_probs`** — hidden_read_detected
  - AST-only coordinates: `['noise']`; hand-only: `['code']`
  - AST finds the hidden `['noise']` read the hand model declares as faithful-but-wrong (g / e / n / e / r / a / l / . / p / y / : / 2 / 5 / 3 / , / 2 / 6 / 5 /   / ` / p / r / o / b / s / [ / m / a / n / h / a / t / t / a / n / ( / . / . / . / ) / + / 1 / ] / ` /   / - / - /   / r / e / a / d / s /   / t / h / e /   / g / l / o / b / a / l /   / ` / p / r / o / b / s / ` /   / t / a / b / l / e / , /   / i / . / e / . /   / t / h / e /   / n / o / i / s / e /   / c / o / o / r / d / i / n / a / t / e)

## 2. The two expected hidden reads — did AST find them?

- **`idle`** (hidden_read_detected): `general.py:414 reads `code``; `general.py:414 reads `idle_error``; `general.py:422 reads `code``; `general.py:422 reads `idle_error``
- **`succ_probs`** (hidden_read_detected): `general.py:253 reads `probs``; `general.py:265 reads `probs``

- all hand-labelled faithful-but-wrong components detected: **True** (`('succ_probs', 'idle')`)
- hidden reads the hand model **missed**: `['circuit']` — the AST found a third hidden noise read (`circuit` ← `muls001`)

## 3. The sr_lr_split aggregate: a layer difference, not a miss

file-level AST sees min/std over the whole radius vector; the coordinate-keyed probe is blind to it (aggregate moves with the coordinate)

The hand model's coordinate probe stays blind to the aggregate because the aggregate and the coordinate move together; the AST, working at file level, sees `min(x_rs)+np.std(x_rs)` directly.  Both statements are true at their own layer.

## 4. Dependency availability (this machine)

| module | available | version | needed by |
|---|---|---|---|
| `numpy` | True | 2.2.6 | general.py, mec.py |
| `scipy` | True | 1.15.3 | general.py (sparse) |
| `matplotlib` | True | 3.9.2 | general.py (pyplot) |
| `stim` | True | 1.14.0 | general.py |
| `galois` | True | 0.4.2 | general.py (GF(2) rank) |
| `ldpc` | True | 2.1.2 | general.py (bposd) |
| `tqdm` | True | 4.67.1 | general.py (experiment loop) |
| `pandas` | False | — | code_exploration.py only -- NOT needed by the gate |
| `networkx` | True | 3.4.2 | requirements.txt only -- not imported by src_py |
| `sinter` | True | 1.14.0 | requirements.txt only -- not imported by src_py |

galois 0.4.2 required upgrading numba (numpy 2.2 compat) and coverage (numba 0.61 compat) on this machine; the general.py pipeline imports are otherwise all satisfied

