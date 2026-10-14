"""Does the noise parameterisation shift the *threshold*, not just the rate?

``physical_impact.py`` showed that swapping SD6 for SI1000 moves the logical
error rate by a huge, decisive margin at a single operating point.  A single
operating point cannot answer the follow-up question a QEC study actually
cares about: does the noise coordinate move the *threshold*?  This experiment
is the distance-scaling version of that question.

**Distance scan.**  The natural reading of "BB code, distance d" is
``BbCode(l=d, m=d, ...)``; that family is *degenerate* for the pinned shift
polynomials A_x=[3], A_y=[1,2], B_x=[1,2], B_y=[3]: measured in the pinned
tree, ``l=m=3`` gives an [[18,8,*2*]] code and ``l=m=5`` / ``l=m=7`` encode
*k=0* logical qubits (``code.lz`` is empty, so there is nothing to decode).
The nearest non-degenerate family with the same polynomials is ``(l, m) =
(3, 3d)`` for d in {2,4,6}, giving [[18,8,2]], [[36,8,4]], [[54,8,6]].  The
distance of each code is measured directly (minimum weight over the span of
the ``lz`` basis) and cross-checked against the known [[72,12,6]] BB code at
``(l, m) = (6, 6)``; the evidence, with ``file:line`` references into the
pinned tree, is recorded in ``code_evidence``.

**Error-rate grid.**  SD6 and SI1000 differ by exactly a uniform scale factor
of 5 (every SI1000 rate is 0.2x the corresponding SD6 rate in
``qec_measure.NOISE_PARAMS``).  A per-model scale factor ``s`` would therefore
sweep the two models over *different absolute* error-rate ranges, and a
threshold comparison is only meaningful in absolute units.  Each model is
instead scaled so its ``sqgate_error`` lands on a shared absolute grid
(4e-4 .. 2e-2), which for SD6 is exactly the brief's "scale SD6 by s" with
s in {0.4, ..., 20} and for SI1000 corresponds to s in {2, ..., 100}.  The
grid extends above the brief's s=2.0 because a calibration probe showed the
pseudo-threshold region lies above 2e-3 ``sqgate_error``: at s=12 the d=4
and d=6 curves cross, and beyond it the rates saturate near 0.5.  Both facts
are recorded in ``metadata.design_adjustments``.

**Threshold fit.**  For each noise model all (d, p, pL) points with pL > 0
are pooled and fit to the critical-scaling form ``pL = A (p - p_th)^nu`` by
searching ``p_th`` on a log grid (default [1e-4, 3e-2], widened from the
brief's [1e-4, 5e-3] for the reason above) and keeping the ``p_th`` whose
above-threshold points (``p > 1.05 * p_th``) give the smallest residual sum
of squares in ``log pL ~ log(p - p_th)``.  ``p`` is the ``sqgate_error`` of
the scaled model, recorded per point.

**Separability.**  A parametric bootstrap (>=200 replicates by default;
each point's error count is resampled from its binomial) yields the
distribution of ``p_th`` for each model; the difference distribution's 95%
percentile interval decides whether the two thresholds are separable.  This
comparison is *expected* to come out "not separable" for an honest reason
that is itself a result: the two parameterisations are uniform rescalings of
each other, so in absolute error-rate units they define the same circuit
family and must share a threshold -- any measured separation would be a
finite-size or grid artifact, which is exactly what the bootstrap interval
quantifies.

Caveats (also in the Markdown): ``num_rounds=2``, so every number here is a
two-round pseudo-threshold -- a finite-size estimate, not the thermodynamic
threshold of the BB family; and the scaling fit pools distances without the
``d``-dependent prefactor of true critical scaling.

Outputs: ``threshold_shift.json`` and ``threshold_shift.md``.

Run:  python experiments/threshold_shift.py [--shots N] [--quick]
"""
from __future__ import annotations

import itertools
import json
import sys
import time
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

