"""Declarative checking vs. real QEC re-computation practices (Gap 6).

This experiment answers the paper's sixth gap:

> 6. 与现实做法的对比：没有和 QEC 研究者今天的实际做法比较，
>      比如手工记录参数、按配置做缓存、每次全部重跑。

**Why this file was rewritten (de-circularisation).**  The first version of
this experiment defined its "checker" column as "recompute everything that
*could* be affected" and then reported that the checker misses nothing.  A
checker whose prediction is defined as the set of things that changed cannot
miss by construction — the comparison was circular and measured nothing.
This version separates the two sides completely:

* **Ground truth** is measured: a deterministic research log of N specs is
  executed on the pinned QUITS tree, and per step the artifact fingerprints
  (circuit text hash, DEM text hash, a 64-shot prediction hash, plus the code
  / noise / layout artifacts) are compared byte-wise to the previous step.
  Only *here* do fingerprints exist.
* **Each strategy's prediction is computed from declared information only**
  and scored *afterwards* against the ground-truth table.  The checker
  strategy uses exactly the declared read sets
  ``R(code)={code}``, ``R(extractor)={code,extractor,noise}``,
  ``R(noise)={noise}``, ``R(decoder)={decoder}``, ``R(arch)={arch}``
  (``semantics.READ_SETS_FROM_SOURCE``, auto-extracted by
  ``experiments/extract_read_sets.py`` — the extractor's read of ``noise``
  is finding H3) and the artifact-DAG edges via
  ``semantics.coordinate_impact``.  It never receives the fingerprint table
  (structurally: its predictor's inputs are two specs, nothing else).

The six strategies compared on the same log, the same artifacts, the same
ground truth:

* ``full_rerun``   — rebuild every artifact at every step (cost baseline).
* ``config_diff``  — the "git diff the config" practice: rebuild only the
                     artifacts of dimensions whose *declared spec value*
                     changed.  It cannot see runtime reads, so a noise
                     parameter change does **not** trigger a rebuild of the
                     extractor's circuit/DEM — this structural blind spot is
                     what we measure.  It has no per-artifact declarations
                     at all: it diffs one config file at whatever dimension
                     granularity the file happens to have.
* ``declarative_naive`` — the make/snakemake practice with an *honest*
                     user: every artifact carries an explicit declaration of
                     the spec coordinates it depends on, but the declarations
                     are based on interface visibility only — each artifact
                     is bound to its *nominal component* coordinate
                     (``stim_circuit: extractor``, ``decoder_predictions:
                     decoder``, ...) plus the pipeline-visible artifact-file
                     wiring (the circuit is built on the code object, the
                     decoder consumes the circuit, the layout is built on
                     the code object — the edges the pipeline author can see
                     in their own build script, then a make-style cascade
                     rebuilds downstream files of anything regenerated).
                     What this user cannot see is the *runtime* coordinate
                     read inside a component: the extractor receives the
                     noise model inside ``build_circuit`` (finding H3), not
                     as a pipeline file, so no declaration they can write
                     expresses it.  This is exactly the situation of a
                     researcher who wires their pipeline in snakemake and
                     writes down every dependency they believe in.
* ``declarative_omniscient`` — the upper bound: the same per-artifact
                     declaration mechanism, but the declared coordinate sets
                     are the *true* ones (the full spec-coordinate impact
                     closure of each artifact, which includes
                     extractor -> noise).  It answers "how far could even a
                     perfect declarative-build user get" — and thereby what
                     information content the checker has to supply.
* ``logbook``      — the manual lab-notebook practice: the log records the
                     *intent* dimension of each step; only that dimension's
                     artifacts are rebuilt; all cross-dimension staleness is
                     missed.  (On this log every step changes exactly one
                     declared dimension except the code-port step, where the
                     log records intent ``code`` but the declared spec diff
                     also touches ``extractor`` — that step separates
                     ``logbook`` from ``config_diff``.)
* ``checker``      — our tool: coordinate change -> readers (declared R(c))
                     -> artifact-DAG cone.  Prediction only.

Metrics per strategy: missed artifacts (changed by ground truth but not
rebuilt, listed per step), over-rebuilds (rebuilt but byte-identical), total
artifact builds (cost proxy), and an estimated wall-clock from a calibration
timing of one build + one decode.

Expected honest outcome: on the QUITS model the checker misses **0**
(because the model already contains the extractor -> noise read), while
``config_diff``, ``logbook`` and ``declarative_naive`` miss the extractor's
circuit/DEM/predictions on every noise-only step — for the declarative-build
user because the hidden read is not declarable at the file interface.
``declarative_naive`` still strictly improves on ``config_diff`` on the
extractor-swap and code-port steps (the file wiring it declares catches the
downstream consumers), and ``declarative_omniscient`` reaches the checker's
prediction exactly — the paper's core story, measured without circularity.

Outputs: ``practice_comparison.json`` / ``practice_comparison.md``.

Run:  python experiments/practice_comparison.py [--quick] [--out DIR] [--steps N] [--shots N]
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

import outdir  # noqa: E402
import qec_measure as Q  # noqa: E402
from semantics import (ASSEMBLY_EDGES_FROM_SOURCE, coordinate_impact,  # noqa: E402
                       make_source_faithful_assembly)

DEFAULT_STEPS = 12
QUICK_STEPS = 6
DEFAULT_SHOTS = 64
SAMPLER_SEED = 7
NUM_ROUNDS = 2

BASELINE_SPEC = {"code": "BB", "extractor": "zxcoloration",
                 "arch": "transversal", "noise": "SD6", "decoder": "BP-OSD"}

#: deterministic order the noise sweep walks through (skips the current value).
#: SD6-10x is deliberately excluded: at that saturated operating point both
#: QUITS decoders are non-reproducible call-to-call (unseeded randomness
#: inside ldpc's OSD/LSD tie-breaking), which would corrupt the byte-level
#: ground truth.  The remaining values are verified deterministic for both
#: decoders on every code family used here.
NOISE_CYCLE = ["SI1000", "SD6-0.1x", "SD6"]

#: research-log shape: noise sweep x4, decoder swap, extractor swap, then a
#: noise pair, the code port, the arch swap, one more noise step; longer logs
#: pad with further noise sweeps, shorter logs truncate (``--quick`` takes the
#: first 5 changes -> 6 steps, which still contains noise-only steps).
CHANGE_PLAN = ["noise", "noise", "noise", "noise",
               "decoder", "extractor",
               "noise", "noise", "code", "arch", "noise"]

#: component -> the artifacts it produces (the artifact set of one pipeline run)
COMPONENT_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "code": ("code_matrices",),
    "noise": ("noise_model",),
    "extractor": ("stim_circuit", "detector_error_model"),
    "decoder": ("decoder_predictions",),
    "arch": ("layout_positions",),
}
ALL_ARTIFACTS: tuple[str, ...] = tuple(
    a for dim in ("code", "noise", "extractor", "decoder", "arch")
    for a in COMPONENT_ARTIFACTS[dim])

#: which calibration timing bucket pays for rebuilding an artifact
ARTIFACT_COST_KIND = {
    "code_matrices": "code", "noise_model": "noise",
    "stim_circuit": "extractor", "detector_error_model": "extractor",
    "decoder_predictions": "decoder", "layout_positions": "arch",
}

#: the make/snakemake-style *declared* dependency model of an honest user,
#: used by ``predict_declarative_naive``.  Two parts:
#:
#: (a) per-artifact coordinate declarations, based on interface visibility
#:     only: every artifact is bound to the spec coordinate of its *nominal
#:     component* (the knob a researcher believes the artifact answers to:
#:     the circuit declares ``extractor``, the noise model declares ``noise``,
#:     the predictions declare ``decoder``, ...).  No runtime reads.
#: (b) pipeline-visible artifact-file edges — the wiring the pipeline author
#:     can see in their own build script (the circuit is built *on* the code
#:     object, the decoder consumes the code matrices and the circuit, the
#:     layout is built on the code object).  Under make semantics,
#:     regenerating an upstream file forces a rebuild of everything
#:     downstream of it, so these edges cascade.
#:
#: What is deliberately NOT in this model: the coordinate read
#: extractor -> noise (finding H3).  ``build_circuit`` receives the error
#: model *inside* the component call, not as a pipeline file, so there is no
#: edge a make/snakemake user could declare for it.  That un-declarable read
#: is the measured blind spot of the declarative-build practice.
ARTIFACT_NOMINAL_COMPONENT: dict[str, str] = {
    a: dim for dim, arts in COMPONENT_ARTIFACTS.items() for a in arts}
DECLARATIVE_NAIVE_COORD_DEPS: dict[str, frozenset[str]] = {
    a: frozenset({ARTIFACT_NOMINAL_COMPONENT[a]}) for a in ALL_ARTIFACTS}


def _declarative_rebuild(changed: set[str],
                         coord_deps: dict[str, frozenset[str]],
                         file_edges: dict[str, tuple[str, ...]]) -> set[str]:
    """Make semantics: rebuild an artifact when a declared coordinate changed
    or when an upstream component's artifact was (re)built — closure over the
    declared file edges."""
    comp_rebuilt = {ARTIFACT_NOMINAL_COMPONENT[a]
                    for a in ALL_ARTIFACTS
                    if set(coord_deps[a]) & changed}
    frontier = set(comp_rebuilt)
    while frontier:
        nxt: set[str] = set()
        for dim in frontier:
            for down, ups in file_edges.items():
                if dim in ups and down not in comp_rebuilt:
                    nxt.add(down)
        comp_rebuilt |= nxt
        frontier = nxt
    return {a for d in comp_rebuilt for a in COMPONENT_ARTIFACTS[d]}


def _sha(text_or_bytes) -> str:
    data = (text_or_bytes if isinstance(text_or_bytes, bytes)
            else str(text_or_bytes).encode("utf-8"))
    return hashlib.sha256(data).hexdigest()[:16]


# ---------------------------------------------------------------------------
# deterministic research log
# ---------------------------------------------------------------------------

def generate_sequence(n_steps: int) -> list[dict]:
    """The N-step research log: baseline + deterministic change plan.

    Every entry records the full spec, the dimensions whose declared value
    changed, and the *intent* dimension a human would write in a lab log.
    """
    plan = list(CHANGE_PLAN)
    while len(plan) < n_steps - 1:
        plan.append("noise")
    plan = plan[:n_steps - 1]

    seq = [{"step": 0, "spec": dict(BASELINE_SPEC), "intent": None,
            "changed_dimensions": [], "note": "baseline run"}]
    spec = dict(BASELINE_SPEC)
    noise_idx = 0
    for step, kind in enumerate(plan, start=1):
        prev = dict(spec)
        if kind == "noise":
            while True:
                cand = NOISE_CYCLE[noise_idx % len(NOISE_CYCLE)]
                noise_idx += 1
                if cand != spec["noise"]:
                    spec["noise"] = cand
                    break
            note = "noise model sweep"
        elif kind == "decoder":
            spec["decoder"] = ("BP-LSD" if spec["decoder"] == "BP-OSD"
                               else "BP-OSD")
            note = "decoder swap"
        elif kind == "extractor":
            spec["extractor"] = ("custom" if spec["extractor"] == "zxcoloration"
                                 else "zxcoloration")
            note = "extraction schedule swap"
        elif kind == "code":
            spec["code"] = "HGP"
            spec["extractor"] = "zxcoloration"   # port: custom not in HGP whitelist
            note = ("code family change; extractor reset to zxcoloration "
                    "(H1: custom is not in HgpCode.supported_strategies)")
        elif kind == "arch":
            spec["arch"] = ("toric" if spec["arch"] == "transversal"
                            else "transversal")
            note = ("architecture swap (QUITS build does not route arch into "
                    "the circuit products -- expected to change only the "
                    "layout artifact)")
        changed = sorted(k for k in spec if spec[k] != prev[k])
        seq.append({"step": step, "spec": dict(spec), "intent": kind,
                    "changed_dimensions": changed, "note": note})
    return seq


# ---------------------------------------------------------------------------
# ground truth: build every step on the pinned QUITS tree, fingerprint artifacts
# ---------------------------------------------------------------------------

def _layout_fingerprint(code_obj, arch: str):
    try:
        if arch == "transversal":
            from quits.layout import TransversalLayout
            obj = TransversalLayout(code_obj, center_checks=True)
        elif arch == "toric":
            from quits.layout import ToricLayout
            obj = ToricLayout(code_obj)
        else:
            return _sha(f"arch={arch}")
        mapping = obj.mapping()
        payload = tuple(sorted(
            (role, tuple(sorted(getattr(mapping, role).items())))
            for role in ("data", "zcheck", "xcheck")))
        return _sha(str(payload))
    except Exception as exc:  # layout is optional in QUITS (get_layout -> None)
        return _sha(f"arch={arch}:unavailable:{exc.__class__.__name__}")


def _decode_predictions(built, decoder: str, shots: int, seed: int) -> np.ndarray:
    if decoder == "BP-OSD":
        return np.asarray(Q.decode(built, shots=shots, seed=seed))
    from quits.decoder import sliding_window_bplsd_circuit_mem
    from quits.simulation import get_stim_mem_result
    det, _ = get_stim_mem_result(built["circuit"], shots, seed=seed)
    return np.asarray(sliding_window_bplsd_circuit_mem(
        det.copy(), built["circuit"], built["hz"], built["lz"], W=3, F=1))


def build_artifact_fingerprints(spec: dict, shots: int, seed: int = SAMPLER_SEED) -> dict:
    """One pipeline run -> fingerprint of every artifact (the ground truth row)."""
    code_obj = Q.code_instance(spec["code"])
    built = Q.build(spec["code"], spec["extractor"], spec["noise"],
                    arch=spec["arch"], num_rounds=NUM_ROUNDS)
    pred = _decode_predictions(built, spec["decoder"], shots, seed)
    from quits import ErrorModel
    error_model = ErrorModel(**Q.NOISE_PARAMS[spec["noise"]])
    return {
        "code_matrices": _sha(b"".join(
            _sha(m.tobytes()).encode() for m in
            (code_obj.hz, code_obj.hx, code_obj.lz, code_obj.lx))),
        "noise_model": _sha(tuple(sorted(error_model.__dict__.items()))),
        "stim_circuit": _sha(str(built["circuit"])),
        "detector_error_model": _sha(str(built["dem"])),
        "decoder_predictions": _sha(np.asarray(pred).tobytes()),
        "layout_positions": _layout_fingerprint(code_obj, spec["arch"]),
    }


def ground_truth(sequence: list[dict], shots: int) -> dict:
    """Per step, per artifact: fingerprint + changed flag vs the previous step.

    This is the ONLY place fingerprints are produced; every strategy is
    scored against this table after its prediction has been fixed.
    """
    fps = []
    for entry in sequence:
        fps.append(build_artifact_fingerprints(entry["spec"], shots))
    rows = []
    for t, entry in enumerate(sequence):
        row = {"step": entry["step"], "spec": entry["spec"]}
        if t == 0:
            row["changed"] = {a: True for a in ALL_ARTIFACTS}
        else:
            row["changed"] = {a: fps[t][a] != fps[t - 1][a]
                              for a in ALL_ARTIFACTS}
        row["fingerprints"] = fps[t]
        rows.append(row)
    return {"rows": rows}


# ---------------------------------------------------------------------------
# strategy predictors — declared information ONLY (specs), no fingerprints
# ---------------------------------------------------------------------------
#
# Anti-circularity contract: the functions below take specs (and, for the
# logbook, the recorded intent dimension).  None of them accepts the ground
# truth or any fingerprint table; the checker additionally restricts itself
# to the declared read sets R(c) and the artifact-DAG edges.  Scoring against
# ground truth happens afterwards in ``simulate_strategy``.

def predict_full_rerun(prev_spec: dict, new_spec: dict) -> set[str]:
    """Rebuild everything, every step (the no-cache baseline)."""
    return set(ALL_ARTIFACTS)


def predict_config_diff(prev_spec: dict, new_spec: dict) -> set[str]:
    """The 'git diff the config' practice: only dimensions whose *declared*
    spec value changed get their artifacts rebuilt.  Runtime reads are
    invisible to it, so a noise change never triggers an extractor rebuild."""
    changed = {d for d in prev_spec if prev_spec[d] != new_spec[d]}
    return {a for d in changed for a in COMPONENT_ARTIFACTS[d]}


def predict_logbook(prev_spec: dict, new_spec: dict, intent: str | None) -> set[str]:
    """The manual lab-notebook practice: rebuild only the artifacts of the
    dimension the log records as this step's intent; cross-dimension
    staleness is entirely missed."""
    if intent is None:
        return set(ALL_ARTIFACTS)      # baseline
    return set(COMPONENT_ARTIFACTS[intent])


def predict_declarative_naive(prev_spec: dict, new_spec: dict) -> set[str]:
    """The make/snakemake practice with an honest user (see module docstring).

    Declared information: per-artifact binding to the nominal component
    coordinate (``DECLARATIVE_NAIVE_COORD_DEPS``) + the pipeline-visible
    artifact-file edges (``ASSEMBLY_EDGES_FROM_SOURCE`` — the wiring visible
    in the pipeline author's own build script) + make-style cascade.  The
    runtime read extractor -> noise (H3) happens inside ``build_circuit``
    and has no file-level edge, so a noise-only step rebuilds only the
    noise model — exactly the blind spot of the git-diff practice.  The
    difference from ``predict_config_diff`` is the practice, not the
    granularity of the config file: this user DOES declare per-artifact
    dependencies, and those declarations + the visible file wiring close
    every miss that stems from pipeline-level coupling (e.g. the decoder
    consuming the circuit); what declarations cannot express is a
    coordinate read hidden inside a component.
    """
    changed = {d for d in prev_spec if prev_spec[d] != new_spec[d]}
    return _declarative_rebuild(changed, DECLARATIVE_NAIVE_COORD_DEPS,
                                ASSEMBLY_EDGES_FROM_SOURCE)


def _omniscient_coord_deps() -> dict[str, frozenset[str]]:
    """The perfect declarative user's per-artifact coordinate declarations:
    artifact a declares exactly the spec coordinates whose change can alter
    it, ``{coord : a in coordinate_impact(coord)}`` on the source-faithful
    assembly.  Declared-information modelling (same channel as the checker),
    never ground-truth fingerprints."""
    assembly = make_source_faithful_assembly()
    deps: dict[str, set[str]] = {a: set() for a in ALL_ARTIFACTS}
    for coord in ("code", "noise", "extractor", "decoder", "arch"):
        for dim in coordinate_impact(assembly, coord):
            for a in COMPONENT_ARTIFACTS.get(dim, ()):
                deps[a].add(coord)
    return {a: frozenset(d) for a, d in deps.items()}


def predict_declarative_omniscient(prev_spec: dict, new_spec: dict) -> set[str]:
    """The declarative-build upper bound: same per-artifact declaration
    mechanism as the naive variant, but the declared coordinate sets are the
    true ones (they contain extractor -> noise).  On this model its
    prediction coincides with the checker's — which is the point: it shows
    that the checker's information content equals *perfect* declarations,
    and that source-level extraction is the non-omniscient way to obtain
    them."""
    changed = {d for d in prev_spec if prev_spec[d] != new_spec[d]}
    return _declarative_rebuild(changed, _omniscient_coord_deps(),
                                ASSEMBLY_EDGES_FROM_SOURCE)


def predict_checker(prev_spec: dict, new_spec: dict) -> set[str]:
    """Our tool: coordinate change -> readers via the *declared* read sets
    R(c) -> artifact-DAG cone (``semantics.coordinate_impact`` on the
    source-faithful assembly, whose read sets were auto-extracted from the
    pinned tree by ``experiments/extract_read_sets.py``).

    The extractor's declared read set contains ``noise`` (finding H3:
    ``build_circuit`` bakes the error model into the circuit), which is why a
    noise step forces a rebuild of the circuit, DEM and predictions here —
    and why this predictor must NOT be given access to the ground-truth
    fingerprints: doing so would recreate the circularity this rewrite
    removes (a checker corrected by "what actually changed" cannot miss).
    """
    changed = {d for d in prev_spec if prev_spec[d] != new_spec[d]}
    if not changed:
        return set()
    assembly = make_source_faithful_assembly()
    impacted: set[str] = set()
    for coord in changed:
        impacted |= coordinate_impact(assembly, coord)
    return {a for d in impacted if d in COMPONENT_ARTIFACTS
            for a in COMPONENT_ARTIFACTS[d]}


def simulate_strategy(name: str, sequence: list[dict], gt: dict,
                      calibration: dict) -> dict:
    """Score one strategy's predictions against the ground-truth table.

    Prediction first (from specs only), scoring second — the two phases are
    deliberately separate functions so the checker can never see the answer.
    """
    predictor = {"full_rerun": predict_full_rerun,
                 "config_diff": predict_config_diff,
                 "declarative_naive": predict_declarative_naive,
                 "declarative_omniscient": predict_declarative_omniscient,
                 "checker": predict_checker}.get(name)
    per_step = []
    totals = {"missed": 0, "over_rebuilds": 0, "builds": 0,
              "wall_clock_est_s": 0.0}
    for t, entry in enumerate(sequence):
        new_spec = entry["spec"]
        prev_spec = sequence[t - 1]["spec"] if t > 0 else None
        if name == "logbook":
            rebuilt = predict_logbook(prev_spec, new_spec, entry["intent"])
        elif t == 0:
            rebuilt = set(ALL_ARTIFACTS)   # every strategy builds the baseline
        else:
            rebuilt = predictor(prev_spec, new_spec)
        changed = gt["rows"][t]["changed"]
        missed = sorted(a for a in ALL_ARTIFACTS if changed[a] and a not in rebuilt)
        over = sorted(a for a in ALL_ARTIFACTS if not changed[a] and a in rebuilt)
        kinds = {ARTIFACT_COST_KIND[a] for a in rebuilt}
        wall = sum(calibration[k] for k in kinds)
        totals["missed"] += len(missed)
        totals["over_rebuilds"] += len(over)
        totals["builds"] += len(rebuilt)
        totals["wall_clock_est_s"] += wall
        per_step.append({
            "step": entry["step"],
            "intent": entry["intent"],
            "changed_dimensions": entry["changed_dimensions"],
            "changed_artifacts": sorted(a for a in ALL_ARTIFACTS if changed[a]),
            "rebuilt": sorted(rebuilt),
            "missed": missed,
            "over_rebuilds": over,
            "wall_clock_est_s": wall,
        })
    totals["wall_clock_est_s"] = round(totals["wall_clock_est_s"], 3)
    return {"strategy": name, "totals": totals, "per_step": per_step}


STRATEGY_DESCRIPTIONS = {
    "full_rerun": "rebuild every artifact at every step (cost baseline)",
    "config_diff": ("'git diff the config': rebuild only artifacts of dimensions "
                    "whose declared spec value changed; runtime reads invisible; "
                    "no per-artifact declarations at all (pure spec-file diff)"),
    "declarative_naive": ("make/snakemake practice, honest user: per-artifact "
                          "declarations binding each artifact to its nominal "
                          "component coordinate + pipeline-visible artifact-file "
                          "edges (ASSEMBLY_EDGES_FROM_SOURCE) + make-style "
                          "cascade; the runtime read extractor->noise (H3) "
                          "happens inside build_circuit, has no file edge, and "
                          "is therefore un-declarable"),
    "declarative_omniscient": ("same declaration mechanism, but declared "
                               "coordinate sets are the true impact closure "
                               "(extractor->noise included): the upper bound "
                               "of what any declarative-build user can reach"),
    "logbook": ("manual lab notebook: rebuild only the intent dimension's "
                "artifacts; all cross-dimension staleness missed"),
    "checker": ("our tool: declared read sets R(c) + artifact-DAG cone "
                "(coordinate_impact on the source-faithful assembly); "
                "prediction uses no ground truth"),
}


# ---------------------------------------------------------------------------
# calibration: seconds for one build / one decode (wall-clock estimate)
# ---------------------------------------------------------------------------

def calibrate(shots: int) -> dict:
    spec = dict(BASELINE_SPEC)

    def timed(fn, warmup: int = 1) -> float:
        for _ in range(warmup):
            fn()
        t0 = time.perf_counter()
        fn()
        return time.perf_counter() - t0

    t_code = timed(lambda: Q.code_instance(spec["code"]))
    built_box: dict = {}

    def _build():
        built_box["b"] = Q.build(spec["code"], spec["extractor"], spec["noise"],
                                 num_rounds=NUM_ROUNDS)
    t_extract = timed(_build)
    t_decode = timed(lambda: _decode_predictions(built_box["b"], spec["decoder"],
                                                 shots, SAMPLER_SEED))
    code_obj = Q.code_instance(spec["code"])
    t_layout = timed(lambda: _layout_fingerprint(code_obj, spec["arch"]))

    from quits import ErrorModel
    t_noise = timed(lambda: ErrorModel(**Q.NOISE_PARAMS[spec["noise"]]))

    def rnd(x: float) -> float:
        return round(x, 4)
    return {"code": rnd(t_code), "noise": rnd(t_noise),
            "extractor": rnd(t_extract), "decoder": rnd(t_decode),
            "arch": rnd(t_layout), "shots": shots}


# ---------------------------------------------------------------------------
# run + report
# ---------------------------------------------------------------------------

def run(n_steps: int = DEFAULT_STEPS, shots: int = DEFAULT_SHOTS) -> dict:
    sequence = generate_sequence(n_steps)
    calibration = calibrate(shots)
    t0 = time.perf_counter()
    gt = ground_truth(sequence, shots)
    gt_seconds = round(time.perf_counter() - t0, 2)

    strategies = {}
    for name in ("full_rerun", "config_diff", "declarative_naive",
                 "declarative_omniscient", "logbook", "checker"):
        strategies[name] = simulate_strategy(name, sequence, gt, calibration)

    total_changed = sum(
        sum(1 for a in ALL_ARTIFACTS if r["changed"][a])
        for r in gt["rows"])
    for name, s in strategies.items():
        s["miss_rate"] = (round(s["totals"]["missed"] / total_changed, 4)
                          if total_changed else 0.0)

    return {
        "metadata": {
            "description": "declarative checking vs real QEC re-computation "
                           "practices (Gap 6), de-circularised",
            "date": date.today().isoformat(),
            "steps": n_steps,
            "shots": shots,
            "sampler_seed": SAMPLER_SEED,
            "num_rounds": NUM_ROUNDS,
            "baseline_spec": dict(BASELINE_SPEC),
            "noise_cycle": list(NOISE_CYCLE),
            "ground_truth_wall_s": gt_seconds,
            "pythonhashseed": "0 via main() self re-exec (QUITS circuit text "
                              "is hash-seed dependent; metrics are not)",
            "calibration_seconds_per_build": calibration,
            "read_sets_used": {
                "code": ["code"], "extractor": ["code", "extractor", "noise"],
                "noise": ["noise"], "decoder": ["decoder"], "arch": ["arch"],
                "source": "semantics.READ_SETS_FROM_SOURCE "
                          "(experiments/extract_read_sets.py; extractor->noise is H3)",
            },
            "assembly_model_sources": __import__("semantics").assembly_model_sources(
                ["source_faithful"]),
        },
        "methodology": {
            "anti_circularity": (
                "The previous version of this experiment defined the checker's "
                "prediction as 'recompute everything that could be affected' "
                "and reported 0 misses by construction.  Here ground truth "
                "(byte-level artifact fingerprints per step) is measured "
                "independently on the pinned QUITS tree; each strategy's "
                "rebuild set is predicted from declared information only — "
                "for the checker, the declared read sets R(c) and the "
                "artifact-DAG edges via semantics.coordinate_impact — and "
                "scored against ground truth only afterwards.  "
                "predict_checker/predict_config_diff/predict_logbook/"
                "predict_declarative_naive/predict_declarative_omniscient "
                "take specs (plus the logged intent), never the fingerprint "
                "table; this is enforced by their signatures and locked by "
                "experiments/test_practice_comparison.py.  The omniscient "
                "declarative variant uses the same declared-information "
                "channel as the checker (the source-faithful read sets), "
                "never the measured fingerprints — it models a user whose "
                "declarations happen to be perfect, not a peek at the answer."),
            "declarative_vs_config_diff": (
                "config_diff and declarative_naive are NOT the same practice. "
                "config_diff has no declarations at all: it diffs the spec "
                "file and rebuilds the artifacts of whatever dimension "
                "changed, so (i) it cannot attach different dependencies to "
                "different artifacts of one component and (ii) it knows "
                "nothing about artifact-file wiring, missing e.g. the "
                "decoder's consumption of the circuit.  declarative_naive "
                "declares per-artifact dependencies and the pipeline-visible "
                "file edges, and make's cascade closes exactly those "
                "pipeline-level misses.  What no declaration at the pipeline "
                "interface can express is a coordinate read hidden INSIDE a "
                "component call — extractor -> noise (H3) enters "
                "build_circuit as a parameter value, not as a file, so the "
                "file DAG has no edge for it and every declarative-build "
                "user, however honest, keeps the extractor's circuit/DEM/"
                "predictions stale on noise-only steps.  declarative_"
                "omniscient is the upper bound in which the declared "
                "coordinate sets are the true ones: it reaches the "
                "checker's prediction, showing the checker's information "
                "content equals perfect declarations."),
            "declarative_naive_declaration_sets": {
                "coordinate_decls": {a: sorted(d) for a, d in
                                     DECLARATIVE_NAIVE_COORD_DEPS.items()},
                "file_edges": {k: list(v) for k, v in
                               ASSEMBLY_EDGES_FROM_SOURCE.items()},
                "omitted_hidden_read": "extractor -> noise (H3): inside "
                                       "build_circuit, not a pipeline file",
            },
            "artifacts": list(ALL_ARTIFACTS),
            "component_artifacts": {k: list(v) for k, v in COMPONENT_ARTIFACTS.items()},
            "metrics": {
                "missed": "artifact changed by ground truth but not rebuilt "
                          "(the dangerous case: stale artifact in use)",
                "over_rebuilds": "artifact rebuilt but byte-identical "
                                 "(wasted compute, not incorrect)",
                "builds": "total artifact rebuilds (cost proxy)",
                "wall_clock_est_s": "builds x calibration seconds per build kind",
            },
            "strategies": dict(STRATEGY_DESCRIPTIONS),
            "reproducibility": (
                "Ground truth is byte-level, so every step must decode "
                "reproducibly.  The SD6-10x noise setting is excluded from "
                "the log because at that saturated operating point both QUITS "
                "decoders give different outputs on identical inputs across "
                "calls (unseeded randomness inside ldpc's OSD/LSD "
                "tie-breaking); SD6 / SI1000 / SD6-0.1x are verified "
                "deterministic for both decoders on every code family used."),
            "expected_outcome": (
                "checker misses 0 on the QUITS model because R(extractor) "
                "already contains noise (H3); config_diff, logbook and "
                "declarative_naive miss the extractor's circuit/DEM/"
                "predictions on every noise-only step — the measured blind "
                "spot of both the git-diff practice and (identically, on "
                "those steps) the honest declarative-build practice, since "
                "the extractor->noise read is not declarable at the file "
                "interface.  declarative_naive still closes every miss "
                "caused by pipeline-visible coupling (its file edges catch "
                "the decoder's consumption of the circuit and the layout's "
                "consumption of the code), so it strictly improves on "
                "config_diff on the extractor-swap and code-port steps "
                "while paying almost nothing in over-rebuilds.  "
                "declarative_omniscient matches the checker's prediction: "
                "perfect declarations = the checker's information content."),
        },
        "sequence": sequence,
        "ground_truth": gt["rows"],
        "strategies": strategies,
        "summary": {
            "total_changed_artifact_steps": total_changed,
            "miss_rates": {n: s["miss_rate"] for n, s in strategies.items()},
        },
    }


def to_markdown(data: dict) -> str:
    m = data["metadata"]
    seq = data["sequence"]
    gt = data["ground_truth"]
    S = data["strategies"]
    L = ["# Declarative checking vs. real QEC re-computation practices", "",
         f"Generated: {m['date']}",
         f"Steps: {m['steps']} (baseline + {m['steps'] - 1} changes), "
         f"shots: {m['shots']} per prediction fingerprint, "
         f"rounds={m['num_rounds']}, seed={m['sampler_seed']}",
         f"Ground-truth measurement wall time: {m['ground_truth_wall_s']} s; "
         f"calibration (s/build): {m['calibration_seconds_per_build']}",
         ""]

    L += ["## Methodology — and how the circularity was removed", "",
          data["methodology"]["anti_circularity"], "",
          "Declared read sets used by the checker: "
          + ", ".join(f"R({k})={{{', '.join(v)}}}"
                      for k, v in m["read_sets_used"].items()
                      if isinstance(v, list)),
          "",
          "Reproducibility constraint: " + data["methodology"]["reproducibility"],
          ""]

    L += ["## 1. The research log (deterministic)", "",
          "| step | intent | code | extractor | arch | noise | decoder | changed dims | note |",
          "|---|---|---|---|---|---|---|---|---|"]
    for e in seq:
        sp = e["spec"]
        L.append(f"| {e['step']} | {e['intent'] or '-'} | {sp['code']} | {sp['extractor']} "
                 f"| {sp['arch']} | {sp['noise']} | {sp['decoder']} "
                 f"| {', '.join(e['changed_dimensions']) or '(baseline)'} | {e['note']} |")
    L.append("")

    L += ["## 2. Ground truth: which artifacts actually changed", "",
           "Byte-level fingerprints per step (C = changed vs previous step).", "",
           "| step | " + " | ".join(a.replace('_', ' ') for a in ALL_ARTIFACTS) + " |",
           "|---|" + "---|" * len(ALL_ARTIFACTS)]
    for r in gt:
        L.append(f"| {r['step']} | " + " | ".join(
            "C" if r["changed"][a] else "." for a in ALL_ARTIFACTS) + " |")
    L.append("")

    L += ["## 3. Per-strategy metrics", "",
          "| strategy | missed artifacts | miss rate | over-rebuilds | builds | est. wall-clock (s) |",
          "|---|---|---|---|---|---|"]
    for name in ("full_rerun", "config_diff", "declarative_naive",
                 "declarative_omniscient", "logbook", "checker"):
        t = S[name]["totals"]
        L.append(f"| {name} | **{t['missed']}** | {S[name]['miss_rate']:.4f} "
                 f"| {t['over_rebuilds']} | {t['builds']} | {t['wall_clock_est_s']:.2f} |")
    L += ["", "missed = artifact changed by ground truth but not rebuilt "
               "(stale artifact in use); over-rebuilds = rebuilt but "
               "byte-identical (wasted compute, still correct).", ""]

    L += ["## 4. Missed artifacts per step (the dangerous column)", "",
          "| step | intent | changed artifacts | full_rerun | config_diff | declarative_naive | declarative_omniscient | logbook | checker |",
          "|---|---|---|---|---|---|---|---|---|"]
    for i, e in enumerate(seq):
        row = lambda n: ", ".join(S[n]["per_step"][i]["missed"]) or "—"
        changed = ", ".join(a for a in ALL_ARTIFACTS if gt[i]["changed"][a]) or "—"
        L.append(f"| {e['step']} | {e['intent'] or '-'} | {changed} "
                 f"| {row('full_rerun')} | {row('config_diff')} "
                 f"| {row('declarative_naive')} | {row('declarative_omniscient')} "
                 f"| {row('logbook')} | {row('checker')} |")
    L += ["", "Over-rebuilds (rebuilt but byte-identical): "
          + "; ".join(f"{n}: {S[n]['totals']['over_rebuilds']}"
                      for n in ("full_rerun", "config_diff", "declarative_naive",
                                "declarative_omniscient", "logbook", "checker")),
          ""]

    L += ["## 5. Conclusion — declarative checking vs. git-diff, logbook and declarative-build practices", "",
          "| practice | missed artifacts | miss rate | vs checker |",
          "|---|---|---|---|"]
    checker_misses = S["checker"]["totals"]["missed"]
    for name in ("config_diff", "declarative_naive", "logbook", "full_rerun"):
        t = S[name]["totals"]
        L.append(f"| {name} | {t['missed']} | {S[name]['miss_rate']:.4f} "
                 f"| {'equal' if t['missed'] == checker_misses else 'worse'} |")
    L.append(f"| declarative_omniscient (perfect declarations) | "
             f"{S['declarative_omniscient']['totals']['missed']} "
             f"| {S['declarative_omniscient']['miss_rate']:.4f} "
             f"| {'equal' if S['declarative_omniscient']['totals']['missed'] == checker_misses else 'worse'} |")
    L.append(f"| checker (declared R(c)) | {checker_misses} "
             f"| {S['checker']['miss_rate']:.4f} | — |")
    L += ["",
          f"- On every **noise-only** step, `config_diff`, `logbook` and "
          f"`declarative_naive` keep using the extractor's stale "
          f"circuit/DEM/predictions: the declared spec diff shows only "
          f"`noise`, and the runtime read (extractor -> noise, finding H3) "
          f"is invisible to a config diff **and un-declarable for a "
          f"make/snakemake user** — `build_circuit` takes the error model "
          f"inside the component call, so the pipeline's file DAG has no "
          f"edge to declare.  The checker's declared read set "
          f"R(extractor) = {{code, extractor, noise}} catches exactly these "
          f"steps.",
          f"- The declarative-build practice is NOT the git-diff practice, "
          f"and the gap is measurable: an honest snakemake user wires the "
          f"pipeline's visible file flow (decoder consumes the circuit, "
          f"layout consumes the code), so `declarative_naive` closes every "
          f"miss that comes from that wiring — on this log it misses "
          f"{S['declarative_naive']['totals']['missed']} artifacts vs. "
          f"{S['config_diff']['totals']['missed']} for `config_diff` — "
          f"while paying almost nothing in extra over-rebuilds "
          f"({S['declarative_naive']['totals']['over_rebuilds']} vs. "
          f"{S['config_diff']['totals']['over_rebuilds']}).  What no honest "
          f"declaration can close is the intra-component read: on the "
          f"noise-only steps `declarative_naive` misses exactly what "
          f"`config_diff` misses.",
          f"- The upper bound confirms where the increment lives: "
          f"`declarative_omniscient` — a user whose declared coordinate "
          f"sets are the true ones — rebuilds exactly the checker's set "
          f"({S['declarative_omniscient']['totals']['builds']} builds, "
          f"{S['declarative_omniscient']['totals']['missed']} misses on "
          f"this log).  Perfect declarations and the checker's extracted "
          f"read sets carry the same information; source-level extraction "
          f"is the way to obtain them without omniscience.  This is the "
          f"empirical answer to 'what is an increment': the increment is "
          f"the runtime read set, which neither a spec diff nor an honest "
          f"file-level declaration recovers.",
          f"- The checker's cost is close to `config_diff`'s blind spot-free "
          f"ideal: it rebuilds only the impacted artifacts, so its over-rebuild "
          f"count is {S['checker']['totals']['over_rebuilds']} (vs. "
          f"{S['full_rerun']['totals']['over_rebuilds']} for the full re-run "
          f"baseline) while missing {checker_misses}.",
          "- Honest negatives: the decoder swap (BP-OSD -> BP-LSD) changes no "
          "byte of the 64-shot predictions on this subject — consistent with "
          "physical_impact's negative result — so every strategy that rebuilds "
          "predictions there over-rebuilds, none misses. The arch swap changes "
          "only the layout artifact: QUITS' build does not route arch into "
          "the circuit products, which is exactly the 'changed in the spec, "
          "unchanged in the circuit products' case, and no strategy is fooled "
          "by it.",
          ""]
    return "\n".join(L) + "\n"


def _ensure_hash_seed(argv: list[str] | None = None) -> int | None:
    """Re-run in a child interpreter with ``PYTHONHASHSEED=0``.

    QUITS' stim circuit text depends on Python's hash randomisation
    (``dynamic_impact.probe_hash_seed_sensitivity`` measures this), so the
    raw fingerprints recorded here are only reproducible under a pinned
    seed.  The *changed flags* — and therefore every metric in this
    experiment — are hash-seed-independent (ground truth compares steps
    within one process); pinning the seed only stabilises the fingerprint
    strings written to the JSON.  ``os.execve`` is avoided because it
    segfaults on Windows; a child process is used instead.  Returns the
    child's exit code, or ``None`` when no re-run is needed.
    """
    import os
    import subprocess

    if os.environ.get("PYTHONHASHSEED") == "0":
        return None
    env = dict(os.environ, PYTHONHASHSEED="0")
    script = str(Path(__file__).resolve())
    args = list(sys.argv[1:] if argv is None else argv)
    proc = subprocess.run([sys.executable, script, *args], env=env)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rc = _ensure_hash_seed(argv)
    if rc is not None:
        return rc
    out = outdir.resolve_out(argv, HERE)
    quick = "--quick" in argv
    n_steps = QUICK_STEPS if quick else DEFAULT_STEPS
    if "--steps" in argv:
        n_steps = int(argv[argv.index("--steps") + 1])
    shots = DEFAULT_SHOTS
    if "--shots" in argv:
        shots = int(argv[argv.index("--shots") + 1])

    data = run(n_steps=n_steps, shots=shots)
    (out / "practice_comparison.json").write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8")
    (out / "practice_comparison.md").write_text(to_markdown(data), encoding="utf-8")
    print(f"practice_comparison: {n_steps} steps x {shots} shots -> {out}")
    for name, s in data["strategies"].items():
        t = s["totals"]
        print(f"  {name:12s} missed={t['missed']:3d} over={t['over_rebuilds']:3d} "
              f"builds={t['builds']:3d} est_wall={t['wall_clock_est_s']:8.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
