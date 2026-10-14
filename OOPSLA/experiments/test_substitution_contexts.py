"""Regression cases for reachable-input equality and structural impact."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from semantics import (
    Assembly, Component, Spec, artifact_equal, behavior_change_report,
    context_independence, pointwise_equal_on_reads, theorem1_report,
)

DOMAIN = {"code": ["BB", "HGP"], "extractor": ["cardinal"],
          "arch": ["free"], "noise": ["SD6"], "decoder": ["BP-OSD"]}


def test_array_artifact_equality_rejects_broadcasting_and_dtype_changes():
    import numpy as np
    assert not artifact_equal(np.ones((1, 2)), np.ones((2, 2)))
    assert not artifact_equal(np.ones((2,), dtype=np.int32),
                              np.ones((2,), dtype=np.float64))
    assert artifact_equal(np.ones((1, 2)), np.ones((1, 2)))


def fixture_assembly():
    upstream = Component("code", ("code",), lambda s, inp: s.code)
    target = Component("decoder", ("decoder",), lambda s, inp: inp["code"])
    sink = Component("sink", (), lambda s, inp: inp["decoder"])
    independent = Component("independent", (), lambda s, inp: "stable")
    return Assembly({"code": upstream, "decoder": target, "sink": sink,
                     "independent": independent},
                    {"code": (), "decoder": ("code",), "sink": ("decoder",)})


def test_c4_rejects_replacement_differing_only_on_nondefault_predecessor():
    assembly = fixture_assembly()
    replacement = Component("decoder", ("decoder",), lambda s, inp:
                            inp["code"] if inp["code"] == "BB" else "CHANGED")
    report = theorem1_report(assembly, "decoder", replacement, DOMAIN)
    assert report["checks"]["x_context_independent"]
    assert report["checks"]["x_prime_context_independent"]
    assert not report["checks"]["pointwise_equal_on_reads"]
    assert not report["applicable"]
    assert not report["all_nodes_provably_unchanged"]


def test_exact_reachable_replacement_preserves_all_outputs_including_descendants():
    assembly = fixture_assembly()
    replacement = Component("decoder", ("decoder",),
                            lambda s, inp: str(inp["code"]))
    report = theorem1_report(assembly, "decoder", replacement, DOMAIN)
    assert report["applicable"]
    assert set(report["all_nodes_provably_unchanged"]) == set(assembly.nodes)
    assert report["necessary_output_reruns"] == []
    changed = Assembly({**assembly.nodes, "decoder": replacement}, assembly.edges)
    for family in DOMAIN["code"]:
        spec = Spec(code=family)
        assert assembly.evaluate(spec) == changed.evaluate(spec)


def test_behavior_change_impact_includes_target_and_excludes_independent_nodes():
    assembly = fixture_assembly()
    report = behavior_change_report(assembly, "decoder")
    assert report["potentially_changed_nodes"] == ["decoder", "sink"]
    assert report["structurally_unchanged_nodes"] == ["code", "independent"]
    replacement = Component("decoder", ("decoder",), lambda s, inp: "CHANGED")
    changed = Assembly({**assembly.nodes, "decoder": replacement}, assembly.edges)
    before = assembly.evaluate(Spec(code="HGP"))
    after = changed.evaluate(Spec(code="HGP"))
    assert before["decoder"] != after["decoder"]
    assert all(before[n] == after[n] for n in report["structurally_unchanged_nodes"])


class SameDisplay:
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "same display"

    def __eq__(self, other):
        return isinstance(other, SameDisplay) and self.value == other.value


def test_hidden_dependency_uses_value_equality_not_display_string():
    component = Component("opaque", (), lambda s, inp: SameDisplay(s.code))
    assert not context_independence(component, DOMAIN)
    assert not artifact_equal(SameDisplay("BB"), SameDisplay("HGP"))


def test_pointwise_equality_never_calls_specs_outside_supplied_domain():
    domain = {**DOMAIN, "code": ["HGP"]}
    old = Component("decoder", ("decoder",), lambda s, inp: s.code)
    new = Component("decoder", ("decoder",), lambda s, inp: "HGP")
    assert pointwise_equal_on_reads(old, new, domain)


def test_new_contract_is_not_inferred_from_unchanged_outputs():
    assembly = fixture_assembly()
    replacement = Component("decoder", ("decoder",),
                            lambda s, inp: inp["code"], contract=lambda a: False)
    report = theorem1_report(assembly, "decoder", replacement, DOMAIN)
    assert report["applicable"]
    assert report["new_target_contract_requires_check"]
