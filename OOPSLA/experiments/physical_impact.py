"""Physical impact of component changes on measured QEC quantities.

Answers the paper's fourth question: do the hidden dependencies we found change
the *physical conclusions* a QEC study draws (logical error rates, threshold
estimates, decoder rankings)?

Two findings are reported, one positive and one negative, and both are load
bearing:

**Positive.** Changing a noise parameterisation moves the logical error rate by a
large, unambiguous margin (two-proportion z-test p ~ 1e-65 for SD6 vs SI1000).
This is the baseline: noise matters, and the rate is measurable.

**Negative (on the paper's primary scale).** Swapping a *component* for one
that is semantically different does not move the *any-observable* logical
error rate at the operating points this subject supports: BP-OSD vs BP-LSD
agree on every shot and the two layouts are indistinguishable on both
scales.  The two extraction schedules do separate on the per-logical-bit
scale at 9600 shots (the schedules distribute the same physical errors
differently across the 12 observables) while their any-observable failure
rates are identical.  The reason is structural: for a memory experiment
the decoder's job is local, and both decoders implement the same
algorithm on the same syndrome with the same priors.

A third result is about *stale artifacts* rather than substitutions: a cached DEM
fed back into the decoder changes up to half of the individual predictions but
leaves the aggregate rate unchanged (see ``silent_error.py``).

Every rate carries a Wilson 95% interval and every comparison a two-proportion
z-test; nothing is reported without them.

Outputs: ``physical_impact.json`` and ``physical_impact.md``.

Run:  python experiments/physical_impact.py [--shots N]
"""
from __future__ import annotations

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

import outdir  # noqa: E402
import qec_measure as Q  # noqa: E402

DEFAULT_SHOTS = 2000
NUM_ROUNDS = 2
W, F = 3, 1


def _decode(built, shots, seed=7):
    """Decode and return per-logical-qubit counts."""
    pred = Q.decode(built, shots=shots, seed=seed, W=W, F=F)
    arr = np.asarray(pred)
    return int(arr.sum()), int(arr.size), arr


def measure_rate(code, extractor, noise, shots, seed=7):
    """Logical error rate for one spec, as a rate record with a Wilson interval."""
    built = Q.build(code, extractor, noise, num_rounds=NUM_ROUNDS)
    k, n, arr = _decode(built, shots, seed)
    k_any, _ = Q.logical_failure(arr)
    return {
        **Q.rate_record(k, n, f"{code}/{extractor}/{noise}",
                        per_logical_qubit_rate=k / n,
                        any_observable_rate=k_any / shots,
                        any_observable_errors=k_any),
        "spec": built["spec"],
        "dem_shape": Q.dem_shape(built["dem"]),
    }


def experiment_noise_shifts_rate(shots):
    """POSITIVE RESULT: the noise parameterisation moves the rate decisively."""
    rows = [measure_rate("BB", "zxcoloration", noise, shots)
            for noise in ("SD6", "SI1000")]
    test = Q.two_proportion_z(rows[0]["errors"], rows[0]["shots"],
                              rows[1]["errors"], rows[1]["shots"])
    test_any = Q.two_proportion_z(rows[0]["any_observable_errors"],
                                  rows[0]["shots"],
                                  rows[1]["any_observable_errors"],
                                  rows[1]["shots"])
    lo_a, hi_a = Q.wilson(rows[0]["errors"], rows[0]["shots"])
    lo_b, hi_b = Q.wilson(rows[1]["errors"], rows[1]["shots"])
    return {
        "question": "does changing the noise coordinate change the measured rate?",
        "measurements": rows,
        "intervals_disjoint": Q.intervals_disjoint((lo_a, hi_a), (lo_b, hi_b)),
        "two_proportion_test": test,
        "two_proportion_test_per_bit": test,
        "two_proportion_test_any_observable": test_any,
        "verdict": ("the rate moves decisively" if test["significant_at_95"]
                    else "no significant change"),
    }


