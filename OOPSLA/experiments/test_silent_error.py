"""Regression tests for the silent-error scenarios in ``silent_error``.

These pin the two-granularity claim: stale *derived* models (DEM) can corrupt
half the individual predictions yet leave the aggregate rate untouched, while
stale *primary* artifacts (circuit, cache key without the noise coordinate)
do move the headline number.  If a future change inverts either side, the
paper's silent-error story changes with it and must be rewritten, not silently
absorbed.

Run:  python -m pytest OOPSLA/experiments/test_silent_error.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import silent_error as SE  # noqa: E402

SHOTS = 200  # enough to separate the stale-circuit rates at z >> 4


def test_stale_dem_does_not_move_aggregate_rate():
    """The negative result, asserted: a structurally different stale DEM leaves
    the reported rate inside its interval."""
    # This difference is rare. Use the recorded 9600-shot protocol so the
    # assertion tests the experiment at its measured scale.
    case = SE.experiment_stale_dem_structural(9600)
    assert case["silent_error_on_rate"] is False
    assert case["individual_fraction_changed"] > 0  # but predictions DO move


def test_stale_circuit_does_move_aggregate_rate():
    """The positive result, asserted: a stale primary circuit corrupts the
    headline number for the declared spec."""
    case = SE.experiment_stale_circuit_rounds(SHOTS)
    assert case["silent_error_on_rate"] is True
    # rate_record counts per-logical-qubit samples (shots x observables), so
    # the two sides are equal even though the underlying experiments differ
    assert case["declared"]["shots"] == case["consumed"]["shots"]


def test_every_scenario_reports_both_granularities():
    """Two-granularity discipline: prediction-level and aggregate-level numbers
    must both be present for every scenario block."""
    for case in (SE.experiment_stale_dem_structural(SHOTS),
                 SE.experiment_stale_circuit_rounds(SHOTS)):
        assert "individual_predictions_differing" in case
        assert "individual_predictions_total" in case
        assert "two_proportion_test" in case
        assert "silent_error_on_rate" in case
        assert case["individual_predictions_total"] > 0


def test_run_structure_and_definition():
    """The JSON layout the paper cites, including the silent-error definition."""
    data = SE.run(shots=50)
    assert "silent_error_definition" in data["metadata"]
    assert len(data["stale_dem_cases"]) == 4
    assert len(data["stale_circuit_cases"]) == 1
    s = data["summary"]
    assert s["n_circuit_cases_silent_on_rate"] == 1
    assert s["n_dem_cases_silent_on_rate"] == 0
    md = SE.to_markdown(data)
    assert "Two granularities" in md and "Stale circuit scenarios" in md
