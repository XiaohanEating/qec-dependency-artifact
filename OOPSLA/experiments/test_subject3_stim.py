"""Regression tests for the second-subject audit (``subject3_stim.py``).

These lock the properties the paper claim rests on for the Stim + sinter +
PyMatching subject system:

* ``test_registry_evidence_files_exist`` — every registry-audit evidence
  record must point at a real file and line; a count without a verifiable
  file:line is not evidence.
* ``test_noise_is_compiled_into_the_circuit`` — swap_impact dimension
  ``noise_parameter`` must record a fingerprint change for every grid step.
  This pins "the noise parameter is written into the circuit artifact" on
  the second subject system, mirroring QUITS' H3.
* ``test_quick_structure_and_statistics`` — the quick pipeline produces a
  well-formed artifact: metadata with versions/paths, the three experiment
  blocks, non-negative counts, and LER points carrying Wilson intervals.
* ``test_no_auto_discovery`` — the hidden-dependency story needs the
  registry (which *does* exist in sinter) to be closed: no entry-point /
  importlib auto-discovery anywhere in the scanned sources.

Run:  python -m pytest OOPSLA/experiments/test_subject3_stim.py -v
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

import subject3_stim  # noqa: E402


@pytest.fixture(scope="module")
def quick_artifact(tmp_path_factory):
    out = tmp_path_factory.mktemp("subject3")
    assert subject3_stim.main(["--quick", "--out", str(out)]) == 0
    blob = json.loads((out / "subject3_stim.json").read_text(encoding="utf-8"))
    md = (out / "subject3_stim.md").read_text(encoding="utf-8")
    return blob, md


def test_registry_evidence_files_exist(quick_artifact):
    """Every evidence record names a real file and a positive line number."""
    blob, _ = quick_artifact
    evidence = blob["registry_audit"]["evidence"]
    assert evidence, "registry audit collected no evidence at all"
    for e in evidence:
        assert e["line"] > 0, e
        assert os.path.exists(e["file"]), f"evidence file missing: {e}"
        lines = Path(e["file"]).read_text(
            encoding="utf-8", errors="replace").splitlines()
        assert e["line"] <= len(lines), e
        assert e["code"] in lines[e["line"] - 1], (
            f"evidence code does not match line content: {e}")


def test_registry_counts_are_non_negative(quick_artifact):
    blob, _ = quick_artifact
    counts = blob["registry_audit"]["counts"]
    for key, value in counts.items():
        assert value >= 0, (key, value)
    # the closed-registry finding: registries exist in sinter ...
    assert counts["name_registries"] >= 1
    # ... but no entry-point/importlib auto-discovery exists anywhere
    assert counts["auto_discovery_sites"] == 0


def test_noise_is_compiled_into_the_circuit(quick_artifact):
    """swap_impact (a): every noise-parameter step must change the circuit
    fingerprint — the Stim subject confirms 'noise is written into the
    circuit' just as QUITS' H3 does."""
    blob, _ = quick_artifact
    rows = [r for r in blob["swap_impact"]["rows"]
            if r["dimension"] == "noise_parameter"]
    assert rows, "no noise_parameter rows recorded"
    for r in rows:
        assert r["changed"], (
            f"noise swap {r['before']} -> {r['after']} did not change the "
            f"circuit fingerprint at distance {r['distance']}")
        assert (r["fingerprint_before"] != r["fingerprint_after"]
                and len(r["fingerprint_before"]) == 64)


def test_export_option_changes_dem_at_fixed_circuit(quick_artifact):
    blob, _ = quick_artifact
    rows = [r for r in blob["swap_impact"]["rows"]
            if r["dimension"] == "export_option"]
    assert rows
    for r in rows:
        assert r["changed"], "decompose_errors=True/False must differ"


def test_quick_structure_and_statistics(quick_artifact):
    blob, md = quick_artifact
    for key in ("metadata", "registry_audit", "swap_impact", "decoder_ler"):
        assert key in blob, key
    m = blob["metadata"]
    for pkg in ("stim", "sinter", "pymatching"):
        assert m["versions"][pkg]
        assert os.path.isdir(m["package_paths"][pkg])
    assert m["quick"] is True
    # LER points carry the shared statistics: rate + Wilson 95% interval
    points = blob["decoder_ler"]["points"]
    assert len(points) == 2
    for pt in points:
        assert 0.0 <= pt["wilson95_low"] <= pt["rate"] <= pt["wilson95_high"]
        assert pt["shots"] == m["ler_shots"]
    # the markdown renders all three sections
    for section in ("Registry audit", "Swap impact", "Decoder LER"):
        assert section in md


def test_decoder_prior_swap_records_shots(quick_artifact):
    """The decoder-prior dimension must record how many predictions were
    compared, whatever the outcome (an honest 0 is a result, not an omission;
    it mirrors QUITS' prior-robustness finding)."""
    blob, _ = quick_artifact
    rows = [r for r in blob["swap_impact"]["rows"]
            if r["dimension"] == "decoder_prior"]
    assert rows
    for r in rows:
        assert r["detail"]["structure_identical"], (
            "prior dimension requires same DEM structure, priors only")
        assert r["detail"]["total_predictions"] == r["detail"]["shots"] > 0
        assert r["detail"]["differing_predictions"] >= 0


def test_no_auto_discovery(quick_artifact):
    """The sinter registry is closed (built-in only): nothing discovers
    components from entry points or importlib metadata.  This is what keeps
    the one registry it does have from becoming a hidden dependency."""
    blob, _ = quick_artifact
    assert blob["registry_audit"]["counts"]["auto_discovery_sites"] == 0