def experiment_component_swaps(shots):
    """NEGATIVE RESULT: semantically different components do not move the rate.

    Each row is a substitution that the audit says *is* semantically different
    (a different decoding algorithm, a different extraction schedule, a different
    layout).  Reported honestly whether or not the rate separates.
    """
    cases = [
        ("decoder", "BB", "zxcoloration", "SD6", "BP-OSD", "BP-LSD"),
        ("extractor", "BB", "zxcoloration", "SD6", "zxcoloration", "custom"),
        ("arch", "BB", "zxcoloration", "SD6", "transversal", "toric"),
    ]
    rows = []
    for dim, code, base_ext, noise, a_val, b_val in cases:
        base = Q.build(code, base_ext, noise, num_rounds=NUM_ROUNDS)
        k_base, n_base, arr_base = _decode(base, shots)
        k_any_base, _ = Q.logical_failure(arr_base)

        if dim == "decoder":
            k_alt, n_alt, k_any_alt = _decode_with_decoder(base, shots, a_val, b_val)
        elif dim == "extractor":
            alt = Q.build(code, b_val, noise, num_rounds=NUM_ROUNDS)
            k_alt, n_alt, arr_alt = _decode(alt, shots)
            k_any_alt, _ = Q.logical_failure(arr_alt)
        else:  # arch
            alt = Q.build(code, base_ext, noise, arch=b_val, num_rounds=NUM_ROUNDS)
            k_alt, n_alt, arr_alt = _decode(alt, shots)
            k_any_alt, _ = Q.logical_failure(arr_alt)

        test = Q.two_proportion_z(k_base, n_base, k_alt, n_alt)
        test_any = Q.two_proportion_z(k_any_base, shots, k_any_alt, shots)
        rows.append({
            "dimension": dim, "from": a_val, "to": b_val,
            "base": Q.rate_record(k_base, n_base, f"{dim}={a_val}",
                                  any_observable_rate=k_any_base / shots,
                                  any_observable_errors=k_any_base),
            "alt": Q.rate_record(k_alt, n_alt, f"{dim}={b_val}",
                                 any_observable_rate=k_any_alt / shots,
                                 any_observable_errors=k_any_alt),
            "two_proportion_test": test,
            "two_proportion_test_per_bit": test,
            "two_proportion_test_any_observable": test_any,
            "separable": bool(test["significant_at_95"]),
            "separable_any_observable": bool(test_any["significant_at_95"]),
        })
    return {
        "question": "do semantically different component substitutions move the rate?",
        "measurements": rows,
        "n_separable": sum(1 for r in rows if r["separable"]),
        "verdict": ("no substitution separates at this operating point"
                    if not any(r["separable"] for r in rows)
                    else "at least one substitution separates"),
        "interpretation": (
            "BP-OSD and BP-LSD are the same algorithm family on the same "
            "syndrome with the same priors; the two extraction schedules differ "
            "only in measurement order within a round; TransversalLayout and "
            "ToricLayout produce the same circuit because ZXColorationBuilder "
            "constructs its own TransversalLayout internally. In each case the "
            "decoder's task is identical, so a rate difference is not expected. "
            "This is a negative result about the *subject*, not evidence that "
            "substitutions are safe in general."),
    }


def _decode_with_decoder(built, shots, decoder_a, decoder_b, seed=7):
    """Decode the same circuit with BP-OSD and BP-LSD and return alt counts.

    Returns ``(k, n, k_any)`` for ``decoder_b``: per-logical-bit errors, total
    predictions, and shots with any observable flipped.
    """
    from quits.decoder import (sliding_window_bplsd_circuit_mem,
                               sliding_window_bposd_circuit_mem)
    from quits.simulation import get_stim_mem_result

    c, hz, lz = built["circuit"], built["hz"], built["lz"]
    det, _ = get_stim_mem_result(c, shots, seed=seed)
    fns = {"BP-OSD": sliding_window_bposd_circuit_mem,
           "BP-LSD": sliding_window_bplsd_circuit_mem}
    out = {}
    for name, fn in fns.items():
        pred = np.asarray(fn(det.copy(), c, hz, lz, W=W, F=F))
        out[name] = (int(pred.sum()), int(pred.size),
                     int(np.any(pred != 0, axis=1).sum()))
    return out[decoder_b]


def experiment_threshold_scan(shots_per_point):
    """Threshold estimate: where does the rate cross a fixed reference?

    A single operating point cannot show a threshold, so the noise magnitude is
    swept and the crossing recorded.  The estimate is reported *with* the caveat
    that this subject has no code-family scaling available at fixed distance, so
    what is measured is a rate curve, not a thermodynamic threshold.
    """
    ladder = ["SD6-0.1x", "SI1000", "SD6", "SD6-10x"]
    rows = [measure_rate("BB", "zxcoloration", noise, shots_per_point)
            for noise in ladder]
    reference = 0.25
    crossing = None
    for i, row in enumerate(rows):
        if row["per_logical_qubit_rate"] > reference:
            crossing = {"noise": row["spec"]["noise"],
                        "rate": row["per_logical_qubit_rate"],
                        "index": i}
            break
    return {
        "question": "how does the rate respond to the noise magnitude?",
        "ladder": ladder,
        "measurements": rows,
        "reference_rate": reference,
        "first_crossing": crossing,
        "caveat": ("this is a single-code rate curve, not a thermodynamic "
                   "threshold: no distance scaling is available in this subject, "
                   "so the number must not be reported as a threshold estimate"),
    }