DEFAULT_SHOTS = 4000
NUM_ROUNDS = 2
W, F = 3, 1
SEED = 7
EXTRACTOR = "zxcoloration"
NOISE_MODELS = ("SD6", "SI1000")

#: measured distance -> (l, m) for BbCode(A_x=[3], A_y=[1,2], B_x=[1,2], B_y=[3]);
#: see code_evidence() for why l=m=d in {3,5,7} is not usable.
DISTANCE_TO_LM = {2: (3, 3), 4: (3, 6), 6: (3, 9)}

#: (l, m) of the known [[72,12,6]] BB code, used only as a distance cross-check.
LITERATURE_CROSSCHECK_LM = (6, 6)

#: shared absolute grid for sqgate_error; each model is uniformly scaled onto it.
ABS_SQGATE_GRID = (4e-4, 6e-4, 8e-4, 1e-3, 1.4e-3, 2e-3, 3.5e-3, 6e-3,
                   1.2e-2, 2e-2)
QUICK_SQGATE_GRID = (1e-3, 1.2e-2)

#: p_th search grid (widened from the brief's [1e-4, 5e-3]; see module docstring).
P_TH_RANGE = (1e-4, 3e-2)
P_TH_GRID_N = 480
ABOVE_MARGIN = 1.05
MIN_ABOVE_POINTS = 4
BOOTSTRAP_REPS = 200
QUICK_BOOTSTRAP_REPS = 60
TIMING_PROBE_BUDGET_S = 90.0

#: file:line evidence into the pinned tree for the (l, m) vs distance claim.
BB_EVIDENCE = [
    "quits/qldpc_code/bb.py:30 -- construction follows arXiv:2308.07915 "
    "(the [[72,12,6]] BB code lives at l=m=6 with these polynomials)",
    "quits/qldpc_code/bb.py:36 -- self.l, self.m stored; size = l * m",
    "quits/qldpc_code/bb.py:40-60 -- A = x^3 + y + y^2, B = x + x^2 + y^3 "
    "over circulant rings of order (l, m)",
    "quits/qldpc_code/bb.py:62-63 -- hx = [A B], hz = [B^T A^T]: n = 2*l*m "
    "physical qubits",
    "quits/qldpc_code/bb.py:64 -- lz, lx = compute_lz_and_lx(hz, hx): k = "
    "len(lz) logical qubits; distance estimated as the minimum weight over "
    "the span of lz / lx",
]


# ---------------------------------------------------------------------------
# code construction (ErrorModel bypassing the NOISE_PARAMS name table)
# ---------------------------------------------------------------------------

def make_code(distance: int):
    """The BbCode instance for one measured distance."""
    import quits.qldpc_code as qc

    l, m = DISTANCE_TO_LM[distance]
    return qc.BbCode(l=l, m=m, A_x_pows=[3], A_y_pows=[1, 2],
                     B_x_pows=[1, 2], B_y_pows=[3])


def scaled_error_model(noise: str, sqgate_target: float):
    """A uniformly scaled copy of ``NOISE_PARAMS[noise]`` with the given
    ``sqgate_error``; returns (ErrorModel, scale_factor)."""
    from quits import ErrorModel

    base = Q.NOISE_PARAMS[noise]
    s = sqgate_target / base["sqgate_error"]
    scaled = {k: v * s for k, v in base.items()}
    return ErrorModel(**scaled), s


def build_point(distance: int, noise: str, sqgate_p: float) -> dict:
    """One circuit/DEM pair, mirroring ``qec_measure.build`` but with a scaled
    ErrorModel that has no entry in the ``NOISE_PARAMS`` name table."""
    code = make_code(distance)
    error_model, s = scaled_error_model(noise, sqgate_p)
    circuit = code.build_circuit(strategy=EXTRACTOR, error_model=error_model,
                                 num_rounds=NUM_ROUNDS, basis="Z")
    return {
        "spec": {"code": f"BB(l={DISTANCE_TO_LM[distance][0]},"
                         f"m={DISTANCE_TO_LM[distance][1]})",
                 "extractor": EXTRACTOR, "arch": "transversal", "noise": noise,
                 "num_rounds": NUM_ROUNDS, "sqgate_error": sqgate_p,
                 "scale_factor": s},
        "code_obj": code, "hz": code.hz, "lz": code.lz,
        "circuit": circuit,
        "dem": circuit.detector_error_model(decompose_errors=False),
        "error_model": error_model, "scale_factor": s,
    }


