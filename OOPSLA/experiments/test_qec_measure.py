"""Regression tests for the measurement primitives in ``qec_measure``.

These exist because the first round of the gap experiments measured the wrong
thing and nothing failed: a helper accepted a ``dem`` argument, never used it, and
reported a relative error of exactly 0.  The tests below pin down the three
properties that make a number from this module trustworthy.

* ``test_injected_dem_reproduces_official_path_bitwise`` -- the injected-DEM
  sliding-window copy must agree with
  ``quits.decoder.sliding_window_bposd_circuit_mem`` on every prediction when
  given a fresh DEM.  If this fails, any stale-DEM difference could be an
  artefact of the copy rather than of the stale DEM.
* ``test_same_structure_different_extractor`` -- pins the fact that the two
  extraction schedules agree on detector and observable counts while differing in
  the nonzero pattern, which is what makes the structural stale-DEM case worth
  running.
* ``test_stale_dem_does_not_move_the_rate`` -- the negative result, asserted so a
  future change that breaks it is noticed.
* ``test_two_proportion_detects_a_real_difference`` and the Wilson interval
  properties -- the statistics are only useful if they are calibrated, so a case
  that must be detected and a case that must not are both checked.

Run:  python -m pytest OOPSLA/experiments/test_qec_measure.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

import qec_measure as Q  # noqa: E402


# ---------------------------------------------------------------------------
# the decoder path
# ---------------------------------------------------------------------------

def test_injected_dem_reproduces_official_path_bitwise():
    """The stale-DEM harness must be faithful before any stale-DEM number means
    anything."""
    built = Q.build("BB", "zxcoloration", "SD6", num_rounds=2)
    check = Q.agreement_check(built, shots=16, seed=7)
    assert check["bitwise_identical"], (
        f"injected-DEM copy diverges from the official path: "
        f"{check['differing_entries']}/{check['total_entries']} entries differ")
    assert check["differing_entries"] == 0


def test_agreement_check_is_not_vacuous():
    """agreement_check must actually compare two decode paths, not short-circuit."""
    built = Q.build("BB", "zxcoloration", "SD6", num_rounds=2)
    check = Q.agreement_check(built, shots=16, seed=7)
    assert check["total_entries"] > 0
    assert check["official_ler"] == check["injected_ler"]


# ---------------------------------------------------------------------------
# DEM structure
# ---------------------------------------------------------------------------

def test_same_structure_different_extractor():
    """zxcoloration and custom agree on shape but differ in the nonzero pattern."""
    zx = Q.dem_shape(Q.build("BB", "zxcoloration", "SD6")["dem"])
    cu = Q.dem_shape(Q.build("BB", "custom", "SD6")["dem"])
    assert zx["num_detectors"] == cu["num_detectors"]
    assert zx["num_observables"] == cu["num_observables"]
    assert zx["matrix_shape"] == cu["matrix_shape"]
    assert (zx["check_matrix_nonzeros"]
            != cu["check_matrix_nonzeros"]), (
        "the two extraction schedules are expected to produce different "
        "detector error matrices; if they no longer do, the structural "
        "stale-DEM experiment has lost its premise")


def test_noise_parameterisations_share_structure():
    """SD6 and SI1000 differ only in priors -- this is why a prior-only stale
    DEM is a weak perturbation, and the experiment says so."""
    sd6 = Q.dem_shape(Q.build("BB", "zxcoloration", "SD6")["dem"])
    si = Q.dem_shape(Q.build("BB", "zxcoloration", "SI1000")["dem"])
    assert sd6["num_detectors"] == si["num_detectors"]
    assert sd6["matrix_shape"] == si["matrix_shape"]
    assert sd6["check_matrix_nonzeros"] == si["check_matrix_nonzeros"]
    assert sd6["mean_prior"] != si["mean_prior"]


def test_dem_uses_decompose_errors_false():
    """The injected DEM must be the same artifact the official decoder builds.

    ``spacetime`` calls ``detector_error_model(decompose_errors=False)``; any
    other form yields a different column count and is not the artifact under
    discussion.
    """
    import stim
    from quits import ErrorModel
    import quits.qldpc_code as qc

    obj = qc.BbCode(l=6, m=6, A_x_pows=[3], A_y_pows=[1, 2],
                    B_x_pows=[1, 2], B_y_pows=[3])
    circuit = obj.build_circuit(
        strategy="zxcoloration", error_model=ErrorModel(**Q.NOISE_PARAMS["SD6"]),
        num_rounds=2, basis="Z")
    built = Q.build("BB", "zxcoloration", "SD6", num_rounds=2)
    assert isinstance(built["dem"], stim.DetectorErrorModel)
    assert (built["dem"].num_detectors
            == circuit.detector_error_model(decompose_errors=False).num_detectors)


# ---------------------------------------------------------------------------
# the negative result, asserted
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label,base_kwargs,stale_kwargs,rounds", [
    ("structural", dict(extractor="zxcoloration", noise="SD6"),
     dict(extractor="custom", noise="SD6"), 2),
    ("prior_only", dict(extractor="zxcoloration", noise="SI1000"),
     dict(extractor="zxcoloration", noise="SD6"), 2),
])
def test_stale_dem_does_not_move_the_rate(label, base_kwargs, stale_kwargs,
                                          rounds):
    """A stale DEM does not move the aggregate rate. Pinned deliberately.

    This is the paper's negative result.  If a future change makes the rate
    separable, the negative result no longer holds and the claim must be revised,
    so the assertion is written to fail loudly rather than to document a range.
    """
    built = Q.build("BB", base_kwargs["extractor"], base_kwargs["noise"],
                    num_rounds=rounds)
    stale = Q.build("BB", stale_kwargs["extractor"], stale_kwargs["noise"],
                    num_rounds=rounds)["dem"]
    fresh = Q.decode(built, dem=None, shots=1200, seed=7)
    stale_pred = Q.decode(built, dem=stale, shots=1200, seed=7)
    import numpy as np
    kf, nf = int(np.asarray(fresh).sum()), np.asarray(fresh).size
    ks, ns = int(np.asarray(stale_pred).sum()), np.asarray(stale_pred).size
    test = Q.two_proportion_z(kf, nf, ks, ns)
    assert not test["significant_at_95"], (
        f"{label}: stale DEM now moves the rate (z={test['z']:.3f}, "
        f"p={test['p_value']:.3g}); the negative result needs restating")
    # Equivalence margin, not just a significance assertion: a small-sample
    # significance test is inherently fragile for a negative result (an
    # unseeded tie-break in the ldpc decoder drifts the point estimate between
    # runs), so the observed absolute difference is also pinned against the
    # preregistered equivalence margin of 0.02.
    observed_diff = abs(kf / nf - ks / ns)
    assert observed_diff < 0.02, (
        f"{label}: stale DEM shifts the rate by {observed_diff:.4f}, outside "
        f"the preregistered equivalence margin of 0.02")


# ---------------------------------------------------------------------------
# statistics calibration
# ---------------------------------------------------------------------------

def test_two_proportion_detects_a_real_difference():
    """A large true difference must be reported as significant."""
    test = Q.two_proportion_z(500, 1000, 50, 1000)
    assert test["significant_at_95"]
    assert test["z"] > 5


def test_two_proportion_rejects_a_tiny_difference():
    """A difference inside the noise must not be reported as significant."""
    test = Q.two_proportion_z(137, 1000, 143, 1000)
    assert not test["significant_at_95"]


def test_two_proportion_handles_degenerate_samples():
    """An all-zero sample must not raise (the previous version overflowed)."""
    for args in ((0, 100, 0, 100), (100, 100, 100, 100), (0, 0, 0, 0)):
        out = Q.two_proportion_z(*args)
        assert "z" in out and "p_value" in out


def test_wilson_interval_properties():
    lo, hi = Q.wilson(50, 100)
    assert 0.0 <= lo < 0.5 < hi <= 1.0
    # degenerate counts stay inside [0, 1]
    assert Q.wilson(0, 100)[0] == 0.0
    assert Q.wilson(100, 100)[1] == 1.0
    assert Q.wilson(0, 0)[0] != Q.wilson(0, 0)[0]  # nan: x != x


def test_wilson_interval_narrows_with_more_shots():
    narrow = Q.wilson(500, 1000)
    wide = Q.wilson(50, 100)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_intervals_disjoint():
    a = Q.wilson(50, 1000)     # ~0.05
    b = Q.wilson(200, 1000)    # ~0.20
    assert Q.intervals_disjoint(a, b)
    assert not Q.intervals_disjoint(Q.wilson(500, 1000), Q.wilson(520, 1000))