"""Shared, validated measurement primitives for the QEC gap experiments.

Everything here exists because the first round of these experiments measured the
wrong thing, and the reasons are worth recording:

1.  **QUITS recomputes the DEM on every call.**  Every ``sliding_window_*`` entry
    point delegates to ``quits.decoder.sliding_window.spacetime``, whose first two
    lines are ``model = circuit.detector_error_model(...)`` followed by
    ``detector_error_model_to_matrix(model)``.  There is no parameter through
    which an externally cached DEM can reach the decoder.  A helper that accepted
    a ``dem`` argument and then passed only ``circuit`` onwards therefore measured
    nothing at all -- which is why the first ``stale_dem`` experiment reported a
    relative error of exactly 0.

    :func:`sliding_window_from_dem` is a faithful copy of
    ``sliding_window_circuit_mem`` in which *only* those two lines are replaced by
    a caller-supplied DEM.  ``agreement_check()`` asserts that with a fresh DEM the
    copy reproduces the official path's predictions **bitwise**, so any difference
    measured afterwards is attributable to the stale artifact and nothing else.

2.  **Two noise parameterisations of the same model are structurally identical.**
    SD6 and SI1000 both produce 144 detectors, 12 observables and the same 1152
    fault columns; only the prior vector differs (~287x between 1e-4 and 3e-2).
    BP-OSD is robust to a wrong prior at low error rates, so swapping a cached
    SD6 DEM into an SI1000 run changes no predictions.  A stale-DEM experiment
    must therefore vary something that changes the *structure*: the extractor
    schedule (zxcoloration vs custom have 3984 vs 3996 nonzeros in the same
    matrix shape) or the noise magnitude enough to saturate.

3.  **A logical error rate needs an interval.**  At the error rates in this paper
    the counts are small and the normal approximation is useless, so every rate
    reported here carries a Wilson score interval and every comparison carries a
    two-proportion z test.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402


def _evict_foreign_quits():
    """Ensure later ``import quits`` resolves to the pinned third_party tree.

    Same discipline as ``stim_circuit_gate._evict_foreign_quits``: another
    test module may already have imported the site-packages wheel into
    ``sys.modules``, and ``import quits`` would then return the cached wheel
    even though this project's PYTHONPATH points at the pinned tree.  All
    numbers produced from this module are pinned-tree numbers.
    """
    mod = sys.modules.get("quits")
    if mod is not None:
        f = (getattr(mod, "__file__", "") or "").replace("\\", "/")
        if "third_party" not in f:
            for name in [m for m in sys.modules
                         if m == "quits" or m.startswith("quits.")]:
                del sys.modules[name]


_evict_foreign_quits()

# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Used instead of the normal approximation because the observed rates here are
    often at or near 0 or 1, where the normal interval leaves [0,1].
    """
    if n <= 0:
        return (float("nan"), float("nan"))
    p = min(1.0, max(0.0, k / n))
    d = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    var = max(0.0, p * (1 - p) / n + z * z / (4 * n * n))
    half = z * math.sqrt(var) / d
    lo, hi = max(0.0, centre - half), min(1.0, centre + half)
    # exact clamps: the degenerate proportions land on the boundary and the
    # floating-point residue is not meaningful
    if k <= 0:
        lo = 0.0
    if k >= n:
        hi = 1.0
    return (lo, hi)


