"""Tests for subject 2's two upgrades (``subject2_read_sets.py`` and
``subject2_artifact_gate.py``).

The modelling layer of subject 2 (``subject2_qecc.py``) was hand-annotated;
these tests pin the two claims that remove the "toy table" attack surface:

* **AST extraction** finds at least the two hidden reads the hand model
  labelled faithful-but-wrong (``succ_probs`` -> ``probs``,
  ``idle`` -> ``idle_error``), and reports the aggregate-visibility layer
  difference on ``sr_lr_split``;
* **the real-artifact gate** runs the pinned qecc_routing pipeline and
  asserts, on its real products:
    (a) a code-spec change moves Hz / lattice / succ_probs / the circuit;
    (b) a noise-ONLY change moves the products of the components that
        declare only ``{code}`` -- the hidden dependency evidenced on real
        artifacts (max|Δ| > 0, idle DEPOLARIZE1 probability changes);
    (c) the faithful components' products are byte-identical under that
        same noise change (invariance positive control);
  plus an independent-baseline reproducibility check (same sha256 twice).

Everything runs in ``--quick`` mode and needs no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_OOPSLA = _HERE.parent
for _p in (str(_OOPSLA / "src"), str(_OOPSLA), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

read_sets = pytest.importorskip(
    "subject2_read_sets",
    reason="AST read-set extraction needs the pinned qecc_routing tree")
gate = pytest.importorskip(
    "subject2_artifact_gate",
    reason="the real-artifact gate needs stim/galois/ldpc and the pinned tree")


@pytest.fixture(scope="module")
def rs() -> dict:
    return read_sets.collect()


@pytest.fixture(scope="module")
def g() -> dict:
    return gate.run(quick=True)


# ---------------------------------------------------------------------------
# deliverable 1: AST read-set extraction vs the hand model
# ---------------------------------------------------------------------------

def test_ast_finds_at_least_the_two_hand_labelled_hidden_reads(rs):
    """AST extraction must detect >= the 2 faithful-but-wrong hidden reads."""
    s = rs["summary"]
    assert len(s["hidden_reads_detected_by_ast"]) >= 2
    assert s["covers_all_hand_labelled_hidden_reads"] is True
    assert {"succ_probs", "idle"} <= set(s["hidden_reads_detected_by_ast"])


def test_ast_hidden_read_evidence_points_at_the_noise_globals(rs):
    """The evidence lines must be the pinned source sites, not a guess."""
    by_name = {r["component"]: r for r in rs["components"]}
    idle_ev = " ".join(by_name["idle"]["evidence"]["coordinate"])
    assert "idle_error" in idle_ev and "general.py:414" in idle_ev
    succ_ev = " ".join(by_name["succ_probs"]["evidence"]["coordinate"])
    assert "probs" in succ_ev and "general.py:253" in succ_ev


def test_ast_reports_the_circuit_muls001_read_the_hand_model_missed(rs):
    """A third hidden noise read (circuit <- muls001) is found and flagged."""
    s = rs["summary"]
    assert "circuit" in s["hidden_reads_the_hand_model_missed"]


def test_sr_lr_split_aggregate_is_reported_as_a_layer_difference(rs):
    by_name = {r["component"]: r for r in rs["components"]}
    row = by_name["sr_lr_split"]
    assert row["verdict"] == "aggregate_visible_at_file_level"
    assert "min" in row["explanation"] and "std" in row["explanation"]
    assert "geometry" in row["ast_artifact_reads"]   # x_rs / z_rs read


def test_every_component_is_accounted_for(rs):
    s = rs["summary"]
    assert s["n_components"] == 11
    assert s["n_agreements"] + s["n_disagreements"] == 11
    for r in rs["components"]:
        assert r["verdict"] != "partial_disagreement", r["component"]


# ---------------------------------------------------------------------------
# deliverable 2: the real-artifact gate
# ---------------------------------------------------------------------------

def test_gate_runs_the_real_pipeline_and_is_reproducible(g):
    assert g["reproducibility"]["all_identical"] is True
    base = g["variants"]["baseline"]["artifacts"]
    assert base["Hz"]["shape"] == [45, 90]           # 9x5 bivariate bicycle
    assert base["circuit"]["num_measurements"] > 0
    assert base["circuit"]["num_detectors"] > 0


def test_control_a_code_change_moves_every_real_artifact(g):
    cmp_ = g["controls"]["code_change"]
    assert cmp_["verdict_pass"] is True
    for key in ("Hz", "lattice", "succ_probs_x", "circuit"):
        assert cmp_["comparisons"][key]["changed"] is True, key


def test_control_b_noise_only_change_moves_hidden_products(g):
    """钉死：只改噪声，声明 {code} 的组件的真实产物必须变（H3 反向对照）。"""
    cmp_ = g["controls"]["noise_only_hidden_read"]
    assert cmp_["verdict_pass"] is True
    n = cmp_["comparisons"]
    for key in ("succ_probs_x", "succ_probs_z"):
        assert n[key]["changed"] is True, key
        assert n[key]["max_abs_delta"] > 0, key
    assert n["depolarize1_probs"]["changed"] is True   # the idle rate
    assert n["circuit"]["changed"] is True


def test_control_c_faithful_products_invariant_under_noise_change(g):
    inv = g["controls"]["faithful_invariance"]
    assert inv["verdict_pass"] is True
    for key, row in inv["unchanged_artifacts"].items():
        assert row["held"] is True, key


def test_gate_summary_all_pass(g):
    assert g["summary"]["all_pass"] is True