def measure_point(distance: int, noise: str, sqgate_p: float, shots: int,
                  seed: int = SEED) -> dict:
    """Logical error rate at one (distance, model, absolute sqgate_error)."""
    built = build_point(distance, noise, sqgate_p)
    pred = np.asarray(Q.decode(built, shots=shots, seed=seed, W=W, F=F))
    k, n = int(pred.sum()), int(pred.size)
    k_any, _ = Q.logical_failure(pred)
    rec = Q.rate_record(k, n, f"d={distance}/{noise}/p={sqgate_p:g}",
                        per_logical_qubit_rate=k / n,
                        any_observable_rate=k_any / shots)
    rec.update({
        "distance": distance, "l": DISTANCE_TO_LM[distance][0],
        "m": DISTANCE_TO_LM[distance][1], "noise": noise,
        "sqgate_error": sqgate_p, "scale_factor": built["scale_factor"],
        "n_physical": int(built["hz"].shape[1]),
        "k_logical": int(built["lz"].shape[0]),
    })
    return rec


# ---------------------------------------------------------------------------
# distance evidence
# ---------------------------------------------------------------------------

def _min_span_weight(rows: np.ndarray) -> int | None:
    """Minimum nonzero Hamming weight over the span of a logical-operator basis.

    Brute force over all 2^k - 1 combinations; only used on codes with
    k <= 16, where that is at most 65535 rows of XORs.
    """
    if rows.shape[0] == 0:
        return None
    best = None
    for r in range(1, rows.shape[0] + 1):
        for combo in itertools.combinations(range(rows.shape[0]), r):
            w = int(np.sum(np.mod(rows[list(combo), :].sum(axis=0), 2)))
            if w > 0 and (best is None or w < best):
                best = w
    return best


def _code_row(l: int, m: int) -> dict:
    import quits.qldpc_code as qc

    code = qc.BbCode(l=l, m=m, A_x_pows=[3], A_y_pows=[1, 2],
                     B_x_pows=[1, 2], B_y_pows=[3])
    return {
        "l": l, "m": m, "n_physical": int(code.hx.shape[1]),
        "k_logical": int(code.lz.shape[0]),
        "min_lz_span_weight": _min_span_weight(code.lz),
        "min_lx_span_weight": _min_span_weight(code.lx),
    }


def measure_code_evidence() -> dict:
    """Why the scan uses (l, m) = (3, 3d) with d in {2,4,6} and not l=m=d."""
    family = [{"distance": d, **_code_row(*lm)}
              for d, lm in sorted(DISTANCE_TO_LM.items())]
    cross = _code_row(*LITERATURE_CROSSCHECK_LM)
    requested = []
    for d in (3, 5, 7):  # the brief's l=m=d probe; degenerate, so unused
        row = _code_row(d, d)
        requested.append({"l": d, "m": d, "n_physical": row["n_physical"],
                          "k_logical": row["k_logical"],
                          "min_lz_span_weight": row["min_lz_span_weight"]})
    return {
        "basis": BB_EVIDENCE,
        "family": family,
        "cross_check": {
            **cross,
            "expected": "[[72,12,6]] bivariate bicycle code (arXiv:2308.07915)",
            "match": (cross["n_physical"] == 72 and cross["k_logical"] == 12
                      and cross["min_lz_span_weight"] == 6),
        },
        "requested_l_eq_m_eq_d_probe": {
            "note": ("the brief asked for BbCode(l=d, m=d) with d in {3,5,7}; "
                     "with the pinned shift polynomials that family is "
                     "degenerate (d=3 encodes k=8 at distance 2; d=5 and d=7 "
                     "encode k=0, i.e. there is no logical qubit to decode), "
                     "so the scan uses the nearest valid family (l, m) = "
                     "(3, 3d) with measured distances {2,4,6}"),
            "rows": requested,
        },
    }


