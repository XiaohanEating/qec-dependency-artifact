"""Tests for the real-artifact gate (``stim_circuit_gate.py``).

The gate is the answer to "your semantic layer's artifacts are dicts -- why
should anyone care?".  These tests assert, on **real** stim circuits produced by
the pinned QUITS tree, that

* Theorem 1's conclusion (the artifacts outside ``cone(x)`` are unchanged) holds
  byte-for-byte for every (configuration, dimension) the gate ran on;
* the gate *agrees* with the published semantic verdict, row by row -- i.e. the
  toy model's verdicts transferred to real artifacts rather than merely being
  self-consistent;
* the negative controls still bite: a noise *coordinate* change is not local on
  the real circuit (H3), an inadmissible pair is refused (H1), and a non-(C4)
  substitution is refused by the checker.

Everything runs in ``--quick`` mode (2 configurations) so the suite stays fast.
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

stim_gate = pytest.importorskip(
    "stim_circuit_gate",
    reason="real-artifact gate needs the pinned QUITS tree and stim")


@pytest.fixture(scope="module")
def gate() -> dict:
    return stim_gate.run("quick", quick=True)


# ---------------------------------------------------------------------------
# the positive claim: Theorem 1 survives contact with real artifacts
# ---------------------------------------------------------------------------

def test_gate_produces_real_stim_circuits(gate):
    """The assembly layer must yield a real stim circuit, not a dict."""
    import stim
    A = stim_gate.make_stim_assembly()
    from semantics import Spec
    art = A.evaluate(Spec(code="HGP", extractor="cardinal", arch="free",
                          noise="SD6", decoder="BP-OSD"))
    assert isinstance(art["extractor"]["circuit"], stim.Circuit)
    assert art["experiment"]["kind"] == "experiment"
    assert art["experiment"]["stim_circuit_sha256"]
    assert art["experiment"]["detector_error_model_sha256"]
    # the extractor's artifact really is the circuit the DEM comes from
    assert str(art["extractor"]["circuit"].detector_error_model(flatten_loops=True))


def test_circuit_and_dem_unchanged_on_every_substitution(gate):
    """替换前后 stim circuit 文本与 DEM 文本逐字节相同（主命题）。"""
    rows = gate["rows"]
    assert rows, "the gate ran no substitutions"
    for r in rows:
        real = r["real"]
        assert real["stim_circuit_text_equal"], r["config"] + "/" + r["dim"]
        assert real["detector_error_model_text_equal"], r["config"] + "/" + r["dim"]
        assert real["all_provably_unchanged_nodes_equal"], (
            r["config"] + "/" + r["dim"])


def test_gate_agrees_with_the_published_semantic_verdict(gate):
    """语义层判定与真实 artifact 测量逐行一致。"""
    for r in gate["rows"]:
        sem, real = r["semantic"], r["real"]
        # the semantic layer says invariance_ok; the real circuit agrees
        assert sem["invariance_ok"] is True, r["config"] + "/" + r["dim"]
        assert r["gate_agrees"], r["config"] + "/" + r["dim"]
        assert sem["baseline_assembly"] == "source_faithful"
        # every node outside the cone was measured and held
        for node in sem["provably_unchanged_nodes"]:
            assert real["per_node_equal"][node], (
                r["config"] + "/" + r["dim"] + " node " + node)


def test_gate_covers_all_five_dimensions(gate):
    dims = {r["dim"] for r in gate["rows"]}
    assert dims == {"code", "extractor", "arch", "noise", "decoder"}


def test_alternative_implementations_are_documented(gate):
    """每个维度都必须说明它的 alt 实现是什么，否则 (C4) 无法审计。"""
    alts = gate["metadata"]["alt_implementations"]
    for dim in ("code", "extractor", "arch", "noise", "decoder"):
        assert alts[dim].strip(), dim
        assert len(alts[dim]) > 20, dim


# ---------------------------------------------------------------------------
# negative controls
# ---------------------------------------------------------------------------

def test_h3_noise_coordinate_change_is_not_local(gate):
    """H3, on the real artifact: changing the noise *value* changes the circuit."""
    nc = gate["probes"]["noise_coordinate_change"]
    assert nc["circuit_text_equal"] is False
    assert nc["dem_text_equal"] is False
    assert nc["circuit_sha256_before"] != nc["circuit_sha256_after"]
    assert nc["dem_sha256_before"] != nc["dem_sha256_after"]


def test_h1_inadmissible_pair_is_refused_by_both_levels(gate):
    ip = gate["probes"]["inadmissible_pair"]
    assert ip["quits_outcome"] == "refused"
    assert ip["semantic_outcome"] == "refused"
    assert ip["family_whitelist"] == ["custom", "zxcoloration"]
    assert "cardinal" in ip["global_registry_strategies"]
    assert ip["semantic_layer_refuses"] is True


def test_h1_arch_family_restriction_is_a_second_hidden_dependency(gate):
    """``arch = grid2d`` admissibility is a property of the *code* component."""
    af = gate["probes"]["arch_family_restriction"]
    results = af["results"]
    assert results["BB"]["quits_outcome"] == "assembled"
    assert results["BB"]["semantic_contract"] is True
    for family in ("HGP", "QLP"):
        assert results[family]["quits_outcome"] == "refused", family
        assert results[family]["semantic_contract"] is False, family


def test_non_c4_substitution_is_refused_by_the_checker(gate):
    n4 = gate["probes"]["non_c4_substitution"]
    assert n4["checker_applicable"] is False
    assert n4["checks"]["pointwise_equal_on_reads"] is False


# ---------------------------------------------------------------------------
# reproducibility / provenance
# ---------------------------------------------------------------------------

def test_gate_records_the_pinned_object_under_test(gate):
    m = gate["metadata"]
    assert "quits" in m["quits_file"].replace("\\", "/")
    assert m["pinned_commit"] == stim_gate.QUITS_COMMIT
    assert m["baseline_assembly"] == "source_faithful"
    # the verdicts are read from the published experiment, not recomputed here
    assert m["semantic_verdicts_from"] == "experiments/artifact_invariance.run(48)"


def test_gate_stamps_its_modelling_provenance(gate):
    src = gate["metadata"]["assembly_model_sources"]["source_faithful"]
    assert "extract_read_sets" in src["read_sets"]
    assert "ASSEMBLY_EDGES_FROM_SOURCE" in src["edges"]


def test_stim_assembly_matches_the_semantic_assembly_topology():
    """真实 assembly 与语义层 assembly 的节点/读集合/边必须一致。

    否则 gate 测的就是另一个对象，语义层的 cone 与判定都不适用。
    """
    from semantics import (ASSEMBLY_EDGES_FROM_SOURCE, COORDINATES,
                           READ_SETS_FROM_SOURCE,
                           make_source_faithful_assembly)
    real = stim_gate.make_stim_assembly()
    toy = make_source_faithful_assembly()
    assert set(real.nodes) == set(toy.nodes)
    for n in toy.nodes:
        assert real.nodes[n].reads == toy.nodes[n].reads, n
        assert real.edges[n] == toy.edges[n], n
        assert real.dependencies(n) == toy.dependencies(n), n
    for n in COORDINATES:
        assert real.nodes[n].reads == READ_SETS_FROM_SOURCE[n], n
        assert real.edges[n] == ASSEMBLY_EDGES_FROM_SOURCE[n], n


def test_gate_script_runs_and_emits_artifacts(tmp_path):
    """``main`` 必须落盘 JSON + Markdown（与其它实验一致）。

    ``--out tmp_path`` keeps the published artifact byte-identical (§3.4-D).
    """
    import json
    assert stim_gate.main(["--quick", "--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "stim_circuit_gate.json")
                      .read_text(encoding="utf-8"))
    assert data["summary"]["all_gate_agrees"] is True
    assert data["summary"]["all_circuit_text_equal"] is True
    assert data["summary"]["all_dem_text_equal"] is True
    md = (tmp_path / "stim_circuit_gate.md").read_text(encoding="utf-8")
    assert "stim circuit text" in md
    assert "gate agrees" in md.lower()
