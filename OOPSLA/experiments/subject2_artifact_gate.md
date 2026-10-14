# Subject 2 real-artifact gate — qecc_routing pipeline

Generated: 2026-10-12  
commit: `4ef18121c39492414b85ff36b3a61c83f9ebf95f`  
rounds: 10, lr_time: 5, seed: 20261012  
Method: compile/exec of the pinned general.py from its file path (the directory name is not a package name), truncated at the module-level experiment loop (general.py:448); substitutions are source-level re-assignments of module globals; every product is produced by the pinned code itself

> general.py:448-496 (the tqdm experiment driver, 1,000,001 iterations writing into results/) is not a definition and is not executed.  Substitutions never touch the pinned tree; they are re-assignments of module globals in the executed copy.

## Variants

| variant | patch |
|---|---|
| `baseline` | none (pinned baseline) |
| `code_alt` | general.py:18 `code` -> the repo's own commented k=8 candidate (general.py:17): [12,3,9,1,2,0,1,11,3,12,2,0,11,6] |
| `noise_alt` | only the noise globals re-assigned after their pinned definitions (general.py:39-41): probs = probs * 0.9; idle_error = 2 * idle_error |

## (a) code change moves the real artifacts

- `Hz`: changed = **True**
- `lattice`: changed = **True**
- `x_rs`: changed = **True**
- `z_rs`: changed = **True**
- `split`: changed = **True**
- `circuit`: changed = **True**
- `succ_probs_x`: changed = **True**
- `succ_probs_z`: changed = **True**
- `depolarize1_probs`: changed = **True**

verdict: **True**

## (b) noise-only change moves the {code}-declared components' products (the hidden read, on real artifacts)

- `succ_probs_x`: changed = **True** (max|Δ| = 0.456874)
- `succ_probs_z`: changed = **True** (max|Δ| = 0.456874)
- `depolarize1_probs` (incl. the idle rate): changed = **True** ([0.0, 0.0001, 0.0046, 0.0066] -> [0.0, 0.0001, 0.0082, 0.0122])
- `circuit` (stim.Circuit sha256): changed = **True**

interpretation: succ_probs and idle declare R(c) = {code} in the hand model, yet the real pipeline recomputes their products from the global `probs`/`idle_error` tables: the noise-only patch changes x/z_check_succ_probs (max|Δ| > 0) and the idle DEPOLARIZE1 probability inside the real stim.Circuit.  This is hypothesis H3 evidenced on real artifacts, on a system with no registry.

verdict: **True**

## (c) faithful components are invariant under the noise change

- `Hz`: held byte-identical = **True**
- `lattice`: held byte-identical = **True**
- `x_rs`: held byte-identical = **True**
- `z_rs`: held byte-identical = **True**
- `split`: held byte-identical = **True**

verdict: **True**

## Reproducibility

an independent second baseline load/run produces identical sha256 for every artifact: **True** ({'Hz': True, 'lattice': True, 'succ_probs': True, 'circuit': True})

## Verdict

all controls pass: **True**