# ---------------------------------------------------------------------------
# threshold fit and bootstrap
# ---------------------------------------------------------------------------

def fit_threshold(points, p_lo: float = P_TH_RANGE[0],
                  p_hi: float = P_TH_RANGE[1], grid_n: int = P_TH_GRID_N,
                  min_above: int = MIN_ABOVE_POINTS,
                  above_margin: float = ABOVE_MARGIN) -> dict:
    """Grid-search fit of ``pL = A (p - p_th)^nu`` over pooled (p, pL) points.

    For each candidate ``p_th`` the points with ``p > above_margin * p_th``
    are regressed in log space; the candidate with the smallest residual sum
    of squares wins.  ``p`` is the representative physical error rate
    (``sqgate_error``).  Returns an invalid record rather than raising when
    too few points lie above every candidate.
    """
    arr = np.asarray([(p, pl) for p, pl in points if pl > 0], dtype=float)
    if arr.shape[0] < min_above:
        return {"valid": False,
                "reason": f"only {arr.shape[0]} points with pL > 0"}
    p, pl = arr[:, 0], arr[:, 1]
    best = None
    for p_th in np.logspace(np.log10(p_lo), np.log10(p_hi), grid_n):
        above = p > above_margin * p_th
        if int(above.sum()) < min_above:
            continue
        x = np.log(p[above] - p_th)
        y = np.log(pl[above])
        nu, log_a = np.polyfit(x, y, 1)
        resid = y - (nu * x + log_a)
        rss = float(resid @ resid)
        tss = float(((y - y.mean()) ** 2).sum())
        r2 = float(1.0 - rss / tss) if tss > 0 else float("nan")
        if best is None or rss < best["rss"]:
            best = {"p_th": float(p_th), "A": float(np.exp(log_a)),
                    "nu": float(nu), "r_squared": r2, "rss": rss,
                    "n_points": int(above.sum())}
    if best is None:
        return {"valid": False,
                "reason": f"no candidate p_th has >= {min_above} points above it"}
    best["valid"] = True
    best["at_range_boundary"] = bool(
        np.isclose(best["p_th"], p_lo, rtol=1e-6)
        or np.isclose(best["p_th"], p_hi, rtol=1e-6))
    return best


def bootstrap_thresholds(rows_by_model: dict[str, list[dict]], reps: int,
                         seed: int) -> dict[str, list[float]]:
    """Parametric bootstrap: resample each point's count from its binomial
    and refit, collecting the p_th distribution per model."""
    rng = np.random.default_rng(seed)
    out: dict[str, list[float]] = {m: [] for m in rows_by_model}
    for _ in range(reps):
        for model, rows in rows_by_model.items():
            pts = []
            for r in rows:
                k = int(rng.binomial(r["shots"], r["per_logical_qubit_rate"]))
                pts.append((r["sqgate_error"], k / r["shots"]))
            fit = fit_threshold(pts)
            if fit["valid"]:
                out[model].append(fit["p_th"])
    return out