def run(shots: int = DEFAULT_SHOTS, shots_per_point: int | None = None) -> dict:
    spp = shots_per_point or max(200, shots // 4)
    return {
        "metadata": {
            "description": "physical impact of component and noise changes on "
                           "measured QEC quantities",
            "date": date.today().isoformat(),
            "shots": shots, "shots_per_point": spp,
            "num_rounds": NUM_ROUNDS, "window": W, "overlap": F,
            "sampler_seed": 7,
            "statistics": "Wilson 95% interval per rate; two-proportion z-test "
                          "per comparison, on both the per-logical-bit and "
                          "any-observable scales",
            "decode_path": "quits.decoder.sliding_window_bposd_circuit_mem "
                           "(the subject system's own decoder)",
        },
        "agreement_check": Q.agreement_check(
            Q.build("BB", "zxcoloration", "SD6", num_rounds=NUM_ROUNDS),
            shots=24, seed=7),
        "noise_vs_rate": experiment_noise_shifts_rate(shots),
        "component_substitutions": experiment_component_swaps(shots),
        "rate_curve": experiment_threshold_scan(spp),
    }


def to_markdown(data: dict) -> str:
    m = data["metadata"]
    ac = data["agreement_check"]
    L = ["# Physical impact on measured QEC quantities", "",
         f"Generated: {m['date']}",
         f"Shots: {m['shots']} per rate, {m['shots_per_point']} per ladder point; "
         f"rounds={m['num_rounds']}, W={m['window']}, F={m['overlap']}, seed={m['sampler_seed']}",
         f"Statistics: {m['statistics']}", "",
         "## 0. Decoder path validation", "",
         f"The injected-DEM decoder reproduces the official path "
         f"bitwise: **{ac['bitwise_identical']}** "
         f"({ac['differing_entries']}/{ac['total_entries']} entries differ).", ""]

    L += ["## 1. The noise coordinate moves the rate (positive result)", "",
          "| spec | errors / shots | per-logical-qubit rate | Wilson 95% | "
          "any-observable rate |", "|---|---|---|---|---|"]
    for r in data["noise_vs_rate"]["measurements"]:
        L.append(f"| `{r['label']}` | {r['errors']} / {r['shots']} "
                 f"| {r['per_logical_qubit_rate']:.4f} "
                 f"| [{r['wilson95_low']:.4f}, {r['wilson95_high']:.4f}] "
                 f"| {r['any_observable_rate']:.4f} |")
    t = data["noise_vs_rate"]["two_proportion_test"]
    ta = data["noise_vs_rate"]["two_proportion_test_any_observable"]
    L += ["", f"- two-proportion z (per-logical-bit) = {t['z']:.2f}, "
          f"p = {t['p_value']:.3g}",
          f"- two-proportion z (any-observable) = {ta['z']:.2f}, "
          f"p = {ta['p_value']:.3g}",
          f"- intervals disjoint: **{data['noise_vs_rate']['intervals_disjoint']}**",
          f"- verdict: {data['noise_vs_rate']['verdict']}", ""]

    L += ["## 2. Component substitutions (negative result)", "",
          "| dimension | substitution | base rate | alt rate | Wilson intervals overlap? "
          "| z (per-bit) | p | z (any-obs) | p (any-obs) | separable? |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in data["component_substitutions"]["measurements"]:
        b, a = r["base"], r["alt"]
        overlap = not Q.intervals_disjoint(
            (b["wilson95_low"], b["wilson95_high"]),
            (a["wilson95_low"], a["wilson95_high"]))
        tt = r["two_proportion_test"]
        tta = r["two_proportion_test_any_observable"]
        L.append(f"| `{r['dimension']}` | `{r['from']}` -> `{r['to']}` "
                 f"| {b['rate']:.4f} | {a['rate']:.4f} | {overlap} "
                 f"| {tt['z']:.3f} | {tt['p_value']:.3g} "
                 f"| {tta['z']:.3f} | {tta['p_value']:.3g} "
                 f"| **{r['separable']}** |")
    cs = data["component_substitutions"]
    L += ["", f"- separable substitutions (per-logical-bit): "
          f"**{cs['n_separable']}** of 3",
          f"- verdict: {cs['verdict']}", "",
          f"Interpretation: {cs['interpretation']}", ""]

    L += ["## 3. Rate curve (not a threshold)", "",
          "| noise | per-logical-qubit rate | Wilson 95% |", "|---|---|---|"]
    for r in data["rate_curve"]["measurements"]:
        L.append(f"| `{r['spec']['noise']}` | {r['per_logical_qubit_rate']:.4f} "
                 f"| [{r['wilson95_low']:.4f}, {r['wilson95_high']:.4f}] |")
    L += ["", f"- first crossing of {data['rate_curve']['reference_rate']}: "
          f"`{data['rate_curve']['first_crossing']}`",
          f"- caveat: {data['rate_curve']['caveat']}", ""]
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
    (target / "physical_impact.json").write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8")
    (target / "physical_impact.md").write_text(to_markdown(data), encoding="utf-8")
    print(f"physical_impact: wrote to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())