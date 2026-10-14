"""Tests for the de-circularised practice comparison (``practice_comparison.py``).

The experiment's claim is a comparison, so the tests pin the comparison down:

* structure: the JSON has metadata + sequence + ground truth + all six
  strategies with complete metrics;
* the paper's core story: on every noise-only step ``config_diff`` (the
  git-diff practice) and ``declarative_naive`` (the honest make/snakemake
  user) miss at least one extractor artifact (circuit/DEM), because the
  extractor's runtime read of ``noise`` (H3) is invisible to a declared-config
  diff and un-declarable at the pipeline's file interface — while the checker
  and ``declarative_omniscient`` miss nothing;
* the practice ladder: ``declarative_naive`` declares per-artifact
  dependencies plus the pipeline-visible file wiring, so it closes every
  pipeline-level miss of ``config_diff`` (its rebuild set is a per-step
  superset and its missed set a per-step subset) and strictly improves on
  it wherever a downstream artifact consumes a rebuilt upstream one;
* anti-circularity, structurally: the strategy predictors take specs (plus
  the logged intent) and **no** fingerprint/ground-truth table — the checker
  cannot be "corrected" by the answer it is being scored against;
* ``main`` writes JSON + Markdown next to the script (or ``--out``), like
  every other experiment.

Everything runs in quick mode (6 steps) so the suite stays fast.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_OOPSLA = _HERE.parent
for _p in (str(_OOPSLA / "src"), str(_OOPSLA), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

pc = pytest.importorskip(
    "practice_comparison",
    reason="practice comparison needs the pinned QUITS tree and stim")

EXTRACTOR_ARTIFACTS = {"stim_circuit", "detector_error_model"}


@pytest.fixture(scope="module")
def data() -> dict:
    return pc.run(n_steps=pc.QUICK_STEPS, shots=pc.DEFAULT_SHOTS)


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------

def test_structure(data):
    m = data["metadata"]
    assert m["steps"] == pc.QUICK_STEPS
    assert m["shots"] == pc.DEFAULT_SHOTS
    assert len(data["sequence"]) == pc.QUICK_STEPS
    assert len(data["ground_truth"]) == pc.QUICK_STEPS
    for key in ("read_sets_used", "calibration_seconds_per_build",
                "assembly_model_sources"):
        assert key in m, key
    assert "anti_circularity" in data["methodology"]
    assert "reproducibility" in data["methodology"]


def test_all_six_strategies_with_complete_metrics(data):
    assert set(data["strategies"]) == {
        "full_rerun", "config_diff", "declarative_naive",
        "declarative_omniscient", "logbook", "checker"}
    for name, s in data["strategies"].items():
        t = s["totals"]
        for key in ("missed", "over_rebuilds", "builds", "wall_clock_est_s"):
            assert key in t, (name, key)
        assert isinstance(t["missed"], int)
        assert len(s["per_step"]) == pc.QUICK_STEPS
        for row in s["per_step"]:
            for key in ("changed_artifacts", "rebuilt", "missed",
                        "over_rebuilds"):
                assert key in row, (name, key)


def test_sequence_records_specs_and_change_dimensions(data):
    for i, e in enumerate(data["sequence"]):
        assert e["step"] == i
        for dim in ("code", "extractor", "arch", "noise", "decoder"):
            assert dim in e["spec"], (i, dim)
        if i == 0:
            assert e["changed_dimensions"] == []
        else:
            assert e["changed_dimensions"], i
    # quick mode must still contain noise-only steps (the core story needs them)
    noise_only = [e["step"] for e in data["sequence"]
                  if e["changed_dimensions"] == ["noise"]]
    assert noise_only, "quick sequence has no noise-only step"


def test_checker_read_sets_match_the_quits_model(data):
    """The checker must run on the auto-extracted read sets (H3 included)."""
    rs = data["metadata"]["read_sets_used"]
    assert rs["extractor"] == ["code", "extractor", "noise"]
    assert rs["code"] == ["code"] and rs["noise"] == ["noise"]
    assert rs["decoder"] == ["decoder"] and rs["arch"] == ["arch"]


# ---------------------------------------------------------------------------
# the paper's core story, pinned as assertions
# ---------------------------------------------------------------------------

def test_config_diff_misses_extractor_artifacts_on_noise_steps(data):
    """git-diff practice: a noise-only spec change leaves the extractor's
    circuit/DEM stale — the runtime read extractor -> noise (H3) is exactly
    what a declared-config diff cannot see."""
    gt = data["ground_truth"]
    hits = 0
    for e in data["sequence"]:
        if e["changed_dimensions"] != ["noise"]:
            continue
        step = e["step"]
        changed = {a for a in pc.ALL_ARTIFACTS if gt[step]["changed"][a]}
        missed = set(data["strategies"]["config_diff"]["per_step"][step]["missed"])
        assert changed & EXTRACTOR_ARTIFACTS, (
            f"step {step}: ground truth says no extractor artifact changed")
        assert missed & EXTRACTOR_ARTIFACTS, (
            f"step {step}: config_diff should miss an extractor artifact")
        hits += 1
    assert hits >= 2, "the story needs at least two noise-only steps"


def test_checker_misses_nothing(data):
    """On the QUITS model (R(extractor) contains noise) the checker's
    declared-information prediction has zero misses on this log."""
    assert data["strategies"]["checker"]["totals"]["missed"] == 0
    for row in data["strategies"]["checker"]["per_step"]:
        assert row["missed"] == [], row["step"]


def test_checker_is_not_a_full_rerun(data):
    """0 misses must come from the read sets, not from rebuilding everything:
    the checker must be strictly cheaper than full_rerun on this log."""
    assert data["strategies"]["checker"]["totals"]["builds"] < \
        data["strategies"]["full_rerun"]["totals"]["builds"]


def test_full_rerun_never_misses(data):
    assert data["strategies"]["full_rerun"]["totals"]["missed"] == 0


def test_logbook_misses_at_least_as_much_as_config_diff(data):
    """The notebook records intent only; on the code-port step it must miss
    strictly more than the declared-config diff (which at least sees the
    extractor reset).  On all other steps they coincide because each step
    changes exactly one declared dimension."""
    cd = data["strategies"]["config_diff"]["totals"]["missed"]
    lb = data["strategies"]["logbook"]["totals"]["missed"]
    assert lb >= cd
    for e, rc, rl in zip(data["sequence"],
                         data["strategies"]["config_diff"]["per_step"],
                         data["strategies"]["logbook"]["per_step"]):
        if e["changed_dimensions"] == ["code", "extractor"]:
            assert len(rl["missed"]) > len(rc["missed"]), e["step"]


# ---------------------------------------------------------------------------
# the declarative-build baselines (make/snakemake practice)
# ---------------------------------------------------------------------------

def _spec(**over):
    sp = dict(pc.BASELINE_SPEC)
    sp.update(over)
    return sp


def test_declarative_naive_has_the_same_hidden_read_blind_spot():
    """An honest make/snakemake user cannot declare extractor -> noise: the
    read happens inside build_circuit, not at the file interface, so a
    noise-only change rebuilds only the noise model — the same blind spot
    as the git-diff practice on such steps."""
    prev = _spec()
    new = _spec(noise="SI1000" if prev["noise"] != "SI1000" else "SD6")
    naive = pc.predict_declarative_naive(prev, new)
    cd = pc.predict_config_diff(prev, new)
    assert naive == cd == {"noise_model"}


def test_declarative_naive_declared_file_wiring_beats_config_diff():
    """The practice difference, pinned at predictor level: the declared
    pipeline-visible file edges (decoder consumes the circuit, layout
    consumes the code) cascade under make semantics, so naive rebuilds the
    downstream consumers that config_diff leaves stale on the extractor
    swap and on the code port."""
    prev = _spec()
    ext_new = _spec(extractor="custom")
    delta_ext = pc.predict_declarative_naive(prev, ext_new) - \
        pc.predict_config_diff(prev, ext_new)
    assert "decoder_predictions" in delta_ext
    port_new = _spec(code="HGP", extractor="zxcoloration")
    delta_port = pc.predict_declarative_naive(prev, port_new) - \
        pc.predict_config_diff(prev, port_new)
    assert {"decoder_predictions", "layout_positions"} <= delta_port


def test_declarative_naive_dominates_config_diff_on_the_log(data):
    """Per step on this log, naive's declared deps + file wiring rebuild a
    superset of config_diff's set and therefore miss a subset.  In quick
    mode (noise x4 + decoder swap) the two coincide on every step — the
    strict improvement lives on the extractor-swap and code-port steps of
    the full log, pinned predictor-level above."""
    cd, naive = data["strategies"]["config_diff"], \
        data["strategies"]["declarative_naive"]
    assert naive["totals"]["missed"] <= cd["totals"]["missed"]
    assert naive["totals"]["builds"] >= cd["totals"]["builds"]
    for rc, rn in zip(cd["per_step"], naive["per_step"]):
        assert set(rn["rebuilt"]) >= set(rc["rebuilt"])
        assert set(rn["missed"]) <= set(rc["missed"])


def test_declarative_naive_misses_extractor_artifacts_on_noise_steps(data):
    """Same blind spot as config_diff on noise-only steps: the extractor's
    circuit/DEM stay stale because the hidden read is un-declarable."""
    gt = data["ground_truth"]
    hits = 0
    for e in data["sequence"]:
        if e["changed_dimensions"] != ["noise"]:
            continue
        step = e["step"]
        missed = set(
            data["strategies"]["declarative_naive"]["per_step"][step]["missed"])
        assert missed & EXTRACTOR_ARTIFACTS, (
            f"step {step}: declarative_naive should miss an extractor artifact")
        hits += 1
    assert hits >= 2, "the story needs at least two noise-only steps"


def test_declarative_omniscient_matches_checker_on_every_step(data):
    """The upper bound: with the true coordinate closures declared,
    omniscient rebuilds exactly the checker's set on every step — perfect
    declarations and the extracted read sets carry the same information."""
    assert data["strategies"]["declarative_omniscient"]["totals"]["missed"] == 0
    for i, e in enumerate(data["sequence"]):
        if i == 0:
            continue
        prev = data["sequence"][i - 1]["spec"]
        expected = set(data["strategies"]["checker"]["per_step"][i]["rebuilt"])
        assert pc.predict_declarative_omniscient(prev, e["spec"]) == \
            expected, e["step"]


def test_methodology_declares_the_declarative_vs_config_diff_difference(data):
    blob = json.dumps(data["methodology"]).lower()
    assert "declarative_vs_config_diff" in data["methodology"]
    assert "un-declarable" in blob or "undeclarable" in blob
    assert "no declarations at all" in blob


# ---------------------------------------------------------------------------
# anti-circularity, enforced by structure and confirmed here
# ---------------------------------------------------------------------------

def test_predictors_do_not_take_ground_truth():
    """The predictors' signatures must not admit the fingerprint table.

    This is the structural half of the de-circularisation: a checker whose
    prediction function cannot receive ground truth cannot be quietly
    corrected by the answer it is scored against.
    """
    for fn in (pc.predict_full_rerun, pc.predict_config_diff,
                pc.predict_declarative_naive,
                pc.predict_declarative_omniscient,
                pc.predict_checker):
        params = set(inspect.signature(fn).parameters)
        assert params == {"prev_spec", "new_spec"}, (fn.__name__, params)
        for p in params:
            assert not any(s in p.lower() for s in
                           ("finger", "truth", "ground", "gt")), (fn.__name__, p)
    params = set(inspect.signature(pc.predict_logbook).parameters)
    assert "intent" in params
    for p in params:
        assert not any(s in p.lower() for s in
                       ("finger", "truth", "ground", "gt")), p


def test_checker_prediction_is_a_pure_function_of_specs(data):
    """Functional half: replaying the checker's predictions from the specs
    alone reproduces the scored rebuild sets — no fingerprint input exists
    on any path."""
    gt = data["ground_truth"]
    for i, e in enumerate(data["sequence"]):
        if i == 0:
            continue
        prev = data["sequence"][i - 1]["spec"]
        expected = set(data["strategies"]["checker"]["per_step"][i]["rebuilt"])
        assert pc.predict_checker(prev, e["spec"]) == expected, e["step"]
    # and the predictor must not consult the ground truth even when it is
    # in scope: corrupting the fingerprint table changes nothing
    for row in gt:
        for art in row["fingerprints"]:
            row["fingerprints"][art] = "0" * 16
    e = data["sequence"][1]
    assert pc.predict_checker(data["sequence"][0]["spec"], e["spec"]) == \
        set(data["strategies"]["checker"]["per_step"][1]["rebuilt"])


def test_methodology_declares_the_no_ground_truth_contract(data):
    blob = json.dumps(data["methodology"]).lower()
    assert "circula" in blob
    assert "fingerprint" in blob
    assert "ground truth" in blob


# ---------------------------------------------------------------------------
# script behaviour: writes JSON + MD (to --out, never the repo in tests)
# ---------------------------------------------------------------------------

def test_script_runs_and_emits_artifacts(tmp_path):
    assert pc.main(["--quick", "--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "practice_comparison.json")
                      .read_text(encoding="utf-8"))
    assert data["metadata"]["steps"] == pc.QUICK_STEPS
    assert data["strategies"]["checker"]["totals"]["missed"] == 0
    md = (tmp_path / "practice_comparison.md").read_text(encoding="utf-8")
    for section in ("Methodology", "research log", "Ground truth",
                    "Per-strategy metrics", "Conclusion"):
        assert section in md, section
    # the core story must be visible in the Markdown
    assert "config_diff" in md and "checker" in md