def summarize_threshold_difference(p_th_a: list[float],
                                   p_th_b: list[float],
                                   min_samples: int = 30) -> dict:
    """Difference distribution of two bootstrap p_th samples and the
    separability verdict.  Never raises on degenerate input."""
    n_a, n_b = len(p_th_a), len(p_th_b)
    if n_a < min_samples or n_b < min_samples:
        return {"valid": False, "n_boot_a": n_a, "n_boot_b": n_b,
                "p_th_a_mean": float(np.mean(p_th_a)) if n_a else None,
                "p_th_b_mean": float(np.mean(p_th_b)) if n_b else None,
                "difference_mean": None, "ci95_low": None, "ci95_high": None,
                "separable": None,
                "verdict": ("undetermined -- too few successful bootstrap "
                            "fits to compare thresholds")}
    a = np.asarray(p_th_a)
    b = np.asarray(p_th_b)
    diffs = (a[:, None] - b[None, :]).ravel()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    separable = bool(not (lo <= 0.0 <= hi))
    return {
        "valid": True, "n_boot_a": n_a, "n_boot_b": n_b,
        "p_th_a_mean": float(a.mean()), "p_th_b_mean": float(b.mean()),
        "difference_mean": float(diffs.mean()),
        "ci95_low": float(lo), "ci95_high": float(hi),
        "separable": separable,
        "verdict": ("thresholds separable at 95% (CI excludes 0)"
                    if separable else
                    "thresholds NOT separable at 95% (CI includes 0)"),
    }


# ---------------------------------------------------------------------------
# the experiment
# ---------------------------------------------------------------------------

def _timing_probe(shots: int) -> tuple[dict, list[int]]:
    """Time one full point at the largest distance; drop d=6 if it blows the
    budget (the brief's ~90 s rule, applied to our largest code)."""
    distances = sorted(DISTANCE_TO_LM)
    largest = distances[-1]
    t0 = time.perf_counter()
    rec = measure_point(largest, "SD6", 1e-3, shots, seed=SEED)
    seconds = time.perf_counter() - t0
    probe = {"distance": largest, "l": DISTANCE_TO_LM[largest][0],
             "m": DISTANCE_TO_LM[largest][1], "noise": "SD6",
             "sqgate_error": 1e-3, "shots": shots, "seconds": seconds,
             "budget_seconds": TIMING_PROBE_BUDGET_S,
             "kept": bool(seconds <= TIMING_PROBE_BUDGET_S)}
    if seconds > TIMING_PROBE_BUDGET_S and len(distances) > 2:
        distances = distances[:-1]
    return probe, distances


def run(shots: int = DEFAULT_SHOTS, quick: bool = False) -> dict:
    grid = QUICK_SQGATE_GRID if quick else ABS_SQGATE_GRID
    reps = QUICK_BOOTSTRAP_REPS if quick else BOOTSTRAP_REPS
    probe, distances = _timing_probe(shots)
    if quick:
        distances = [d for d in distances if d <= 4]

    rows = []
    for d in distances:
        for noise in NOISE_MODELS:
            for p in grid:
                rows.append(measure_point(d, noise, p, shots, seed=SEED))

    by_model = {m: [r for r in rows if r["noise"] == m] for m in NOISE_MODELS}
    fits = {m: fit_threshold([(r["sqgate_error"], r["per_logical_qubit_rate"])
                              for r in by_model[m]])
            for m in NOISE_MODELS}
    boot = bootstrap_thresholds(by_model, reps, seed=SEED + 1)
    comparison = summarize_threshold_difference(boot["SD6"], boot["SI1000"])

    return {
        "metadata": {
            "description": "distance-scan threshold fit under two noise "
                           "parameterisations (SD6 / SI1000): are the "
                           "threshold lines separable?",
            "date": date.today().isoformat(),
            "shots": shots, "num_rounds": NUM_ROUNDS, "window": W,
            "overlap": F, "sampler_seed": SEED,
            "statistics": "Wilson 95% per rate; threshold by grid-search "
                          "least squares on log pL ~ log(p - p_th); "
                          "parametric bootstrap (binomial resampling) for the "
                          "threshold difference CI",
            "decode_path": "quits.decoder.sliding_window_bposd_circuit_mem "
                           "(via qec_measure.sliding_window_from_dem, the "
                           "verified injected-DEM copy)",
            "representative_error_rate": "sqgate_error (single-qubit gate "
                                         "error of the uniformly scaled model)",
            "abs_sqgate_grid": list(grid),
            "p_th_search_range": list(P_TH_RANGE),
            "bootstrap_reps": reps,
            "timing_probe": probe,
            "quick": quick,
            "design_adjustments": [
                "l=m=d in {3,5,7} is degenerate for the pinned polynomials "
                "(k=0 for d=5,7; [[18,8,2]] for d=3); scan uses (l,m)=(3,3d), "
                "measured distances {2,4,6}; see code_evidence",
                "sweep anchored on a shared absolute sqgate_error grid (4e-4.."
                "2e-2) instead of a per-model scale factor s, because SI1000 "
                "is exactly 0.2x SD6 and threshold comparison needs absolute "
                "units; for SD6 this equals s in {0.4..20} on its baseline",
                "error-rate grid and p_th search range extended above the "
                "brief (s>2, range [1e-4,5e-3]) because a calibration probe "
                "showed the 2-round pseudo-threshold region lies above "
                "2e-3 sqgate_error (d=4/d=6 curves cross near s=12)",
            ],
        },
        "code_evidence": measure_code_evidence(),
        "points": rows,
        "threshold_fits": {m: {"model": m, **fits[m]} for m in NOISE_MODELS},
        "bootstrap": {
            "reps": reps,
            "p_th_samples": {m: boot[m] for m in NOISE_MODELS},
            "models_compared": list(NOISE_MODELS),
            "comparison_sd6_minus_si1000": comparison,
        },
        "caveat": ("num_rounds=2 throughout: the fitted p_th is a two-round "
                   "pseudo-threshold, a finite-size estimate that must not be "
                   "reported as the thermodynamic threshold of the BB family. "
                   "The fit pools distances without the d-dependent prefactor "
                   "of true critical scaling, and at the top of the grid the "
                   "windowed decoder saturates (predictions collapse toward "
                   "no-error as the syndrome becomes uninformative)."),
    }


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

