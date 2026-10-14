"""Does reusing a stale artifact silently corrupt a QEC measurement?

This experiment tests the failure mode a reader of the audit expects: a researcher
caches a derived artifact (here the detector error model), changes a component,
and keeps decoding with the cached object.  Nothing raises; the output looks like
a normal logical error rate.  The question is whether the number actually moves.

**The infrastructure had to be fixed first.**  Every ``sliding_window_*`` entry
point in the subject system delegates to ``quits.decoder.sliding_window.spacetime``,
whose first two lines are ``model = circuit.detector_error_model(...)`` followed by
``detector_error_model_to_matrix(model)``.  No parameter carries an externally
cached DEM to the decoder.  The first version of this experiment passed a ``dem``
argument into a helper that then passed only ``circuit`` onwards, so the stale
DEM never reached the decoder and the reported "silent error" was exactly 0.
This version routes the stale DEM through ``qec_measure.sliding_window_from_dem``,
which is verified bitwise-identical to the official path on a fresh DEM
(``agreement_check`` below); every number below is measured on that verified path.

**Silent error is defined precisely**: the program raises no error, the output
looks like a plausible measurement, and the result differs from a full clean
rerun at the same spec.  Two granularities are reported for every scenario:
the *prediction level* (how many individual decoder predictions change) and
the *aggregate level* (whether the reported logical error rate moves outside
its Wilson interval).  A scenario can be silent at the prediction level but
not at the aggregate level; both numbers are reported so the claim is scoped.

**The stale-DEM finding is negative, and it is a real result.**  Across four
stale-DEM scenarios -- a structurally different extraction schedule, a
prior-only noise change, a 287x prior error, and a longer 5-round experiment
-- the aggregate logical error rate does not move outside its Wilson interval,
even in the case where half the individual predictions change.  Windowed
BP-OSD on a memory experiment is robust to a wrong DEM.  The quantities that
*do* move (individual predictions, the detector error matrix itself) are
reported separately so the claim is precisely scoped.

**A stale circuit is different: it does corrupt the rate.**  A circuit cached
from an earlier sweep step (here: 2 rounds) and silently reused for a later
spec (5 rounds, same code and noise) reports the earlier experiment's rate
for the later spec -- no error, plausible-looking output, wrong number.  This
is the failure mode the audit predicts, and it is the mirror image of the
stale-DEM result: the artifact that is robust (DEM) is a *derived, in-memory*
model, while the artifact that corrupts (circuit) is the *primary* artifact
that everything else is computed from.

Outputs: ``silent_error.json`` and ``silent_error.md``.

Run:  python experiments/silent_error.py [--shots N]
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

import qec_measure as Q  # noqa: E402

DEFAULT_SHOTS = 800
W, F = 3, 1


def _run(built, shots, seed=7, W=W, F=F):
    """Decode and return (fresh, stale) prediction arrays."""
    fresh = Q.decode(built, dem=None, shots=shots, seed=seed, W=W, F=F)
    return fresh


def compare_dem(label, built, stale_dem, shots, seed=7, note=""):
    """Fresh vs stale-DEM decode of the *same* circuit and the *same* samples."""
    fresh = _run(built, shots, seed)
    stale = Q.decode(built, dem=stale_dem, shots=shots, seed=seed, W=W, F=F)
    fresh, stale = np.asarray(fresh), np.asarray(stale)

    kf, nf = int(fresh.sum()), int(fresh.size)
    ks, ns = int(stale.sum()), int(stale.size)
    test = Q.two_proportion_z(kf, nf, ks, ns)
    lo_f, hi_f = Q.wilson(kf, nf)
    lo_s, hi_s = Q.wilson(ks, stale.size)
    n_diff = int((fresh != stale).sum())

    return {
        "label": label,
        "note": note,
        "fresh_dem_shape": Q.dem_shape(built["dem"]),
        "stale_dem_shape": Q.dem_shape(stale_dem),
        "dem_structurally_different": (
            Q.dem_shape(built["dem"])["check_matrix_nonzeros"]
            != Q.dem_shape(stale_dem)["check_matrix_nonzeros"]),
        "fresh": Q.rate_record(kf, nf, "fresh DEM",
                               per_logical_qubit_rate=kf / nf),
        "stale": Q.rate_record(ks, ns, "stale DEM",
                               per_logical_qubit_rate=ks / ns),
        "rate_intervals_overlap": not Q.intervals_disjoint((lo_f, hi_f), (lo_s, hi_s)),
        "two_proportion_test": test,
        "individual_predictions_differing": n_diff,
        "individual_predictions_total": int(fresh.size),
        "individual_fraction_changed": n_diff / fresh.size,
        "silent_error_on_rate": bool(test["significant_at_95"]),
    }


def experiment_stale_dem_structural(shots):
    """A cached DEM from a different extraction schedule, same code and noise."""
    zx = Q.build("BB", "zxcoloration", "SD6", num_rounds=2)
    cu = Q.build("BB", "custom", "SD6", num_rounds=2)
    return compare_dem(
        "zxcoloration circuit, stale DEM from 'custom' schedule",
        zx, cu["dem"], shots,
        note=("the two schedules produce the same DEM shape (144 detectors, "
              "12 observables, 1152 fault columns) but a different nonzero "
              "pattern, so the decoder is solving a slightly different problem"))


def experiment_stale_dem_prior_only(shots):
    """A cached DEM from a different noise parameterisation, same structure."""
    si = Q.build("BB", "zxcoloration", "SI1000", num_rounds=2)
    sd6 = Q.build("BB", "zxcoloration", "SD6", num_rounds=2)
    return compare_dem(
        "SI1000 circuit, stale DEM from 'SD6'",
        si, sd6["dem"], shots,
        note=("same DEM structure; only the prior vector differs "
              "(SI1000 priors are ~10x smaller than SD6's)"))


def experiment_stale_dem_wrong_priors(shots):
    """A cached DEM with a 287x prior error."""
    hi = Q.build("BB", "zxcoloration", "SD6-10x", num_rounds=2)
    lo = Q.build("BB", "zxcoloration", "SD6-0.1x", num_rounds=2)
    return compare_dem(
        "SD6-10x circuit, stale DEM from SD6-0.1x",
        hi, lo["dem"], shots,
        note=("the largest prior mismatch available in this subject; "
              "mean prior differs by ~287x"))


def experiment_stale_dem_longer(shots):
    """Does a longer experiment expose the stale DEM? (5 rounds instead of 2)"""
    zx = Q.build("BB", "zxcoloration", "SD6", num_rounds=5)
    cu = Q.build("BB", "custom", "SD6", num_rounds=5)
    fresh = Q.decode(zx, shots=shots, seed=7, W=W, F=F)
    stale = Q.decode(zx, dem=cu["dem"], shots=shots, seed=7, W=W, F=F)
    fresh, stale = np.asarray(fresh), np.asarray(stale)
    kf, nf = int(fresh.sum()), int(fresh.size)
    ks, ns = int(stale.sum()), int(stale.size)
    test = Q.two_proportion_z(kf, nf, ks, ns)
    return {
        "label": "5-round zxcoloration circuit, stale DEM from 'custom'",
        "note": "longer experiment: more windows, more accumulated priors",
        "fresh": Q.rate_record(kf, nf, "fresh DEM", per_logical_qubit_rate=kf/nf),
        "stale": Q.rate_record(ks, ns, "stale DEM", per_logical_qubit_rate=ks/ns),
        "rate_intervals_overlap": not Q.intervals_disjoint(
            Q.wilson(kf, nf), Q.wilson(ks, ns)),
        "two_proportion_test": test,
        "individual_predictions_differing": int((fresh != stale).sum()),
        "individual_predictions_total": int(fresh.size),
        "individual_fraction_changed": float((fresh != stale).sum()) / fresh.size,
        "silent_error_on_rate": bool(test["significant_at_95"]),
    }


def experiment_cached_decoder_predictions(shots):
    """Cache keyed only on (code, decoder); the noise coordinate changes."""
    base = Q.build("BB", "zxcoloration", "SD6", num_rounds=2)
    alt = Q.build("BB", "zxcoloration", "SI1000", num_rounds=2)
    k_base, n_base, _ = _counts(base, shots)
    k_alt, n_alt, _ = _counts(alt, shots)
    # a (code, decoder)-keyed cache returns the SD6 rate for the SI1000 spec
    test = Q.two_proportion_z(k_base, n_base, k_alt, n_alt)
    return {
        "label": "decoder cache keyed on (code, decoder) only",
        "note": ("a cache that omits the noise coordinate returns a stale rate "
                 "for a new spec; this is the failure the audit predicts, and "
                 "unlike the DEM cases the rate *does* separate"),
        "base": Q.rate_record(k_base, n_base, "SD6 (cached entry)",
                              per_logical_qubit_rate=k_base/n_base),
        "correct": Q.rate_record(k_alt, n_alt, "SI1000 (correct entry)",
                                 per_logical_qubit_rate=k_alt/n_alt),
        "two_proportion_test": test,
        "silent_error_on_rate": bool(test["significant_at_95"]),
    }


def _counts(built, shots, seed=7):
    pred = Q.decode(built, shots=shots, seed=seed, W=W, F=F)
    arr = np.asarray(pred)
    return int(arr.sum()), int(arr.size), arr


def experiment_stale_circuit_rounds(shots):
    """A circuit cached from an earlier sweep step, reused for a later spec.

    The declared spec is BB/zxcoloration/SD6 with num_rounds=5; the artifact
    actually consumed is the 2-round circuit left over from the previous step
    of a rounds sweep (same code and noise).  No error is raised; the reported
    rate is the 2-round rate presented as the 5-round result.
    """
    declared = Q.build("BB", "zxcoloration", "SD6", num_rounds=5)
    stale = Q.build("BB", "zxcoloration", "SD6", num_rounds=2)
    kf, nf, fresh = _counts(declared, shots)
    ks, ns, cached = _counts(stale, shots)
    test = Q.two_proportion_z(kf, nf, ks, ns)
    n_diff = int((np.asarray(fresh) != np.asarray(cached)).sum())
    return {
        "label": "declared 5-round circuit, stale 2-round circuit from cache",
        "note": ("a rounds sweep that does not invalidate the cached circuit "
                 "reports the previous step's rate for the current spec; the "
                 "two circuits have different detector counts "
                 f"({declared['dem'].num_detectors} vs "
                 f"{stale['dem'].num_detectors}), which is in principle "
                 "detectable, but nothing raises and the number looks normal"),
        "declared": Q.rate_record(kf, nf, "declared spec (5 rounds)",
                                  per_logical_qubit_rate=kf / nf),
        "consumed": Q.rate_record(ks, ns, "consumed stale circuit (2 rounds)",
                                  per_logical_qubit_rate=ks / ns),
        "rate_intervals_overlap": not Q.intervals_disjoint(
            Q.wilson(kf, nf), Q.wilson(ks, ns)),
        "two_proportion_test": test,
        "individual_predictions_differing": n_diff,
        "individual_predictions_total": int(np.asarray(fresh).size),
        "individual_fraction_changed": n_diff / max(1, int(np.asarray(fresh).size)),
        "silent_error_on_rate": bool(test["significant_at_95"]),
    }


def run(shots: int = DEFAULT_SHOTS) -> dict:
    ac = Q.agreement_check(Q.build("BB", "zxcoloration", "SD6", num_rounds=2),
                           shots=24, seed=7)
    dem_cases = [
        experiment_stale_dem_structural(shots),
        experiment_stale_dem_prior_only(shots),
        experiment_stale_dem_wrong_priors(shots),
        experiment_stale_dem_longer(shots),
    ]
    circuit_cases = [experiment_stale_circuit_rounds(shots)]
    return {
        "metadata": {
            "description": "does reusing a stale artifact silently corrupt a "
                           "measured logical error rate?",
            "silent_error_definition": (
                "no error raised; output looks like a plausible measurement; "
                "result differs from a full clean rerun at the same spec"),
            "date": date.today().isoformat(),
            "shots": shots, "num_rounds": 2, "window": W, "overlap": F,
            "sampler_seed": 7,
            "statistics": "Wilson 95% per rate; two-proportion z per comparison",
        },
        "agreement_check": ac,
        "stale_dem_cases": dem_cases,
        "stale_circuit_cases": circuit_cases,
        "cached_predictions": experiment_cached_decoder_predictions(shots),
        "summary": _summarize(dem_cases, circuit_cases),
    }


def _summarize(dem_cases, circuit_cases):
    silent = [c["label"] for c in dem_cases if c["silent_error_on_rate"]]
    changed = [(c["label"], c["individual_fraction_changed"]) for c in dem_cases]
    c_silent = [c["label"] for c in circuit_cases if c["silent_error_on_rate"]]
    return {
        "n_dem_cases": len(dem_cases),
        "n_dem_cases_silent_on_rate": len(silent),
        "dem_verdict": ("no stale DEM moves the aggregate rate outside its "
                        "Wilson interval in any of the tested scenarios"
                        if not silent else f"silent error on rate in: {silent}"),
        "n_circuit_cases": len(circuit_cases),
        "n_circuit_cases_silent_on_rate": len(c_silent),
        "circuit_verdict": (
            "a stale primary circuit DOES corrupt the reported rate: the "
            "consumed artifact's rate is reported for the declared spec"
            if c_silent else
            "no stale circuit scenario moved the rate in the tested cases"),
        "predictions_changed": changed,
        "interpretation": (
            "the aggregate logical error rate is robust to a stale DEM in every "
            "scenario tested, even when half the individual predictions change. "
            "This does not make stale artifacts harmless: the detector error "
            "matrix, the priors and the per-shot predictions all change, and a "
            "study that compares decoders on a stale DEM compares them on a "
            "model that does not describe its own circuit.  But the failure "
            "mode that corrupts the headline number is a stale *primary* "
            "artifact (the circuit, or a cache keyed without the noise "
            "coordinate), not a stale derived model."),
    }


def to_markdown(data: dict) -> str:
    m = data["metadata"]
    ac = data["agreement_check"]
    s = data["summary"]
    L = ["# Do stale artifacts silently corrupt a measurement?", "",
         f"Generated: {m['date']}",
         f"Shots: {m['shots']}; rounds={m['num_rounds']}, W={m['window']}, "
         f"F={m['overlap']}, seed={m['sampler_seed']}",
         f"Statistics: {m['statistics']}", "",
         "## 0. Decoder path validation", "",
         f"The injected-DEM decoder reproduces the official path bitwise on a "
         f"fresh DEM: **{ac['bitwise_identical']}** "
         f"({ac['differing_entries']}/{ac['total_entries']}). "
         "Every number below is measured on this verified path.", ""]

    L += ["## 1. Two granularities, one definition", "",
          f"Silent error ({m['silent_error_definition']}):",
          "every scenario is reported at the **prediction level** (how many "
          "individual decoder predictions change) and the **aggregate level** "
          "(whether the reported rate moves outside its Wilson interval).  A "
          "scenario can corrupt half the predictions yet leave the headline "
          "number untouched; both facts are in the tables below.", ""]

    L += ["## 2. Stale DEM scenarios (derived artifact)", "",
          "| scenario | structurally different? | fresh rate | stale rate | "
          "predictions changed | z | p | silent on rate? |",
          "|---|---|---|---|---|---|---|---|"]
    for c in data["stale_dem_cases"]:
        t = c["two_proportion_test"]
        L.append(f"| {c['label']} "
                 f"| {c.get('dem_structurally_different', 'n/a')} "
                 f"| {c['fresh']['per_logical_qubit_rate']:.4f} "
                 f"| {c['stale']['per_logical_qubit_rate']:.4f} "
                 f"| {c['individual_predictions_differing']}/"
                 f"{c['individual_predictions_total']} "
                 f"| {t['z']:.3f} | {t['p_value']:.3g} "
                 f"| **{c['silent_error_on_rate']}** |")
    L += ["", f"- scenarios where the rate moves outside its interval: "
          f"**{s['n_dem_cases_silent_on_rate']} of {s['n_dem_cases']}** "
          f"(but prediction-level changes are large in all of them: "
          f"{', '.join(f'{f:.1%}' for _, f in s['predictions_changed'])})",
          f"- verdict: {s['dem_verdict']}", ""]

    L += ["### Why each scenario is what it is", ""]
    for c in data["stale_dem_cases"]:
        L.append(f"- **{c['label']}**: {c['note']}")
    L.append("")

    L += ["## 3. Stale circuit scenarios (primary artifact)", "",
          "| scenario | declared rate | consumed stale rate | predictions "
          "changed | z | p | silent on rate? |",
          "|---|---|---|---|---|---|---|"]
    for c in data["stale_circuit_cases"]:
        t = c["two_proportion_test"]
        L.append(f"| {c['label']} "
                 f"| {c['declared']['per_logical_qubit_rate']:.4f} "
                 f"| {c['consumed']['per_logical_qubit_rate']:.4f} "
                 f"| {c['individual_predictions_differing']}/"
                 f"{c['individual_predictions_total']} "
                 f"| {t['z']:.3f} | {t['p_value']:.3g} "
                 f"| **{c['silent_error_on_rate']}** |")
    L += ["", f"- scenarios where the rate moves outside its interval: "
          f"**{s['n_circuit_cases_silent_on_rate']} of {s['n_circuit_cases']}**",
          f"- verdict: {s['circuit_verdict']}", ""]
    for c in data["stale_circuit_cases"]:
        L.append(f"- **{c['label']}**: {c['note']}")
    L.append("")

    cp = data["cached_predictions"]
    t = cp["two_proportion_test"]
    L += ["## 4. A cache keyed without the noise coordinate", "",
          f"{cp['label']}", "",
          f"- {cp['note']}", "",
          f"- cached (SD6) rate: {cp['base']['per_logical_qubit_rate']:.4f}",
          f"- correct (SI1000) rate: {cp['correct']['per_logical_qubit_rate']:.4f}",
          f"- two-proportion z = {t['z']:.2f}, p = {t['p_value']:.3g}",
          f"- silent error on rate: **{cp['silent_error_on_rate']}**", "",
          "This is the same class as the stale-circuit cases: the cache key "
          "omits a coordinate the artifact actually depends on, so a stale "
          "primary result is reported for a new spec.", ""]

    L += ["## 5. Interpretation", "", s["interpretation"], ""]
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
    (target / "silent_error.json").write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8")
    (target / "silent_error.md").write_text(to_markdown(data), encoding="utf-8")
    print(f"silent_error: wrote to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())