def two_proportion_z(k1: int, n1: int, k2: int, n2: int) -> dict:
    """Two-sided two-proportion z test.  Returns the statistic and a verdict."""
    if n1 <= 0 or n2 <= 0:
        return {"z": None, "p_value": None, "significant": None,
                "note": "empty sample"}
    p1, p2 = k1 / n1, k2 / n2
    pooled = (k1 + k2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return {"z": None, "p_value": None, "significant": p1 == p2,
                "note": "zero variance (both samples all-zero or all-one)"}
    z = (p1 - p2) / se
    p_value = math.erfc(abs(z) / math.sqrt(2))
    return {
        "rate_a": p1, "rate_b": p2,
        "absolute_difference": p1 - p2,
        "relative_difference": (p1 - p2) / p2 if p2 else None,
        "z": z, "p_value": p_value,
        "significant_at_95": p_value < 0.05,
    }


def intervals_disjoint(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[1] < b[0] or b[1] < a[0]


# ---------------------------------------------------------------------------
# the injected-DEM sliding-window decoder
# ---------------------------------------------------------------------------

def _spacetime_from_dem(dem, hz, W, F, num_cor_rounds):
    """``quits.decoder.sliding_window.spacetime`` with the DEM injected.

    Line-for-line the subject system's own implementation.  The only difference
    is that ``check_matrix / observable_matrix / priors`` come from ``dem`` instead
    of from ``circuit.detector_error_model(...)``.
    """
    from quits.decoder import detector_error_model_to_matrix

    if F == 0:
        raise ValueError("F cannot be zero")
    check_matrix, observable_matrix, priors = detector_error_model_to_matrix(dem)

    window_check_set, window_observable_set, window_priors_set, window_update = [], [], [], []
    col_min = 0
    for k in range(num_cor_rounds):
        window_check_matrix = check_matrix[k * F * hz.shape[0]:(k * F + W) * hz.shape[0], col_min:]
        if len(window_check_matrix.indptr) == 1:
            raise ValueError("no noise in one of the decoding windows")
        col_max = int(np.max(np.where(np.diff(window_check_matrix.indptr) > 0)[0]))
        window_check_matrix = window_check_matrix[:, :col_max + 1]
        window_check_set.append(window_check_matrix)

        F_correction = window_check_matrix[:F * hz.shape[0], :]
        cor_max = int(np.max(np.where(np.diff(F_correction.indptr) > 0)[0]))
        window_observable_set.append(observable_matrix[:, col_min:cor_max + 1 + col_min])
        window_priors_set.append(priors[col_min:col_max + 1 + col_min])
        window_update.append(
            check_matrix[(k + 1) * F * hz.shape[0]:((k + 1) * F + 1) * hz.shape[0],
                         col_min:cor_max + 1 + col_min])
        col_min = (cor_max + 1) + col_min

    window_check_set.append(check_matrix[F * num_cor_rounds * hz.shape[0]:, col_min:])
    window_observable_set.append(observable_matrix[:, col_min:])
    window_priors_set.append(priors[col_min:])
    return window_check_set, window_observable_set, window_priors_set, window_update


def sliding_window_from_dem(zcheck_samples, dem, hz, lz, W, F,
                            max_iter: int = 2, osd_order: int = 0,
                            bp_method: str = "product_sum",
                            schedule: str = "serial",
                            osd_method: str = "osd_cs"):
    """``sliding_window_circuit_mem`` with the DEM injected (see module docstring)."""
    from quits.decoder.bposd import BpOsdDecoder

    num_trials = zcheck_samples.shape[0]
    num_rounds = zcheck_samples.shape[1] // hz.shape[0] - 2
    if 2 + num_rounds - W >= 0:
        num_cor_rounds = (2 + num_rounds - W) // F
        if (2 + num_rounds - W) % F != 0:
            num_cor_rounds += 1
    else:
        num_cor_rounds = 0

    wcs, wos, wps, wu = _spacetime_from_dem(dem, hz, W, F, num_cor_rounds)
    kw = dict(max_iter=max_iter, bp_method=bp_method, schedule=schedule,
              osd_method=osd_method, osd_order=osd_order)
    decoders = []
    for i in range(len(wcs) - 1):
        d = dict(kw, channel_probs=wps[i])
        decoders.append(BpOsdDecoder(wcs[i], **d))
    d = dict(kw, channel_probs=wps[len(wcs) - 1])
    decoders.append(BpOsdDecoder(wcs[len(wcs) - 1], **d))

    out = np.zeros((num_trials, lz.shape[0]), dtype=int)
    for i in range(num_trials):
        acc = np.zeros(wos[0].shape[0], dtype=int)
        syn_update = np.zeros(hz.shape[0], dtype=int)
        for k in range(num_cor_rounds):
            ds = zcheck_samples[i, F * k * hz.shape[0]:(F * k + W) * hz.shape[0]].copy() % 2
            ds[:hz.shape[0]] = (ds[:hz.shape[0]] + syn_update) % 2
            de = decoders[k].decode(ds)
            acc = (acc + wos[k] @ de[:wos[k].shape[1]] % 2) % 2
            syn_update = wu[k] @ de[:wos[k].shape[1]] % 2
        ds = zcheck_samples[i, (F * num_cor_rounds) * hz.shape[0]:].copy() % 2
        ds[:hz.shape[0]] = (ds[:hz.shape[0]] + syn_update) % 2
        de = decoders[num_cor_rounds].decode(ds)
        out[i, :] = (acc + wos[num_cor_rounds] @ de % 2) % 2
    return out


def agreement_check(spec: dict, shots: int = 24, seed: int = 7) -> dict:
    """Assert the injected-DEM copy reproduces the official path bitwise.

    This is the gate that makes a stale-DEM number mean anything: if the fresh-DEM
    path is not identical to ``quits.decoder.sliding_window_bposd_circuit_mem``,
    any difference measured with a stale DEM could be an artefact of the copy.
    """
    from quits.decoder import sliding_window_bposd_circuit_mem

    c, dem, hz, lz = spec["circuit"], spec["dem"], spec["hz"], spec["lz"]
    det, _ = _sample(c, shots, seed)
    official = np.asarray(
        sliding_window_bposd_circuit_mem(det.copy(), c, hz, lz, W=3, F=1))
    mine = np.asarray(sliding_window_from_dem(det.copy(), dem, hz, lz, W=3, F=1))
    return {
        "shots": shots, "seed": seed,
        "official_ler": float(official.mean()),
        "injected_ler": float(mine.mean()),
        "bitwise_identical": bool(np.array_equal(official, mine)),
        "differing_entries": int((official != mine).sum()),
        "total_entries": int(official.size),
    }


# ---------------------------------------------------------------------------
# circuit construction / sampling
# ---------------------------------------------------------------------------

def _sample(circuit, shots, seed):
    from quits.simulation import get_stim_mem_result
    return get_stim_mem_result(circuit, shots, seed=seed)


def code_instance(family: str):
    import quits.qldpc_code as qc
    table = {
        "BB": ("BbCode", dict(l=6, m=6, A_x_pows=[3], A_y_pows=[1, 2],
                              B_x_pows=[1, 2], B_y_pows=[3])),
        "HGP": ("HgpCode", dict(h1=np.array([[1, 1, 0], [0, 1, 1]]),
                                h2=np.array([[1, 1, 0], [0, 1, 1]]))),
        "QLP": ("QlpCode", dict(b1=np.array([[0, 0], [0, 3]]),
                                b2=np.array([[0, 1, 0], [1, 0, 3]]),
                                lift_size=12)),
    }
    cls, kwargs = table[family]
    return getattr(qc, cls)(**kwargs)


NOISE_PARAMS = {
    "SD6":       dict(idle_error=1e-4, sqgate_error=1e-3, tqgate_error=1e-3, spam_error=1e-3),
    "SI1000":    dict(idle_error=2e-5, sqgate_error=2e-4, tqgate_error=2e-4, spam_error=2e-4),
    "SD6-10x":   dict(idle_error=3e-3, sqgate_error=3e-2, tqgate_error=3e-2, spam_error=3e-2),
    "SD6-0.1x":  dict(idle_error=1e-5, sqgate_error=1e-4, tqgate_error=1e-4, spam_error=1e-4),
}


def build(code: str, extractor: str, noise: str, arch: str = "transversal",
          num_rounds: int = 2):
    """One QUITS pipeline run, returning the code, circuit and DEM.

    ``dem`` uses ``decompose_errors=False`` because that is exactly what
    ``quits.decoder.sliding_window.spacetime`` uses; any other form gives a
    different column count and is not the artifact the decoder actually consumes.
    """
    from quits import ErrorModel

    obj = code_instance(code)
    error_model = ErrorModel(**NOISE_PARAMS[noise])
    circuit = obj.build_circuit(strategy=extractor, error_model=error_model,
                                num_rounds=num_rounds, basis="Z")
    return {
        "spec": {"code": code, "extractor": extractor, "arch": arch,
                 "noise": noise, "num_rounds": num_rounds},
        "code_obj": obj, "hz": obj.hz, "lz": obj.lz,
        "circuit": circuit, "dem": circuit.detector_error_model(decompose_errors=False),
        "error_model": error_model,
    }


def dem_shape(dem):
    from quits.decoder import detector_error_model_to_matrix
    H, O, P = detector_error_model_to_matrix(dem)
    return {"num_detectors": dem.num_detectors,
            "num_observables": dem.num_observables,
            "matrix_shape": list(H.shape),
            "check_matrix_nonzeros": int(H.nnz),
            "observable_matrix_nonzeros": int(O.nnz),
            "mean_prior": float(P.mean())}


def decode(build_result, dem=None, shots: int = 500, seed: int = 7,
           W: int = 3, F: int = 1) -> np.ndarray:
    """Decode ``shots`` samples of the built circuit using ``dem``.

    ``dem=None`` means "the fresh DEM", i.e. what the official path uses.  Passing
    a different object is how a stale artifact is injected.
    """
    det, _ = _sample(build_result["circuit"], shots, seed)
    use = build_result["dem"] if dem is None else dem
    return np.asarray(sliding_window_from_dem(det.copy(), use, build_result["hz"],
                                              build_result["lz"], W=W, F=F))


def logical_failure(pred: np.ndarray) -> tuple[int, int]:
    """Count shots in which any logical observable was predicted to flip."""
    arr = np.asarray(pred)
    return int(np.any(arr != 0, axis=1).sum()), int(arr.shape[0])


def rate_record(k: int, n: int, label: str, **extra) -> dict:
    lo, hi = wilson(k, n)
    return {"label": label, "errors": k, "shots": n, "rate": k / n if n else None,
            "wilson95_low": lo, "wilson95_high": hi, **extra}