def to_markdown(data: dict) -> str:
    m = data["metadata"]
    L = ["# Threshold shift under noise-model substitution", "",
         f"Generated: {m['date']}",
         f"Shots: {m['shots']} per point; rounds={m['num_rounds']}, "
         f"W={m['window']}, F={m['overlap']}, seed={m['sampler_seed']}",
         f"Representative error rate p: {m['representative_error_rate']}",
         f"p_th search range: [{m['p_th_search_range'][0]:g}, "
         f"{m['p_th_search_range'][1]:g}]; bootstrap reps: {m['bootstrap_reps']}",
         f"Statistics: {m['statistics']}", ""]

    tp = m["timing_probe"]
    L += ["## 0. Timing probe", "",
          f"Largest code d={tp['distance']} (l={tp['l']}, m={tp['m']}), "
          f"p={tp['sqgate_error']:g}, {tp['shots']} shots: "
          f"**{tp['seconds']:.1f}s** (budget {tp['budget_seconds']:.0f}s, "
          f"kept: **{tp['kept']}**).", ""]

    ev = data["code_evidence"]
    L += ["## 1. Code family and distance evidence", "",
          "The requested `BbCode(l=d, m=d)` for d in {3,5,7} is degenerate "
          "for the pinned shift polynomials, so the scan uses "
          "`(l, m) = (3, 3d)`. Measured parameters (distance = minimum weight "
          "over the span of the logical-operator basis):", "",
          "| distance d | (l, m) | n | k | min lz-span wt | min lx-span wt |",
          "|---|---|---|---|---|---|"]
    for r in ev["family"]:
        L.append(f"| {r['distance']} | ({r['l']}, {r['m']}) | {r['n_physical']} "
                 f"| {r['k_logical']} | {r['min_lz_span_weight']} "
                 f"| {r['min_lx_span_weight']} |")
    cc = ev["cross_check"]
    L += ["", f"Cross-check at (l, m) = (6, 6): n={cc['n_physical']}, "
          f"k={cc['k_logical']}, distance={cc['min_lz_span_weight']} -- "
          f"expected {cc['expected']}: **match = {cc['match']}**", "",
          "Evidence (pinned tree):", ]
    L += [f"- `{b}`" for b in ev["basis"]]
    rq = ev["requested_l_eq_m_eq_d_probe"]
    L += ["", f"Requested `l=m=d` probe: {rq['note']}", "",
          "| l=m | n | k | min lz-span wt |", "|---|---|---|---|"]
    for r in rq["rows"]:
        L.append(f"| {r['l']} | {r['n_physical']} | {r['k_logical']} "
                 f"| {r['min_lz_span_weight']} |")
    L.append("")

    L += ["## 2. Measured points", "",
          "| d | (l, m) | noise | p (sqgate) | scale s | errors / shots | "
          "per-qubit rate | Wilson 95% |", "|---|---|---|---|---|---|---|---|"]
    for r in data["points"]:
        L.append(f"| {r['distance']} | ({r['l']}, {r['m']}) | {r['noise']} "
                 f"| {r['sqgate_error']:.3g} | {r['scale_factor']:.3g} "
                 f"| {r['errors']} / {r['shots']} "
                 f"| {r['per_logical_qubit_rate']:.4f} "
                 f"| [{r['wilson95_low']:.4f}, {r['wilson95_high']:.4f}] |")
    L.append("")

    L += ["## 3. Threshold fits (pL = A (p - p_th)^nu)", "",
          "| model | p_th | A | nu | R^2 | n points | at range boundary | "
          "valid |", "|---|---|---|---|---|---|---|---|"]
    for model in data["threshold_fits"]:
        f = data["threshold_fits"][model]
        if f["valid"]:
            L.append(f"| {model} | {f['p_th']:.4g} | {f['A']:.4g} "
                     f"| {f['nu']:.3f} | {f['r_squared']:.4f} "
                     f"| {f['n_points']} | {f['at_range_boundary']} "
                     f"| {f['valid']} |")
        else:
            L.append(f"| {model} | n/a | | | | | | **{f['valid']}** "
                     f"({f.get('reason', '')}) |")
    L.append("")

    bs = data["bootstrap"]
    cp = bs["comparison_sd6_minus_si1000"]
    L += ["## 4. Threshold difference (SD6 - SI1000), parametric bootstrap",
          ""]
    if cp["valid"]:
        L += [f"- p_th(SD6)  bootstrap mean: {cp['p_th_a_mean']:.4g} "
              f"({cp['n_boot_a']}/{bs['reps']} fits valid)",
              f"- p_th(SI1000) bootstrap mean: {cp['p_th_b_mean']:.4g} "
              f"({cp['n_boot_b']}/{bs['reps']} fits valid)",
              f"- difference mean: {cp['difference_mean']:.4g}",
              f"- 95% CI of the difference: [{cp['ci95_low']:.4g}, "
              f"{cp['ci95_high']:.4g}]",
              f"- **verdict: {cp['verdict']}**", ""]
    else:
        L += [f"- **verdict: {cp['verdict']}** "
              f"({cp['n_boot_a']}/{cp['n_boot_b']} valid bootstrap fits)", ""]
    L += ["Note: SI1000 is exactly 0.2x SD6 on every noise parameter, so the "
          "two parameterisations define the same circuit family in absolute "
          "error-rate units and a genuine threshold separation is *not* "
          "expected; the interval above measures whether the finite-size fit "
          "artificially invents one.", ""]

    L += ["## 5. Caveats", "", f"{data['caveat']}", ""]
    L += ["Design adjustments from the brief, for the record:", ""]
    L += [f"- {a}" for a in m["design_adjustments"]]
    L.append("")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    target = outdir.resolve_out(argv, HERE)
    quick = "--quick" in argv
    shots = (int(argv[argv.index("--shots") + 1]) if "--shots" in argv
             else DEFAULT_SHOTS)
    if quick:
        shots = min(shots, 200)
    data = run(shots=shots, quick=quick)
    (target / "threshold_shift.json").write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8")
    (target / "threshold_shift.md").write_text(to_markdown(data),
                                               encoding="utf-8")
    print(f"threshold_shift: wrote to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
