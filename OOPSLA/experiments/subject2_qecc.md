# Second subject system — qecc_routing (Berthusen et al., arXiv:2404.17676)

Generated: 2026-10-10  
commit: `4ef18121c39492414b85ff36b3a61c83f9ebf95f`  
formal core: `OOPSLA/src/semantics.py`  

Reuse of the formal core: unchanged except three additive default-valued parameters (Component.coordinates, _cartesian(spec_cls=), detect_hidden_dependency(coordinates=) + spec_cls threading)

> toy (same sense as QUITS's toy layer); the real artifact is a stim.Circuit built by the pinned module, never executed on this platform

Modelling provenance (pinned file:line):

- `code` — src_py/bivariate-bicycle/general.py:18 (`code` global) :53-64 (Hx, Hz from A/B polynomials)
- `embedding` — general.py:156-202 `embed_code(code, init)`, driven by code[8:12] (emb_m, emb_l, A_ind, B_ind)
- `geometry` — general.py:226-233 x_rs/z_rs = minimal enclosing circle radius of every check's qubits
- `sr_lr_split` — general.py:247,259 `if x_rs[i] > min(x_rs)+np.std(x_rs)` -- an aggregate over the WHOLE radius vector
- `succ_probs` — general.py:253,265 `probs[manhattan(...)+1]` -- reads the global `probs` table, i.e. the noise coordinate
- `idle` — general.py:414,422 `0.001+2*code[12]*idle_error` -- noise multiplied by a code polynomial
- `logicals` — general.py:139-149 `get_logicals` -> SGSOP on Hx/Hz
- `schedule` — general.py:309-438 `Simulation(num_rounds, lr_time)`, `lr_time` = the routing depth
- `circuit` — general.py:332-334,354-407,410-438 -> stim.Circuit
- `decoder` — general.py:473-486 `bposd_decoder(pcm, channel_probs=...)`

## 0. domain (5 coordinates, 11 nodes)

| coordinate | exhaustive? | values | declared readers |
|---|---|---|---|
| `code` | True | 2 | ['circuit', 'code', 'embedding', 'idle', 'logicals', 'schedule', 'sink', 'sr_lr_split', 'succ_probs'] |
| `decoder` | False | 1 | ['decoder', 'sink'] |
| `embedding` | True | 2 | ['circuit', 'embedding', 'geometry', 'sink', 'sr_lr_split'] |
| `noise` | False | 2 | ['sink'] |
| `routing` | False | 2 | ['schedule', 'sink'] |

### structure: coordinates vs. component nodes

- coordinates: 5, nodes: 11
- bijective (QUITS's shape): **False**
- coordinates with **no** node of the same name: `['noise', 'routing']`
- nodes with **no** coordinate of the same name: `['circuit', 'geometry', 'idle', 'logicals', 'schedule', 'sink', 'sr_lr_split', 'succ_probs']`
- coordinates read by more than one node: `{'code': ['circuit', 'code', 'embedding', 'idle', 'logicals', 'schedule', 'sink', 'sr_lr_split', 'succ_probs'], 'decoder': ['decoder', 'sink'], 'embedding': ['circuit', 'embedding', 'geometry', 'sink', 'sr_lr_split'], 'routing': ['schedule', 'sink']}`

## 1. Theorem 3 — hidden reads on a system with no registry

| component | declared R(c) | observed ⊄ declared | extensions | class |
|---|---|---|---|---|
| `circuit` | ['code', 'embedding'] | False | — | faithful |
| `code` | ['code'] | False | — | faithful |
| `decoder` | ['decoder'] | False | — | faithful |
| `embedding` | ['code', 'embedding'] | False | — | faithful |
| `geometry` | ['embedding'] | False | — | faithful |
| `idle` | ['code'] | True | ['noise'] | **faithful-but-wrong** |
| `logicals` | ['code'] | False | — | faithful |
| `schedule` | ['code', 'routing'] | False | — | faithful |
| `sink` | ['code', 'decoder', 'embedding', 'noise', 'routing'] | False | — | faithful |
| `sr_lr_split` | ['code', 'embedding'] | False | — | aggregate-only (probe-blind) |
| `succ_probs` | ['code'] | True | ['noise'] | **faithful-but-wrong** |

- **detected**: `['idle', 'succ_probs']`
- **declared faithful-but-wrong**: `['idle', 'succ_probs']`
- **all of them detected**: True
- **false positives**: none
- **declared correctly but probe-blind (aggregate dependence)**: `['sr_lr_split']`

## 2. Theorem 1 — side conditions and cone

| component | cone | \|cone\|/\|N\| | applicable |
|---|---|---|---|
| `circuit` | ['decoder', 'sink'] | 0.182 | True |
| `code` | ['circuit', 'decoder', 'embedding', 'geometry', 'idle', 'logicals', 'schedule', 'sink', 'sr_lr_split', 'succ_probs'] | 0.909 | True |
| `decoder` | ['sink'] | 0.091 | True |
| `embedding` | ['circuit', 'decoder', 'geometry', 'schedule', 'sink', 'sr_lr_split'] | 0.545 | True |
| `geometry` | ['circuit', 'decoder', 'schedule', 'sink', 'sr_lr_split'] | 0.455 | True |
| `idle` | ['circuit', 'decoder', 'schedule', 'sink'] | 0.364 | False |
| `logicals` | ['circuit', 'decoder', 'sink'] | 0.273 | True |
| `schedule` | ['circuit', 'decoder', 'sink'] | 0.273 | True |
| `sink` | [] | 0.000 | True |
| `sr_lr_split` | ['circuit', 'decoder', 'schedule', 'sink'] | 0.364 | True |
| `succ_probs` | ['circuit', 'decoder', 'schedule', 'sink'] | 0.364 | False |

applicable on 9/11 nodes

## 3. cone vs. coordinate impact (Def. 3.12 vs. 3.13)

| coordinate | readers | cone | impact | agree |
|---|---|---|---|---|
| `code` | ['circuit', 'code', 'embedding', 'idle', 'logicals', 'schedule', 'sink', 'sr_lr_split', 'succ_probs'] | 10 | 11 | False |
| `decoder` | ['decoder', 'sink'] | 1 | 2 | False |
| `embedding` | ['circuit', 'embedding', 'geometry', 'sink', 'sr_lr_split'] | 6 | 7 | False |
| `noise` | ['sink'] | 0 | 2 | False |
| `routing` | ['schedule', 'sink'] | 3 | 5 | False |

agree on 0/5; disagree on ['code', 'decoder', 'embedding', 'noise', 'routing']

The two notions differ by construction whenever a coordinate is read by a node other than one of the same name (that is the case for every coordinate here).  The actionable number is the third column: **how many nodes a cone-only report would have missed**.

| coordinate | readers | cone | impact | missed by a cone report |
|---|---|---|---|---|
| `code` | 9 | 10 | 11 | ['code'] |
| `decoder` | 2 | 1 | 2 | ['decoder'] |
| `embedding` | 5 | 6 | 7 | ['embedding'] |
| `noise` | 1 | 0 | 2 | ['noise', 'sink'] |
| `routing` | 2 | 3 | 5 | ['routing', 'schedule'] |

largest miss: 2 nodes
