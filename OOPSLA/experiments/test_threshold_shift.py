"""Tests for the threshold-shift experiment (``threshold_shift.py``).

Fast by construction: shots <= 200, quick mode, and the fit/verdict logic is
exercised on synthetic data where the answer is known.

* ``test_fit_recovers_known_threshold`` -- the grid-search fit must recover a
  synthetic p_th, A and nu within tolerance, or every measured threshold is
  meaningless.
* ``test_quick_pipeline_structure`` -- ``main(["--quick", ...])`` must
  produce the full JSON/Markdown contract: metadata fields, one row per
  (distance, model, grid point), Wilson interval on every row, fit and
  bootstrap blocks, and a verdict that does not crash on quick-mode data.
* ``test_verdict_not_separable_no_crash`` / ``test_verdict_undetermined`` --
  the separability verdict must report "not separable" (not raise) when the
  bootstrap distributions overlap, and "undetermined" (not raise) when too
  few bootstrap fits succeed.

Run:  python -m pytest OOPSLA/experiments/test_threshold_shift.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

import threshold_shift as TS  # noqa: E402


# ---------------------------------------------------------------------------
# the fit
# ---------------------------------------------------------------------------

def test_fit_recovers_known_threshold():
    """Synthetic data with a known p_th must be recovered by the grid search."""
    rng = np.random.default_rng(7)
    p_th_true, A_true, nu_true = 2e-3, 0.5, 1.5
    p = np.logspace(np.log10(2.4e-3), np.log10(2e-2), 16)
    pl = A_true * (p - p_th_true) ** nu_true
    pl = pl * (1.0 + 0.01 * rng.standard_normal(pl.shape))
    fit = TS.fit_threshold(list(zip(p, pl)))
    assert fit["valid"], f"fit failed: {fit}"
    assert abs(fit["p_th"] - p_th_true) < 2.5e-4, (
        f"p_th off the synthetic truth: {fit['p_th']} vs {p_th_true}")
    assert abs(fit["nu"] - nu_true) / nu_true < 0.20, (
        f"nu off: {fit['nu']} vs {nu_true}")
    assert abs(fit["A"] - A_true) / A_true < 0.60, (
        f"A off: {fit['A']} vs {A_true}")
    assert fit["r_squared"] > 0.99


def test_fit_invalid_when_too_few_points():
    """Degenerate input must return an invalid record, not raise."""
    fit = TS.fit_threshold([(1e-3, 0.1)])
    assert not fit["valid"]
    fit = TS.fit_threshold([(p, 0.05) for p in (1e-3, 2e-3)])
    assert not fit["valid"]


# ---------------------------------------------------------------------------
# the quick pipeline end to end
# ---------------------------------------------------------------------------

def test_quick_pipeline_structure(tmp_path):
    rc = TS.main(["--quick", "--out", str(tmp_path)])
    assert rc == 0
    data = json.loads((tmp_path / "threshold_shift.json").read_text(
        encoding="utf-8"))
    md = (tmp_path / "threshold_shift.md").read_text(encoding="utf-8")

    md_meta = data["metadata"]
    for key in ("description", "date", "shots", "statistics", "decode_path",
                "representative_error_rate", "timing_probe"):
        assert key in md_meta, f"metadata missing {key}"
    assert md_meta["shots"] <= 200
    assert md_meta["quick"] is True

    # quick mode: distances {2,4} x 2 models x 2 grid points = 8 rows
    rows = data["points"]
    assert len(rows) == 8
    distances = {r["distance"] for r in rows}
    assert distances == {2, 4}
    for r in rows:
        assert {"distance", "noise", "sqgate_error", "errors", "shots",
                "wilson95_low", "wilson95_high",
                "per_logical_qubit_rate"} <= set(r)
        lo, hi = r["wilson95_low"], r["wilson95_high"]
        assert 0.0 <= lo <= r["per_logical_qubit_rate"] <= hi <= 1.0

    # fit and bootstrap blocks exist and carry a verdict string
    for model in ("SD6", "SI1000"):
        assert model in data["threshold_fits"]
    cp = data["bootstrap"]["comparison_sd6_minus_si1000"]
    assert isinstance(cp["verdict"], str) and cp["verdict"]
    assert "caveat" in data

    # markdown carries the required tables and the caveat
    for section in ("Measured points", "Threshold fits",
                    "Threshold difference", "Caveats"):
        assert section in md


# ---------------------------------------------------------------------------
# the separability verdict
# ---------------------------------------------------------------------------

def test_verdict_not_separable_no_crash():
    """Overlapping bootstrap distributions -> CI includes 0, no exception."""
    rng = np.random.default_rng(11)
    a = rng.normal(2.0e-3, 2.0e-4, 300)
    b = rng.normal(2.05e-3, 2.0e-4, 300)
    cp = TS.summarize_threshold_difference(list(a), list(b))
    assert cp["valid"]
    assert cp["separable"] is False
    assert cp["ci95_low"] <= 0.0 <= cp["ci95_high"]
    assert "NOT separable" in cp["verdict"]


def test_verdict_separable_when_distributions_are_apart():
    rng = np.random.default_rng(13)
    a = rng.normal(3.0e-3, 1.0e-4, 300)
    b = rng.normal(1.5e-3, 1.0e-4, 300)
    cp = TS.summarize_threshold_difference(list(a), list(b))
    assert cp["valid"]
    assert cp["separable"] is True
    assert cp["ci95_low"] > 0.0


def test_verdict_undetermined_on_degenerate_input():
    cp = TS.summarize_threshold_difference([], [1e-3] * 50)
    assert not cp["valid"]
    assert cp["separable"] is None
    cp = TS.summarize_threshold_difference([], [])
    assert not cp["valid"]
