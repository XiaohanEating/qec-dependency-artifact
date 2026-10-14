"""Semantically different component substitutions, measured with confidence.

The audit finds that the subject's five dimensions each have an extension point,
but the earlier version of this experiment reported rate differences without
intervals and drew conclusions from differences of 0.0016 that are inside the
sampling noise.  This version reports every rate with a Wilson 95% interval and
every comparison with a two-proportion z-test, and it separates two questions
that were previously conflated:

* **Does the substitution change the artifact?**  A deterministic comparison of
  circuit text, detector error model and layout payload.  This is the question the
  audit answers, and it is answered yes for the dimensions the audit flags.
* **Does the substitution change the measured rate?**  A statistical question,
  answered independently, and answered no at these operating points for most
  dimensions.  Reporting only the second would have hidden that; reporting only
  the first would have implied the second.

Code families are reported with their distance and logical-qubit counts, and the
rate comparison across families is marked as *not comparable* unless the family
keeps the same distance, because a logical error rate between codes of different
size measures nothing about the substitution.

Outputs: ``semantic_replacements.json`` and ``semantic_replacements.md``.

Run:  python experiments/semantic_replacements.py [--shots N]
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

import qec_measure as Q  # noqa: E402

DEFAULT_SHOTS = 1000
NUM_ROUNDS = 2
W, F = 3, 1
SAMPLER_SEED = 7

CODE_FAMILIES = ("BB", "HGP", "QLP")


def _sha(obj) -> str:
    data = obj if isinstance(obj, bytes) else str(obj).encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]


def artifact_record(built) -> dict:
    """Deterministic fingerprints of everything the pipeline produces."""
    obj = built["code_obj"]
    return {
        "code_matrices": _sha(b"".join(
            m.tobytes() for m in (obj.hz, obj.hx, obj.lz, obj.lx))),
        "stim_circuit": _sha(str(built["circuit"])),
        "detector_error_model": _sha(str(built["dem"])),
        "num_detectors": built["dem"].num_detectors,
        "num_observables": built["dem"].num_observables,
        "check_matrix_nonzeros": Q.dem_shape(built["dem"])["check_matrix_nonzeros"],
        "mean_prior": Q.dem_shape(built["dem"])["mean_prior"],
    }


def _rate(built, shots, seed=SAMPLER_SEED):
    pred = np.asarray(Q.decode(built, shots=shots, seed=seed, W=W, F=F))
    k, n = int(pred.sum()), int(pred.size)
    k_any, _ = Q.logical_failure(pred)
    return k, n, k_any, shots


def substitution_row(dimension, base_built, alt_built, shots,
                     comparable_note=None, seed=SAMPLER_SEED):
    """One substitution: artifact comparison plus rate comparison, separately."""
    a_art, b_art = artifact_record(base_built), artifact_record(alt_built)
    changed = sorted(k for k in a_art
                     if k not in ("num_detectors", "num_observables",
                                  "check_matrix_nonzeros", "mean_prior")
                     and a_art[k] != b_art[k])
    structure_changed = (
        a_art["check_matrix_nonzeros"] != b_art["check_matrix_nonzeros"]
        or a_art["num_detectors"] != b_art["num_detectors"])

    k_base, n_base, k_any_base, shots_base = _rate(base_built, shots, seed)
    k_alt, n_alt, k_any_alt, shots_alt = _rate(alt_built, shots, seed)
    test = Q.two_proportion_z(k_base, n_base, k_alt, n_alt)
    test_any = Q.two_proportion_z(k_any_base, shots_base, k_any_alt, shots_alt)

    return {
        "dimension": dimension,
        "base_spec": base_built["spec"],
        "alt_spec": alt_built["spec"],
        "artifact_changed": bool(changed),
        "artifacts_changed": changed,
        "structure_changed": bool(structure_changed),
        "rate": {
            "base": Q.rate_record(k_base, n_base, "base",
                                  per_logical_qubit_rate=k_base / n_base,
                                  any_observable_rate=k_any_base / shots_base,
                                  any_observable_errors=k_any_base),
            "alt": Q.rate_record(k_alt, n_alt, "alt",
                                 per_logical_qubit_rate=k_alt / n_alt,
                                 any_observable_rate=k_any_alt / shots_alt,
                                 any_observable_errors=k_any_alt),
            "intervals_overlap": not Q.intervals_disjoint(
                Q.wilson(k_base, n_base), Q.wilson(k_alt, n_alt)),
            "two_proportion_test": test,
            "two_proportion_test_per_bit": test,
            "two_proportion_test_any_observable": test_any,
            "rate_separable": bool(test["significant_at_95"]),
            "rate_separable_any_observable": bool(test_any["significant_at_95"]),
        },
        "comparability_note": comparable_note,
    }


def run(shots: int = DEFAULT_SHOTS) -> dict:
    rows = []

    # --- code families -------------------------------------------------------
    # Reported with distance and k so a reader can see that a cross-family rate
    # comparison is not a like-for-like substitution measurement.
    families = {}
    for fam in CODE_FAMILIES:
        built = Q.build(fam, "zxcoloration", "SD6", num_rounds=NUM_ROUNDS)
        k, n, k_any, _ = _rate(built, shots)
        obj = built["code_obj"]
        families[fam] = {
            "n_physical_qubits": int(obj.hz.shape[1]),
            "n_logical_qubits": int(obj.lz.shape[0]),
            "n_detectors": built["dem"].num_detectors,
            "rate": Q.rate_record(k, n, f"{fam}/zxcoloration/SD6",
                                  per_logical_qubit_rate=k / n),
        }
    rows.append({
        "dimension": "code",
        "families": families,
        "artifact_changed": True,
        "artifacts_changed": ["code_matrices", "stim_circuit",
                              "detector_error_model"],
        "structure_changed": True,
        "rate": None,
        "rate_separable": None,
        "comparability_note": (
            "the three families have different distances and logical-qubit "
            "counts, so their rates are not comparable as a substitution "
            "measurement; a like-for-like comparison needs a fixed distance, "
            "which this subject does not expose"),
    })

    # --- extractor -----------------------------------------------------------
    zx = Q.build("BB", "zxcoloration", "SD6", num_rounds=NUM_ROUNDS)
    cu = Q.build("BB", "custom", "SD6", num_rounds=NUM_ROUNDS)
    rows.append(substitution_row("extractor", zx, cu, shots))

    # --- architecture --------------------------------------------------------
    tr = Q.build("BB", "zxcoloration", "SD6", arch="transversal", num_rounds=NUM_ROUNDS)
    to = Q.build("BB", "zxcoloration", "SD6", arch="toric", num_rounds=NUM_ROUNDS)
    arch_row = substitution_row("arch", tr, to, shots)
    arch_row["comparability_note"] = (
        "the layout changes but the circuit does not: ZXColorationBuilder "
        "constructs its own TransversalLayout internally, so the arch "
        "coordinate does not reach the artifact")
    rows.append(arch_row)

    # --- noise ---------------------------------------------------------------
    sd6 = Q.build("BB", "zxcoloration", "SD6", num_rounds=NUM_ROUNDS)
    si = Q.build("BB", "zxcoloration", "SI1000", num_rounds=NUM_ROUNDS)
    noise_row = substitution_row("noise", sd6, si, shots)
    noise_row["comparability_note"] = (
        "the noise coordinate is baked into the circuit: changing it changes "
        "the circuit text and the detector error model, which is the audit's "
        "third observation (extractor reads noise)")
    rows.append(noise_row)

    # --- decoder (compared on the same circuit and samples) -------------------
    decoder_row = _decoder_substitution(sd6, shots)
    rows.append(decoder_row)

    return {
        "metadata": {
            "description": "semantically different component substitutions, "
                           "measured with confidence intervals",
            "date": date.today().isoformat(),
            "shots": shots, "num_rounds": NUM_ROUNDS,
            "window": W, "overlap": F, "sampler_seed": SAMPLER_SEED,
            "statistics": "Wilson 95% per rate; two-proportion z per comparison "
                          "on both the per-logical-bit and any-observable scales",
            "agreement_check": Q.agreement_check(zx, shots=24, seed=SAMPLER_SEED),
        },
        "substitutions": rows,
        "summary": _summarize(rows),
    }


def _decoder_substitution(built, shots, seed=SAMPLER_SEED):
    """BP-OSD vs BP-LSD on the same circuit and the same sampled syndromes."""
    from quits.decoder import (sliding_window_bplsd_circuit_mem,
                               sliding_window_bposd_circuit_mem)
    from quits.simulation import get_stim_mem_result

    c, hz, lz = built["circuit"], built["hz"], built["lz"]
    det, _ = get_stim_mem_result(c, shots, seed=seed)
    out = {}
    for name, fn in (("BP-OSD", sliding_window_bposd_circuit_mem),
                     ("BP-LSD", sliding_window_bplsd_circuit_mem)):
        pred = np.asarray(fn(det.copy(), c, hz, lz, W=W, F=F))
        out[name] = (int(pred.sum()), int(pred.size),
                     int(np.any(pred != 0, axis=1).sum()))
    (ko, no, ao), (kl, nl, al) = out["BP-OSD"], out["BP-LSD"]
    test = Q.two_proportion_z(ko, no, kl, nl)
    test_any = Q.two_proportion_z(ao, shots, al, shots)
    return {
        "dimension": "decoder",
        "base_spec": built["spec"],
        "alt_spec": {**built["spec"], "decoder": "BP-LSD"},
        "artifact_changed": False,
        "artifacts_changed": [],
        "structure_changed": False,
        "rate": {
            "base": Q.rate_record(ko, no, "BP-OSD",
                                  per_logical_qubit_rate=ko / no,
                                  any_observable_rate=ao / shots,
                                  any_observable_errors=ao),
            "alt": Q.rate_record(kl, nl, "BP-LSD",
                                 per_logical_qubit_rate=kl / nl,
                                 any_observable_rate=al / shots,
                                 any_observable_errors=al),
            "intervals_overlap": not Q.intervals_disjoint(
                Q.wilson(ko, no), Q.wilson(kl, nl)),
            "two_proportion_test": test,
            "two_proportion_test_per_bit": test,
            "two_proportion_test_any_observable": test_any,
            "rate_separable": bool(test["significant_at_95"]),
            "rate_separable_any_observable": bool(test_any["significant_at_95"]),
        },
        "comparability_note": (
            "both decoders run on identical circuits and identical sampled "
            "syndromes; the only difference is the inner decoder class"),
    }


def _summarize(rows):
    with_rate = [r for r in rows if r.get("rate")]
    artifact_yes = sum(1 for r in rows if r["artifact_changed"])
    separable = sum(1 for r in with_rate if r["rate"]["rate_separable"])
    separable_any = sum(
        1 for r in with_rate if r["rate"]["rate_separable_any_observable"])
    return {
        "n_substitutions": len(rows),
        "n_artifact_changed": artifact_yes,
        "n_with_rate_comparison": len(with_rate),
        "n_rate_separable": separable,
        "n_rate_separable_any_observable": separable_any,
        "verdict": (
            "artifact changes and rate changes are different questions: "
            f"{artifact_yes} of {len(rows)} substitutions change an artifact, "
            f"but only {separable} of {len(with_rate)} comparable rate "
            "comparisons separate (per-logical-bit scale; "
            f"{separable_any} separate on the any-observable scale)"),
        "interpretation": (
            "an artifact-level substitution is not automatically a rate-level "
            "substitution. The noise coordinate changes both, because it is "
            "baked into the circuit. The decoder substitution changes no "
            "artifact and no rate, because the decoder's task is unchanged. "
            "The extractor substitution is scale-dependent: it changes the "
            "circuit and moves the per-logical-bit rate (the two extraction "
            "schedules distribute the same physical errors differently across "
            "the 12 observables), while the any-observable failure rate is "
            "unchanged. A study that substitutes a decoder and reports 'no "
            "significant difference' is reporting a real property of the "
            "substitution, not a null result about the software."),
    }


def to_markdown(data: dict) -> str:
    m = data["metadata"]
    s = data["summary"]
    ac = m["agreement_check"]
    L = ["# Semantically different substitutions, measured with confidence", "",
         f"Generated: {m['date']}",
         f"Shots: {m['shots']}; rounds={m['num_rounds']}, W={m['window']}, "
         f"F={m['overlap']}, seed={m['sampler_seed']}",
         f"Statistics: {m['statistics']}",
         f"Decoder path verified bitwise against the official implementation: "
         f"**{ac['bitwise_identical']}**", ""]

    L += ["## 1. Code families (not a like-for-like substitution)", "",
          "| family | n | k | detectors | per-logical-qubit rate | Wilson 95% |",
          "|---|---|---|---|---|---|"]
    code_row = next(r for r in data["substitutions"] if r["dimension"] == "code")
    for fam, info in code_row["families"].items():
        r = info["rate"]
        L.append(f"| `{fam}` | {info['n_physical_qubits']} "
                 f"| {info['n_logical_qubits']} | {info['n_detectors']} "
                 f"| {r['per_logical_qubit_rate']:.4f} "
                 f"| [{r['wilson95_low']:.4f}, {r['wilson95_high']:.4f}] |")
    L += ["", f"{code_row['comparability_note']}", ""]

    L += ["## 2. Substitutions with a rate comparison", "",
          "| dimension | substitution | artifact changed? | structure changed? "
          "| base rate | alt rate | z (per-bit) | p | z (any-obs) | p (any-obs) "
          "| rate separable? |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in data["substitutions"]:
        if not r.get("rate"):
            continue
        rt = r["rate"]
        base = rt["base"]
        alt = rt["alt"]
        t = rt["two_proportion_test"]
        ta = rt["two_proportion_test_any_observable"]
        a = f"{base['per_logical_qubit_rate']:.4f}"
        b = f"{alt['per_logical_qubit_rate']:.4f}"
        L.append(f"| `{r['dimension']}` "
                 f"| `{base['label']}` -> `{alt['label']}` "
                 f"| {r['artifact_changed']} | {r['structure_changed']} "
                 f"| {a} | {b} | {t['z']:.3f} | {t['p_value']:.3g} "
                 f"| {ta['z']:.3f} | {ta['p_value']:.3g} "
                 f"| **{rt['rate_separable']}** |")

    L += ["", f"- artifact-changing substitutions: "
          f"**{s['n_artifact_changed']} of {s['n_substitutions']}**",
          f"- rate-separable substitutions (per-logical-bit): "
          f"**{s['n_rate_separable']} of {s['n_with_rate_comparison']}**; "
          f"any-observable scale: "
          f"**{s['n_rate_separable_any_observable']} of "
          f"{s['n_with_rate_comparison']}**",
          f"- verdict: {s['verdict']}", ""]

    L += ["### Per-substitution notes", ""]
    for r in data["substitutions"]:
        if r.get("comparability_note"):
            L.append(f"- **{r['dimension']}**: {r['comparability_note']}")
    L += ["", "## 3. Interpretation", "", s["interpretation"], ""]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out = None
    if "--out" in argv:
        i = argv.index("--out")
        out = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    shots = int(argv[argv.index("--shots") + 1]) if "--shots" in argv else DEFAULT_SHOTS
    data = run(shots=shots)
    target = out or HERE
    target.mkdir(parents=True, exist_ok=True)
    (target / "semantic_replacements.json").write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8")
    (target / "semantic_replacements.md").write_text(to_markdown(data), encoding="utf-8")
    print(f"semantic_replacements: wrote to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())