"""Tests for experiments/external_substitutions.py.

Run:  python -m pytest experiments/test_external_substitutions.py -q
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

import ldpc  # noqa: E402, F401  (MUST precede any beliefmatching import:
             # ldpc's __init__ back-imports beliefmatching; reversed order
             # is a circular import)

import qec_measure as Q  # noqa: E402
import external_substitutions as X  # noqa: E402


# ---------------------------------------------------------------------------
# pure-formula unit tests (hand-computed examples)
# ---------------------------------------------------------------------------

def test_per_logical_bit_normalisation_hand_computed():
    # k_any = 40 failures in n = 1000 shots, k_logical = 12 (BB):
    # raw rate 0.04; normalised rate 0.04/12 = 0.00333...
    rec = X.per_logical_bit_record(40, 1000, 12, "t")
    assert rec["raw_ler"] == 0.04
    assert abs(rec["per_logical_bit_rate"] - 0.04 / 12) < 1e-12
    # Wilson(40, 1000): centre/half scaled by 1/12 (delta-method)
    lo, hi = Q.wilson(40, 1000)
    centre, half = (lo + hi) / 2, (hi - lo) / 2
    nlo, nhi = rec["per_logical_bit_wilson95"]
    assert abs(nlo - (centre - half) / 12) < 1e-12
    assert abs(nhi - (centre + half) / 12) < 1e-12
    # the scaled interval still brackets the scaled point estimate (loose,
    # because the Wilson centre is shifted, but must hold for n >> z^2)
    assert nlo < rec["per_logical_bit_rate"] < nhi
    assert "delta-method" in rec["normalisation"]


def test_per_logical_bit_k1_is_identity():
    # k_logical = 1 (HGP): normalised scale must equal the raw scale
    rec = X.per_logical_bit_record(7, 100, 1, "t")
    assert rec["per_logical_bit_rate"] == rec["raw_ler"]
    assert rec["per_logical_bit_wilson95"] == list(Q.wilson(7, 100))


def test_minimum_detectable_effect_hand_computed():
    # MDE = 1.959964 * sqrt(2 * 0.128 * 0.872 / 576000)
    # 2 * 0.128 * 0.872 = 0.223232; / 576000 = 3.87556e-07
    # sqrt = 6.22539e-04; * 1.959964 = 1.22020e-03
    mde = X.minimum_detectable_effect(0.128, 576000)
    assert abs(mde - 1.2202e-3) < 1e-6


def test_minimum_detectable_effect_zero_pooled():
    # p = 0 -> zero variance -> MDE 0
    assert X.minimum_detectable_effect(0.0, 1000) == 0.0


def test_discordant_counts():
    a = np.array([1, 1, 0, 0, 1, 0])
    b = np.array([0, 1, 0, 1, 1, 0])
    c = X.discordant_counts(a, b)
    assert c["a_fail_b_pass"] == 1   # shot 0
    assert c["a_pass_b_fail"] == 1   # shot 3
    assert c["both_fail"] == 2       # shots 1, 4
    assert c["both_pass"] == 2       # shots 2, 5
    assert c["discordant_total"] == 2
    assert c["n_shots"] == 6


# ---------------------------------------------------------------------------
# structural test on a quick run
# ---------------------------------------------------------------------------

def test_quick_run_structure(tmp_path=None):
    data = X.run(shots_decoder=24, shots_family=40, shots_power=60)

    # top level: metadata + four experiment blocks
    for key in ("metadata", "decoder_external", "decoder_external_beliefmatching",
                "code_family_normalized", "extractor_power"):
        assert key in data, key
    md = data["metadata"]
    for key in ("date", "shots_decoder", "shots_family", "shots_power",
                "statistics", "agreement_check", "pymatching_version",
                "beliefmatching_version", "beliefmatching_import_order"):
        assert key in md, key
    assert md["agreement_check"]["bitwise_identical"] is True

    # serialisable as the JSON dump will do
    json.dumps(data, default=str)

    # -- decoder_external -----------------------------------------------------
    ext = data["decoder_external"]
    assert {r["noise"] for r in ext["runs"]} == {"SD6", "SI1000"}
    for r in ext["runs"]:
        d = r["direct_pymatching"]
        # the artifact is hypergraph-dominated: fragment keeps a strict
        # minority of the probability mass
        assert d["fraction_of_mass_graphlike"] < 0.5
        # and no observable-carrying mechanism survives into the fragment
        assert d["graphlike_observable_carrying_instructions"] == 0
        # pairing fields the paper reports
        pc = r["paired_comparison"]
        assert pc["discordant_pairs"]["n_shots"] == r["samples"]["shots"]
        assert 0.0 <= pc["entry_agreement"] <= 1.0
        assert "two_proportion_test_any_observable" in pc
        assert r["fragment_graph"]["zero_syndrome_decodes_to_zero"] is True
        # fragment path is logically blind -> identically zero predictions
        assert r["pymatching_fragment_path"]["rate"] == 0.0
        # alignment is recorded
        assert "observable_axis" in r["alignment"]

    # -- decoder_external_beliefmatching --------------------------------------
    bm_ext = data["decoder_external_beliefmatching"]
    assert "import_order_requirement" in bm_ext
    assert {r["noise"] for r in bm_ext["runs"]} == {"SD6", "SI1000"}
    for r in bm_ext["runs"]:
        dec = r["decodability"]
        n = r["samples"]["shots"]
        # the heterogeneous decoder must decode the hypergraph DEM that
        # pymatching cannot -- allow for the rare MWPM-fallback crash
        assert dec["decoded_shots"] + dec["fallback_crashes"] == n
        assert dec["decoded_shots"] >= 0.9 * n
        assert dec["zero_syndrome_decodes_to_zero"] is True
        pc = r["paired_comparison"]
        assert 0.9 < pc["per_shot_agreement"] <= 1.0
        dp = pc["discordant_pairs"]
        assert dp["n_shots"] == dec["decoded_shots"]
        assert dp["discordant_total"] == (dp["a_fail_b_pass"]
                                          + dp["a_pass_b_fail"])
        assert "two_proportion_test_any_observable" in pc
        assert "observable_axis" in r["alignment"]
        # strict rate (decoder failures counted) is at least the decoded rate
        bp = r["beliefmatching_path"]
        assert (bp["strict_any_observable_rate"]
                >= bp["any_observable_rate"])

    # -- code_family_normalized ----------------------------------------------
    fam = data["code_family_normalized"]
    by_label = {r["label"].split("/")[0]: r for r in fam["families"]}
    assert set(by_label) == {"BB", "HGP", "QLP"}
    # logical-qubit counts of the subject's three families
    assert by_label["BB"]["k_logical"] == 12
    assert by_label["HGP"]["k_logical"] == 1
    assert by_label["QLP"]["k_logical"] == 5
    for r in fam["families"]:
        # per-logical-bit rate equals raw rate / k_logical on this scale
        assert abs(r["per_logical_bit_rate"] - r["raw_ler"] / r["k_logical"]) < 1e-12
        nlo, nhi = r["per_logical_bit_wilson95"]
        assert 0.0 <= nlo <= nhi <= 1.0
        assert "delta-method" in r["normalisation"]

    # -- extractor_power ------------------------------------------------------
    pw = data["extractor_power"]
    assert pw["shots"] == 60
    p = pw["power"]
    # MDE formula consistency against the module helper
    assert abs(p["mde_at_this_n"]
               - X.minimum_detectable_effect(p["pooled_rate"],
                                             p["n_trials_per_arm"])) < 1e-15
    assert p["observed_absolute_difference"] >= 0.0
    # the two-proportion z fields exist and are self-consistent
    t = pw["two_proportion_test_per_bit"]
    assert 0.0 <= t["p_value"] <= 1.0
    if t["z"] is not None:
        n = pw["zxcoloration"]["shots"]
        p1, p2 = t["rate_a"], t["rate_b"]
        pooled_p = (pw["zxcoloration"]["errors"] + pw["custom"]["errors"]) / (
            pw["zxcoloration"]["shots"] + pw["custom"]["shots"])
        se = math.sqrt(pooled_p * (1 - pooled_p) * (2 / n))
        assert abs(t["z"] - (p1 - p2) / se) < 1e-9
    assert "significant_at_95" in t


def test_markdown_renders():
    data = X.run(shots_decoder=24, shots_family=40, shots_power=60)
    md = X.to_markdown(data)
    assert "# External substitutions" in md
    assert "PyMatching" in md
    assert "BeliefMatching" in md
    assert "| `BB` |" in md
    assert "MDE" in md
