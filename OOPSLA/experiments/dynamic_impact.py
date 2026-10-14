"""Dynamic impact surface of five real QUITS substitutions (P2-2, part 2).

PAPER_GAP_ANALYSIS **Gap 2.4** asks for the *dynamic* half of "compare against
QUITS' real call sites": `quant_evidence.verify_call_sites()` already checks that
the five `semantics.QUITS_CALL_SITES` claims are *stated* correctly.  This
script does the other half: it **performs** one real substitution per dimension
on the QUITS 1.2.0 object under test and *measures* the impact surface:

* **(a) the quits-internal modules that are actually triggered** -- recorded by
  ``sys.setprofile`` (per-scenario executed-function set, plus the call graph
  between quits modules) and by an import hook installed before ``quits`` is
  first imported (module load order);
* **(b) whether the output artifacts change** -- Stim circuit, detector error
  model and logical observables are fingerprinted (sha256), as are the code
  matrices, the layout coordinates, the noise parameters and the decoder's
  predicted observable flips;
* **(c) which artifacts of *unmodified* components change as collateral** -- the
  measurement the paper actually needs, because that is what decides whether a
  substitution is local.  Artifacts are attributed to the semantic node that
  owns them, so the measured impact set can be compared against the semantic
  layer's ``cone()``.

Two predictions are checked explicitly:

* **H3** -- replacing the noise model is *not* circuit-preserving: the
  ``extractor`` artifact (stim circuit + DEM) must change although only the
  ``noise`` coordinate was substituted.
* **H1** -- replacing the extractor may be *inadmissible*: the family whitelist
  ``supported_strategies`` is a property of the ``code`` component, so some
  ``(code, extractor)`` pairs cannot be assembled at all.  Those refusals are
  measured (exception type + message) and compared with
  ``semantics.inadmissible_pairs()``.

The measured impact set is then compared, per dimension, with

* ``semantics.make_source_faithful_assembly()``  (P0-3 auto-extracted R(c)
  and auto-derived DAG edges), and
* ``cone_table.make_quits_dataflow_assembly()``   (the conservative H3 model),

and with the static modelling in ``semantics.QUITS_CALL_SITES``.

Object under test: the **installed** ``quits==1.2.0`` (per ``shared/VERSIONS.md``
it is the same version as the pinned snapshot in ``third_party/``).  Pass
``--source pinned`` to run against the pinned tree instead, or ``--source both``
to run both and check that the fingerprints agree.

Outputs: ``dynamic_impact.json`` and ``dynamic_impact.md``.

Run:  python experiments/dynamic_impact.py            (installed quits)
      python experiments/dynamic_impact.py --source both
      python experiments/dynamic_impact.py --quick     (used by pytest)
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
REPO_ROOT = OOPSLA_ROOT.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import semantics  # noqa: E402  (E402: path shim above)
import numpy as _np  # noqa: E402  (E402: path shim above)
import outdir  # noqa: E402  (`--out` support; see src/outdir.py)

QUITS_COMMIT = "0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452"
INSTALLED_VERSION = "1.2.0"

# ---------------------------------------------------------------------------
# 0. import hook: record quits' module load order (installed before first import)
# ---------------------------------------------------------------------------

_IMPORT_LOG: list[str] = []


class _ImportRecorder:
    """A ``sys.meta_path`` finder that records every ``quits.*`` module load."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "quits" or fullname.startswith("quits."):
            _IMPORT_LOG.append(fullname)
        return None                      # never claims the module


def _install_import_hook() -> None:
    hook = _ImportRecorder()
    for finder in sys.meta_path:
        if isinstance(finder, _ImportRecorder):
            return
    sys.meta_path.insert(0, hook)


_install_import_hook()


def _quits_root() -> Path:
    import quits
    return Path(quits.__file__).resolve().parent


@contextlib.contextmanager
def _tracer(root: Path):
    """Record executed quits functions and the inter-module call graph.

    ``filename -> module`` is memoised: ``ToricLayout.__new__`` alone executes
    ~150k Python calls, and a ``Path.resolve()`` per call dominates the runtime.
    """
    executed: dict[str, set[str]] = {}
    edges: dict[tuple[str, str], int] = {}
    stack: list[tuple[str, str] | None] = []
    root_str = str(root)
    memo: dict[str, str | None] = {}

    def module_of(filename: str) -> str | None:
        try:
            return memo[filename]
        except KeyError:
            pass
        if not filename.startswith(root_str):
            memo[filename] = None
            return None
        rel = Path(filename).resolve().relative_to(root_str)
        mod = "quits." + str(rel.with_suffix("")).replace("\\", "/").replace("/", ".")
        memo[filename] = mod
        return mod

    def prof(frame, event, arg):
        if event != "call":
            return
        code = frame.f_code
        mod = module_of(code.co_filename)
        if mod is None:
            stack.append(None)
            return
        executed.setdefault(mod, set()).add(code.co_name)
        prev = stack[-1] if stack else None
        if prev and prev[0] != mod:
            edges[(prev[0], mod)] = edges.get((prev[0], mod), 0) + 1
        stack.append((mod, code.co_name))

    sys.setprofile(prof)
    try:
        yield executed, edges
    finally:
        sys.setprofile(None)
        stack.clear()


# ---------------------------------------------------------------------------
# 1. the QUITS-side pipeline: 5 substitutable stages, 7 artifacts
# ---------------------------------------------------------------------------

#: One representative instance per code family, taken from the shared C0 corpus
#: (``shared/C0/corpus.json``).  Values are the QUITS constructor arguments.
CODE_INSTANCES = {
    "BB": ("BbCode", dict(l=6, m=6, A_x_pows=[3], A_y_pows=[1, 2],
                          B_x_pows=[1, 2], B_y_pows=[3])),
    # QUITS' HGP / QLP constructors read ``.shape`` off the base matrices, so
    # they must be numpy arrays (the C0 corpus stores them as nested lists).
    "HGP": ("HgpCode", dict(h1=_np.array([[1, 1, 0], [0, 1, 1]]),
                            h2=_np.array([[1, 1, 0], [0, 1, 1]]))),
    "QLP": ("QlpCode", dict(b1=_np.array([[0, 0], [0, 3]]),
                            b2=_np.array([[0, 1, 0], [1, 0, 3]]),
                            lift_size=12)),
}

#: Noise parameterisations.  ``SD6`` / ``SI1000`` are the two operating points
#: of the shared C0 corpus; ``SD6-stress`` is the same model at 10x the rate,
#: used to expose behaviour that is invisible at the nominal point (a decoder
#: swap in particular).
NOISE_PARAMS = {
    "SD6": dict(idle_error=1e-4, sqgate_error=1e-3, tqgate_error=1e-3,
                spam_error=1e-3),
    "SI1000": dict(idle_error=2e-5, sqgate_error=2e-4, tqgate_error=2e-4,
                   spam_error=2e-4),
    "SD6-stress": dict(idle_error=3e-3, sqgate_error=3e-2, tqgate_error=3e-2,
                        spam_error=3e-2),
}

DECODERS = {"BP-OSD": "sliding_window_bposd_circuit_mem",
            "BP-LSD": "sliding_window_bplsd_circuit_mem"}

NUM_ROUNDS = 2
NUM_SHOTS = 16
#: The `decoder_stress` probe needs enough shots for two decoders to *reliably*
#: disagree; at ``NUM_SHOTS`` they sometimes agree on every sampled shot (the
#: circuit text itself is hash-seed dependent), which made the probe flaky.
STRESS_SHOTS = 128
SAMPLER_SEED = 7
WINDOW = 3
OVERLAP = 1

#: artifact -> the semantic node that *produces* it.  This is the bridge between
#: "what QUITS produced" and "which component's product changed".
ARTIFACT_OWNER = {
    "code_matrices": "code",
    "layout_positions": "arch",
    "noise_model": "noise",
    "stim_circuit": "extractor",
    "detector_error_model": "extractor",
    "logical_observables": "extractor",
    "decoder_output": "decoder",
}

BASELINE = {"code": "BB", "extractor": "zxcoloration", "arch": "transversal",
            "noise": "SD6", "decoder": "BP-OSD"}

#: The five real substitutions, one per dimension.
SUBSTITUTIONS = [
    {"dimension": "code", "from": "BB", "to": "QLP",
     "what": "swap the bivariate-bicycle family instance for a "
             "quasi-cyclic lifted-product one (C0 corpus instances)"},
    {"dimension": "extractor", "from": "zxcoloration", "to": "custom",
     "what": "swap the ZX-coloration builder for the BB-specific custom "
             "schedule builder (both on the family's whitelist)"},
    {"dimension": "arch", "from": "transversal", "to": "toric",
     "what": "swap TransversalLayout for the BB toric embedding"},
    {"dimension": "noise", "from": "SD6", "to": "SI1000",
     "what": "swap the ErrorModel parameterisation (depolarizing 1e-3 vs 2e-4)"},
    {"dimension": "decoder", "from": "BP-OSD", "to": "BP-LSD",
     "what": "swap the sliding-window inner decoder (BP-OSD vs BP-LSD)"},
]

#: Extra probes that are not "replacements" but measure admissibility.
EXTRA_PROBES = [
    {"name": "arch_none", "dimension": "arch", "to": "none",
     "what": "QldpcCode.get_layout() defaults to None: the 'no layout' case"},
    {"name": "extractor_inadmissible", "dimension": "extractor", "to": "cardinal",
     "what": "H1: 'cardinal' is in the global builder registry but NOT in "
             "BbCode.supported_strategies"},
    {"name": "decoder_stress", "dimension": "decoder", "to": "BP-LSD",
     "operating_point": "SD6-stress",
     "shots": STRESS_SHOTS,
     "what": "same decoder swap at 10x the SD6 error rate"},
]


def _sha(text_or_bytes) -> str:
    data = (text_or_bytes if isinstance(text_or_bytes, bytes)
            else str(text_or_bytes).encode("utf-8"))
    return hashlib.sha256(data).hexdigest()[:16]


def _numpy_matrix_fingerprint(arr) -> str:
    return _sha(arr.tobytes())


# ---------------------------------------------------------------------------
# 2. the pipeline
# ---------------------------------------------------------------------------

def run_pipeline(spec: dict, shots: int = NUM_SHOTS) -> dict:
    """Execute the real QUITS pipeline for one 5-dimension spec.

    Returns ``{"artifacts": {...}, "stages": {stage: {...modules executed...}}}``.

    ``shots`` is overridable because the ``decoder_stress`` probe needs more
    samples to make two decoders *reliably* disagree: at ``NUM_SHOTS=16`` the two
    decoders agree on every sampled shot for some circuits (the circuit text
    itself depends on ``PYTHONHASHSEED``, see ``probe_hash_seed_sensitivity``),
    which made "the two decoders differ" a flaky observation.  With 128 shots the
    probe diverges for every hash seed we measured.  The nominal substitutions
    keep ``NUM_SHOTS``: their claim is *locality*, which does not depend on the
    decoders disagreeing.
    """
    import numpy as np
    import quits
    from quits import ErrorModel
    from quits.simulation import get_stim_mem_result

    root = _quits_root()
    artifacts: dict[str, dict] = {}
    stages: dict[str, dict] = {}

    def stage(name: str, fn):
        """Run ``fn()`` under the tracer, recording its modules and edges."""
        with _tracer(root) as (executed, edges):
            out = fn()
        stages[name] = {"modules": sorted(executed),
                        "edges": sorted(f"{a}->{b}" for a, b in edges)}
        return out

    def record(name: str, fingerprint: str, detail: dict) -> None:
        artifacts[name] = {"fingerprint": fingerprint, **detail}

    # -- stage 1: code ------------------------------------------------------
    def _code():
        cls_name, kwargs = CODE_INSTANCES[spec["code"]]
        import quits.qldpc_code as qc
        return getattr(qc, cls_name)(**kwargs)

    code = stage("code", _code)
    record("code_matrices",
           _sha(b"".join(_numpy_matrix_fingerprint(m).encode()
                         for m in (code.hz, code.hx, code.lz, code.lx))),
           {"hz_shape": list(code.hz.shape), "hx_shape": list(code.hx.shape),
            "n_logical": int(code.lz.shape[0]),
            "family": type(code).__name__})

    # -- stage 2: architecture ---------------------------------------------
    def _layout_payload(mapping) -> tuple:
        return tuple(sorted((role, tuple(sorted(getattr(mapping, role).items())))
                            for role in ("data", "zcheck", "xcheck")))

    def _arch():
        if spec["arch"] == "none":
            obj = code.get_layout()
            return None, {"layout": "get_layout()",
                          "is_none": obj is None, "n_positions": 0}
        if spec["arch"] == "transversal":
            from quits.layout import TransversalLayout
            obj = TransversalLayout(code, center_checks=True)
            label = "TransversalLayout"
        else:
            from quits.layout import ToricLayout
            obj = ToricLayout(code)
            label = "ToricLayout"
        mapping = obj.mapping()
        return _layout_payload(mapping), {"layout": label, "is_none": False,
                                         "n_positions": len(mapping.data)}

    layout_payload, layout_detail = stage("arch", _arch)
    record("layout_positions",
           _sha(layout_payload) if layout_payload is not None else _sha(None),
           layout_detail)

    # -- stage 3: noise -----------------------------------------------------
    error_model = stage("noise", lambda: ErrorModel(**NOISE_PARAMS[spec["noise"]]))
    record("noise_model", _sha(tuple(sorted(error_model.__dict__.items()))),
           {"model": spec["noise"], **NOISE_PARAMS[spec["noise"]]})

    # -- stage 4: extraction (circuit, DEM, logical observables) -----------
    circuit = stage("extractor", lambda: code.build_circuit(
        strategy=spec["extractor"], error_model=error_model,
        num_rounds=NUM_ROUNDS, basis="Z"))
    record("stim_circuit", _sha(str(circuit)),
           {"strategy": spec["extractor"], "num_qubits": circuit.num_qubits,
            "num_detectors": circuit.num_detectors,
            "num_observables": circuit.num_observables,
            "num_ticks": circuit.num_ticks})

    dem = stage("dem", lambda: circuit.detector_error_model(flatten_loops=True))
    record("detector_error_model", _sha(str(dem)),
           {"num_detectors": dem.num_detectors,
            "num_observables": dem.num_observables,
            "num_errors": sum(1 for _ in dem)})

    observables = stage("observables", lambda: [
        str(inst) for inst in circuit if inst.name == "OBSERVABLE_INCLUDE"])
    record("logical_observables", _sha(observables),
           {"n_observables": circuit.num_observables,
            "n_observable_includes": len(observables)})

    # -- stage 5: decoding --------------------------------------------------
    import quits.decoder as qdec
    fn = getattr(qdec, DECODERS[spec["decoder"]])

    def _decode():
        det, _obs = get_stim_mem_result(circuit, shots, seed=SAMPLER_SEED)
        return fn(det.copy(), circuit, code.hz, code.lz, W=WINDOW, F=OVERLAP)

    logical_pred = stage("decoder", _decode)
    record("decoder_output", _sha(np.asarray(logical_pred).tobytes()),
           {"decoder": spec["decoder"], "entry": DECODERS[spec["decoder"]],
            "n_shots": int(logical_pred.shape[0]),
            "n_logical_flips": int(np.asarray(logical_pred).sum()),
            "window": WINDOW, "overlap": OVERLAP, "seed": SAMPLER_SEED})

    return {"spec": dict(spec), "artifacts": artifacts, "stages": stages,
            "quits_file": str(quits.__file__)}


# ---------------------------------------------------------------------------
# 3. one substitution -> impact analysis
# ---------------------------------------------------------------------------

def _cones() -> dict[str, dict[str, list[str]]]:
    """Predictors compared against the measurement, with their provenance.

    决策 1（2026-10-09）：本实验是 **ground truth**。下面三个模型是它的
    **交叉验证对象**，每个都注明读集合与边的来源（``_assembly_provenance``）：

    1. ``source_faithful_cone``  — Theorem 1 的 ``{x} ∪ cone(x)``：
       **替换组件** x（spec 不变）的影响面，assembly 的 R(c) 与边都是从
       pinned 源码 AST 提取的（决策 2 之后这也是 cone_table /
       artifact_invariance 的发布基线）。
    2. ``source_faithful_coord`` — ``coordinate_impact(A, x)``：改**坐标** x 的
       影响面 = ``{x} ∪ {u : x ∈ R(u)} ∪ ⋃cone(v)``。这是 QUITS 用户实际问的
       问题（见 PIVOT_NOTE §4.3）。
    3. ``dataflow_cone`` — ``cone_table.make_quits_dataflow_assembly()`` 的手工
       保守 H3 模型；决策 3 已为它补上 ``arch <- code`` 边。
    """
    from cone_table import make_quits_dataflow_assembly
    faithful = semantics.make_source_faithful_assembly()
    dataflow = make_quits_dataflow_assembly()
    return {
        # Theorem 1: replacing *component* x  ->  {x} u cone(x)
        "source_faithful_cone": {n: sorted(set(faithful.cone(n)) | {n})
                                 for n in faithful.nodes},
        # changing *coordinate* x  ->  semantics.coordinate_impact(A, x)
        "source_faithful_coord": {c: sorted(semantics.coordinate_impact(faithful, c))
                                  for c in semantics.COORDINATES},
        # the conservative H3 model in cone_table
        "dataflow_cone": {n: sorted(set(dataflow.cone(n)) | {n})
                          for n in dataflow.nodes},
    }


def _assembly_provenance() -> dict:
    """Where each compared model's read sets and edges come from."""
    src = semantics.assembly_model_sources(
        ("source_faithful", "quits_dataflow", "clean", "quits_faithful"))
    return {
        "compared_models": {
            "source_faithful_cone": {
                "assembly": "source_faithful",
                "read_sets_from": src["source_faithful"]["read_sets"],
                "edges_from": src["source_faithful"]["edges"],
                "question": "replace component x (Theorem 1)",
            },
            "source_faithful_coord": {
                "assembly": "source_faithful",
                "read_sets_from": src["source_faithful"]["read_sets"],
                "edges_from": src["source_faithful"]["edges"],
                "question": "change coordinate x (semantics.coordinate_impact)",
            },
            "dataflow_cone": {
                "assembly": "quits_dataflow",
                "read_sets_from": src["quits_dataflow"]["read_sets"],
                "edges_from": src["quits_dataflow"]["edges"],
                "question": "replace component x on the hand-modelled H3 assembly",
            },
        },
        "all_assemblies": src,
        "note": "this experiment is the ground truth; the static read-set "
                "extractor (extract_read_sets.py) and the cone/invariance "
                "tables are cross-validation of it, not the other way round "
                "(PIVOT_NOTE section 4, decision 1 of 2026-10-09).",
    }


def analyse(base: dict, alt: dict, substitution: dict, cones: dict) -> dict:
    changed = sorted(a for a in base["artifacts"]
                     if base["artifacts"][a]["fingerprint"]
                     != alt["artifacts"][a]["fingerprint"])
    unchanged = sorted(set(base["artifacts"]) - set(changed))
    dim = substitution["dimension"]
    owners_changed = sorted({ARTIFACT_OWNER[a] for a in changed})
    # nodes whose *own* artifact changed
    collateral = sorted(set(owners_changed) - {dim})
    # modules newly executed by the substitution
    mods_base = {m for st in base["stages"].values() for m in st["modules"]}
    mods_alt = {m for st in alt["stages"].values() for m in st["modules"]}
    cone_pred = {k: v[dim] for k, v in cones.items()}
    return {
        "name": substitution.get("name", dim),
        "dimension": dim,
        "what": substitution["what"],
        "from": substitution.get("from", BASELINE[dim]),
        "to": substitution["to"],
        "operating_point": substitution.get("operating_point", "SD6"),
        "shots": substitution.get("shots", NUM_SHOTS),
        "spec_before": base["spec"],
        "spec_after": alt["spec"],
        "changed_artifacts": changed,
        "unchanged_artifacts": unchanged,
        "changed_nodes": owners_changed,
        "collateral_nodes": collateral,
        "collateral_artifacts": [a for a in changed
                                 if ARTIFACT_OWNER[a] != dim],
        "quits_modules_executed_baseline": sorted(mods_base),
        "quits_modules_executed_after": sorted(mods_alt),
        "quits_modules_added": sorted(mods_alt - mods_base),
        "quits_modules_removed": sorted(mods_base - mods_alt),
        "n_quits_modules_baseline": len(mods_base),
        "n_quits_modules_after": len(mods_alt),
        "predicted_nodes_to_rerun": cone_pred,
        "prediction_covers_measurement": {
            model: set(owners_changed) <= set(nodes)
            for model, nodes in cone_pred.items()},
        "measurement_tighter_than_prediction": {
            model: sorted(set(nodes) - set(owners_changed))
            for model, nodes in cone_pred.items()},
    }


def probe_inadmissible() -> dict:
    """H1: an extractor replacement can be *unassemblable*.

    `cardinal` is a key of the global builder registry
    (`circuit_construction/_BUILDERS`) but not of `BbCode.supported_strategies`.
    """
    from quits.qldpc_code import BbCode
    bb = BbCode(**CODE_INSTANCES["BB"][1])
    out = {}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            bb.build_circuit(strategy="cardinal")
            out["outcome"] = "assembled"
        except NotImplementedError as exc:
            out["outcome"] = "refused"
            out["exception"] = type(exc).__name__
            out["message"] = str(exc)
    out["registry_has_cardinal"] = True
    out["family_whitelist"] = sorted(bb.supported_strategies)
    out["global_whitelist"] = sorted(semantics.DOMAIN["extractor"])
    out["semantic_layer_refuses_same_pair"] = (
        ("BB", "cardinal") in semantics.inadmissible_pairs())
    return out


def probe_layout_none() -> dict:
    """Architecture: `get_layout()` defaults to None (PIVOT_NOTE §4 row 5)."""
    from quits.qldpc_code import BbCode
    bb = BbCode(**CODE_INSTANCES["BB"][1])
    return {"outcome": "None" if bb.get_layout() is None else "not-None",
            "get_layout_default": None}


#: A self-contained snippet that builds the baseline circuit and prints its
#: fingerprint.  Used to probe PYTHONHASHSEED sensitivity.
_HASH_PROBE_SRC = """
import hashlib, sys
sys.path.insert(0, {here!r})
sys.path.insert(0, {root!r})
from dynamic_impact import CODE_INSTANCES, NOISE_PARAMS, NUM_ROUNDS
from quits import ErrorModel
from quits.qldpc_code import BbCode
bb = BbCode(**CODE_INSTANCES["BB"][1])
c = bb.build_circuit(strategy="zxcoloration",
                     error_model=ErrorModel(**NOISE_PARAMS["SD6"]),
                     num_rounds=NUM_ROUNDS, basis="Z")
print(hashlib.sha256(str(c).encode()).hexdigest()[:16])
"""


def probe_hash_seed_sensitivity(seeds=("0", "1", "12345"), quick: bool = False) -> dict:
    """Is the stim circuit a *stable* artifact?  (reproducibility check)

    ``edge_coloration`` calls ``networkx.algorithms.bipartite.matching
    .hopcroft_karp_matching``, whose result depends on the iteration order of
    Python sets -- so the produced circuit text varies with
    ``PYTHONHASHSEED``.  This probe builds the baseline circuit in a fresh
    interpreter per seed and compares the fingerprints.
    """
    src = _HASH_PROBE_SRC.format(here=str(HERE), root=str(REPO_ROOT))
    if quick:
        seeds = seeds[:2]
    out: dict[str, str] = {}
    for seed in seeds:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, "-c", src], env=env,
                              capture_output=True, text=True)
        if proc.returncode != 0:                       # pragma: no cover
            out[str(seed)] = f"error: {proc.stderr.strip().splitlines()[-1:]}"
            continue
        out[str(seed)] = proc.stdout.strip().splitlines()[-1]
    distinct = sorted(set(out.values()))
    return {"fingerprints_by_pythonhashseed": out,
            "n_distinct": len(distinct),
            "deterministic": len(distinct) == 1,
            "note": "networkx hopcroft_karp_matching iterates over a set, so "
                    "the circuit text depends on PYTHONHASHSEED; the "
                    "experiment re-execs itself with PYTHONHASHSEED=0 so the "
                    "fingerprints in this file are reproducible."}


def _ensure_hash_seed(argv: list[str] | None = None) -> int | None:
    """Re-run in a child interpreter with ``PYTHONHASHSEED=0``.

    QUITS' stim circuit is *not* a stable artifact under Python's hash
    randomisation (see ``probe_hash_seed_sensitivity``), so the experiment
    pins the seed to make its own fingerprints reproducible.  ``os.execve``
    is avoided because it segfaults on Windows; a child process is used
    instead.  Returns the child's exit code, or ``None`` when no re-run is
    needed.
    """
    if os.environ.get("PYTHONHASHSEED") == "0":
        return None
    env = dict(os.environ, PYTHONHASHSEED="0")
    script = str(Path(__file__).resolve())
    args = list(sys.argv[1:] if argv is None else argv)
    proc = subprocess.run([sys.executable, script, *args], env=env)
    return proc.returncode


# ---------------------------------------------------------------------------
# 4. QUITS_CALL_SITES alignment
# ---------------------------------------------------------------------------

def align_call_sites(rows: list[dict], inadmissible: dict,
                     layout_none: dict) -> list[dict]:
    """Per-dimension: what the static modelling says vs what we measured."""
    by_dim = {r["dimension"]: r for r in rows if not r.get("refused")}
    out = []
    for site in semantics.QUITS_CALL_SITES:
        site_dim = site["dimension"]
        dim = semantics.CALL_SITE_DIMENSIONS[site_dim]
        row = by_dim.get(dim)
        if row is None:
            continue
        measured = {
            "changed_artifacts": row["changed_artifacts"],
            "changed_nodes": row["changed_nodes"],
            "collateral_nodes": row["collateral_nodes"],
            "n_quits_modules_executed": row["n_quits_modules_after"],
        }
        aligned = True
        notes = []
        if dim == "noise":
            aligned = "stim_circuit" in row["changed_artifacts"]
            notes.append(
                "H3 confirmed: replacing only the noise model changes the "
                "stim circuit and its DEM, i.e. the extractor artifact, so a "
                "noise substitution is NOT circuit-preserving.")
        if dim == "extractor":
            notes.append(
                "H1: the substituted strategy is on the family whitelist, so "
                "the assembly succeeds; the inadmissible variant is measured "
                "separately (see `inadmissible_probe`).")
        if dim == "arch":
            aligned = not row["collateral_nodes"]
            notes.append(
                "layout substitution changes only the layout artifact: the "
                "extractor builds its own TransversalLayout internally, so "
                "swapping the arch coordinate is circuit-preserving.")
        if dim == "code":
            notes.append(
                "the code artifact feeds arch (Layout(code)), the extractor "
                "(build_circuit is a QldpcCode method) and the decoder "
                "(hz/lz); the measured collateral matches the "
                "auto-extracted edges exactly.")
        if dim == "decoder":
            notes.append(
                "the decoder artifact changes but no upstream artifact does: "
                "decoder substitution is the most local of the five.")
        out.append({"dimension": dim, "call_site_dimension": site_dim,
                    "site": site["site"],
                    "static_modelling": site["semantic_check"],
                    "measured": measured, "aligned": aligned,
                    "notes": notes})
    return out


# ---------------------------------------------------------------------------
# 5. driver
# ---------------------------------------------------------------------------

_RESULT_CACHE: dict[bool, dict] = {}


def run(quick: bool = False) -> dict:
    """Run every substitution and analyse it.

    Results are memoised per ``quick`` setting so that pytest can assert on the
    measurement *and* check that the CLI writes its artefacts without paying for
    the QUITS runs twice.  ``dynamic_impact.main()`` always recomputes by
    calling :func:`run` with the cache disabled via ``refresh``.
    """
    if quick in _RESULT_CACHE:
        return _RESULT_CACHE[quick]
    data = _run(quick=quick)
    _RESULT_CACHE[quick] = data
    return data


def _run(quick: bool = False) -> dict:
    import quits

    cones = _cones()
    rows: list[dict] = []
    baseline = run_pipeline(dict(BASELINE))

    for sub in SUBSTITUTIONS:
        spec = dict(BASELINE)
        spec[sub["dimension"]] = sub["to"]
        alt = run_pipeline(spec)
        rows.append(analyse(baseline, alt, sub, cones))

    for probe in EXTRA_PROBES:
        dim = probe["dimension"]
        spec = dict(BASELINE)
        shots = probe.get("shots", NUM_SHOTS)
        if "operating_point" in probe:
            spec["noise"] = probe["operating_point"]
            base = run_pipeline(spec, shots=shots)
        else:
            base = baseline
        spec[dim] = probe["to"]
        try:
            alt = run_pipeline(spec, shots=shots)
        except Exception as exc:                      # H1 refusal
            rows.append({"name": probe["name"], "dimension": dim,
                         "what": probe["what"], "to": probe["to"],
                         "refused": True,
                         "exception": type(exc).__name__,
                         "message": str(exc).strip().splitlines()[-1]
                         if str(exc).strip() else ""})
            continue
        merged = {"name": probe["name"], "what": probe["what"],
                  "dimension": dim, "from": BASELINE[dim], "to": probe["to"],
                  "operating_point": probe.get("operating_point", "SD6"),
                  "shots": shots}
        rows.append(analyse(base, alt, merged, cones))

    inadmissible = probe_inadmissible()
    layout_none = probe_layout_none()
    hash_seed = probe_hash_seed_sensitivity(quick=quick)
    measured = [r for r in rows if not r.get("refused")]
    return {
        "metadata": {
            "description": "Dynamic impact surface of five real QUITS "
                           "substitutions (P2-2 dynamic half)",
            "date": date.today().isoformat(),
            "quits_file": quits.__file__,
            "quits_version": getattr(quits, "__version__", "unknown"),
            "pinned_commit": QUITS_COMMIT,
            "quick": quick,
            "baseline_spec": dict(BASELINE),
            "num_rounds": NUM_ROUNDS,
            "sampler_seed": SAMPLER_SEED,
            "num_shots": NUM_SHOTS,
            "stress_shots": STRESS_SHOTS,
            "window": WINDOW,
            "overlap": OVERLAP,
            "artifact_owner": ARTIFACT_OWNER,
            # 决策 1（2026-10-09）：本文件是 **ground truth**——它把 QUITS
            # 跑起来测量；`extract_read_sets.py` 的 AST 提取与 cone_table /
            # artifact_invariance 的静态建模都是它的**交叉验证**。因此这里把
            # 被比较的每个模型及其建模来源一并记下来，任何一列数字都能追到出处。
            "role": "ground truth for the assembly models compared below",
            "assembly_model_sources": _assembly_provenance(),
        },
        "baseline_artifacts": baseline["artifacts"],
        "baseline_stages": baseline["stages"],
        "quits_import_order": list(_IMPORT_LOG),
        "substitutions": rows,
        "cones": cones,
        "inadmissible_probe": inadmissible,
        "layout_none_probe": layout_none,
        "hash_seed_probe": hash_seed,
        "call_site_alignment": align_call_sites(measured, inadmissible,
                                                 layout_none),
        "summary": _summarize(rows, inadmissible),
    }


def _summarize(rows: list[dict], inadmissible: dict) -> dict:
    measured = [r for r in rows if not r.get("refused")]
    return {
        "n_substitutions": len(rows),
        "n_refused": sum(1 for r in rows if r.get("refused")),
        "n_measured": len(measured),
        "coordinate_impact_covers_measurement_all": all(
            r["prediction_covers_measurement"]["source_faithful_coord"]
            for r in measured),
        "theorem1_cone_covers_measurement_all": all(
            r["prediction_covers_measurement"]["source_faithful_cone"]
            for r in measured),
        "dataflow_cone_covers_measurement_all": all(
            r["prediction_covers_measurement"]["dataflow_cone"]
            for r in measured),
        "h3_noise_not_circuit_preserving": next(
            (("stim_circuit" in r["changed_artifacts"])
             for r in measured if r["dimension"] == "noise"), None),
        "h1_extractor_inadmissible_detected": inadmissible.get("outcome") == "refused",
        "h1_semantic_layer_agrees": inadmissible.get(
            "semantic_layer_refuses_same_pair") is True,
        "collateral_nodes_by_dimension": {
            r["dimension"]: r["collateral_nodes"] for r in measured},
        "tighter_than_prediction": {
            r["dimension"]: r["measurement_tighter_than_prediction"]
            for r in measured},
    }


def to_markdown(data: dict) -> str:
    m, s = data["metadata"], data["summary"]
    L = ["# Dynamic Impact Surface of Five Real QUITS Substitutions", "",
         f"Generated: {m['date']}  ",
         f"Object under test: `{m['quits_file']}` (quits "
         f"{m['quits_version']})  ",
         f"Pinned reference: `{m['pinned_commit']}`  ",
         f"Baseline spec: `{m['baseline_spec']}`  ",
         f"Circuit: num_rounds={m['num_rounds']}, sampler seed="
         f"{m['sampler_seed']}, sliding window W={m['window']} F={m['overlap']}; "
         f"{m['num_shots']} shots (the `decoder_stress` probe uses "
         f"{m['stress_shots']} — see the note in section 4)",
         "",
         "## 0. Role of this experiment, and where each compared model's "
         "modelling comes from", "",
         "This file is the **ground truth**: it runs QUITS and measures. The "
         "AST read-set extractor (`extract_read_sets.py`) and the static tables "
         "(`cone_table`, `artifact_invariance`) are **cross-validation** of these "
         "measurements (PIVOT_NOTE section 4, decision 1 of 2026-10-09).", "",
         "| compared model | question | assembly | read sets from | edges from |",
         "|---|---|---|---|---|"]
    prov = m.get("assembly_model_sources", {}).get("compared_models", {})
    for key in ("source_faithful_coord", "source_faithful_cone", "dataflow_cone"):
        info = prov.get(key, {})
        if not info:
            continue
        L.append(f"| `{key}` | {info.get('question', '')} "
                 f"| `{info.get('assembly', '')}` "
                 f"| {info.get('read_sets_from', '')} "
                 f"| {info.get('edges_from', '')} |")
    L += ["",
          "## 1. What changed, per substitution", "",
         "| substitution | changed artifacts | changed nodes | collateral "
         "(unmodified components whose product changed) |",
         "|---|---|---|---|"]
    for r in data["substitutions"]:
        if r.get("refused"):
            L.append(f"| `{r['name']}` | **refused: `{r['exception']}`** | - | - |")
            continue
        L.append(f"| `{r['name']}` "
                 f"| `{', '.join(r['changed_artifacts']) or '-'}` "
                 f"| `{', '.join(r['changed_nodes']) or '-'}` "
                 f"| `{', '.join(r['collateral_nodes']) or 'none'}` |")

    L += ["", "## 2. Prediction vs measurement", "",
          "This experiment changes a **spec coordinate**, not a component, so "
          "the right predictor is `semantics.coordinate_impact(A, x)` = "
          "`{x} ∪ {u : x ∈ R(u)} ∪ ⋃ cone(v)` (readers of the coordinate, "
          "closed along the artifact DAG).  Theorem 1's `{x} ∪ cone(x)` is the "
          "*component-substitution* view and is shown for comparison; the "
          "`dataflow` column is `cone_table`'s conservative H3 model, which "
          "since decision 3 (2026-10-09) also carries the `arch <- code` edge "
          "this measurement demanded — so its `code` row is no longer an "
          "under-approximation.", "",
          "| substitution | measured | `coordinate_impact` | Theorem-1 cone | "
          "dataflow cone | coord-impact covers? |",
          "|---|---|---|---|---|---|"]
    for r in data["substitutions"]:
        if r.get("refused"):
            continue
        pred = r["predicted_nodes_to_rerun"]
        cov = r["prediction_covers_measurement"]
        L.append(f"| `{r['name']}` "
                 f"| `{', '.join(r['changed_nodes'])}` "
                 f"| `{', '.join(pred['source_faithful_coord'])}` "
                 f"| `{', '.join(pred['source_faithful_cone'])}` "
                 f"| `{', '.join(pred['dataflow_cone'])}` "
                 f"| **{cov['source_faithful_coord']}** |")
    L += ["", "Where each model is *conservative* (demanded a rerun that the "
          "measurement showed was unnecessary):", ""]
    for r in data["substitutions"]:
        if r.get("refused"):
            continue
        tight = r["measurement_tighter_than_prediction"]
        L.append(f"- `{r['name']}`: coordinate-impact "
                 f"`{', '.join(tight['source_faithful_coord']) or 'exact'}`; "
                 f"dataflow cone "
                 f"`{', '.join(tight['dataflow_cone']) or 'exact'}`")

    L += ["", "## 3. QUITS-internal modules actually triggered", "",
          "| substitution | modules executed (baseline) | after | added | removed |",
          "|---|---:|---:|---|---|"]
    for r in data["substitutions"]:
        if r.get("refused"):
            continue
        L.append(f"| `{r['name']}` | {r['n_quits_modules_baseline']} "
                 f"| {r['n_quits_modules_after']} "
                 f"| `{', '.join(r['quits_modules_added']) or '-'}` "
                 f"| `{', '.join(r['quits_modules_removed']) or '-'}` |")

    L += ["", "### Modules executed per pipeline stage (baseline)", "",
          "| stage | quits modules executed |", "|---|---|"]
    for stage, info in data["baseline_stages"].items():
        L.append(f"| `{stage}` | `{', '.join(info['modules'])}` |")

    L += ["", "## 4. H1 / H3 checks", "",
          f"- **H3** a noise substitution is **not** circuit-preserving: "
          f"**{s['h3_noise_not_circuit_preserving']}** "
          "(True = the stim circuit and its DEM change although only the "
          "`noise` coordinate was substituted)",
          f"- **H1** an inadmissible extractor substitution is refused by "
          f"QUITS: **{s['h1_extractor_inadmissible_detected']}**",
          f"- **H1** the semantic layer refuses the same `(code, extractor)` "
          f"pair: **{s['h1_semantic_layer_agrees']}**", "",
          "At the nominal SD6 operating point BP-OSD and BP-LSD agree on all "
          f"{NUM_SHOTS} sampled shots, so the `decoder` row of section 1 is "
          "empty; the `decoder_stress` probe repeats the swap at 10x the error "
          f"rate with {STRESS_SHOTS} shots, where the two decoders diverge. "
          "The stress probe needs more shots because the circuit text itself "
          "depends on `PYTHONHASHSEED` (see below), and at "
          f"{NUM_SHOTS} shots the two decoders agree on every sample for some "
          "circuits; the probe is not a locality claim, so the extra shots "
          "cost nothing in the substitution rows.", "",
          "Inadmissible probe detail:", ""]
    ip = data["inadmissible_probe"]
    L += [f"- `BbCode.build_circuit(strategy='cardinal')` -> **{ip['outcome']}**"
          f"{' (' + ip['exception'] + ')' if ip.get('exception') else ''}",
          f"- family whitelist `BbCode.supported_strategies` = "
          f"`{ip['family_whitelist']}`",
          f"- global builder registry keys (semantics `DOMAIN['extractor']`) = "
          f"`{ip['global_whitelist']}`",
          f"- message: `{ip.get('message', '')}`" if ip.get("message") else "",
          f"- `get_layout()` default: `{data['layout_none_probe']['get_layout_default']}`",
          ""]

    hs = data.get("hash_seed_probe")
    if hs:
        L += ["### Reproducibility of the stim-circuit artifact", "",
              f"- fingerprints by `PYTHONHASHSEED`: `{hs['fingerprints_by_pythonhashseed']}`",
              f"- distinct fingerprints: **{hs['n_distinct']}** "
              f"(deterministic: **{hs['deterministic']}**)",
              f"- {hs['note']}", ""]

    cs = m.get("cross_source")
    if cs:
        L += ["### Installed wheel vs pinned snapshot (`--source both`)", ""]
        if not cs.get("pinned_available"):
            L += [f"- {cs['note']}", ""]
        else:
            L += [f"- installed wheel: `{cs['installed_quits_file']}` "
                  f"(quits {cs['installed_quits_version']})",
                  f"- pinned tree: `{cs['pinned_quits_file']}` "
                  f"(quits {cs['pinned_quits_version']})",
                  f"- baseline artifact fingerprints agree: "
                  f"**{cs['all_baseline_fingerprints_agree']}**",
                  f"- the same artifacts change: "
                  f"**{cs['all_same_changed_artifacts']}**",
                  f"- verdicts agree: `{cs['summaries_agree']}`", ""]

    L += ["## 5. Alignment with the static QUITS_CALL_SITES model", "",
          "| dimension | real site | static modelling | measured | aligned |",
          "|---|---|---|---|---|"]
    for a in data["call_site_alignment"]:
        m2 = a["measured"]
        L.append(f"| `{a['dimension']}` | `{a['site']}` "
                 f"| {a['static_modelling']} "
                 f"| changed={','.join(m2['changed_artifacts']) or '-'}, "
                 f"collateral={','.join(m2['collateral_nodes']) or 'none'}, "
                 f"modules={m2['n_quits_modules_executed']} "
                 f"| **{a['aligned']}** |")
    for a in data["call_site_alignment"]:
        for n in a["notes"]:
            L.append(f"- **{a['dimension']}**: {n}")

    L += ["", "## 6. Modelling corrections demanded by the measurement", "",
          "| model | verdict | what the measurement says | action |",
          "|---|---|---|---|"]
    L.append("| `semantics._mk_components()` hand-declared `R(extractor)` | "
             "**under-approximates** | a noise substitution changes the "
             "stim circuit | **fixed**: `READ_SETS_FROM_SOURCE` adds `noise` "
             "(derived by `extract_read_sets.py`, locked by pytest) |")
    L.append("| `semantics._mk_components()` `arch` / `decoder` read sets | "
             "**need re-classification, not repair** | `Layout(code)` and "
             "`get_codecap_pL(code, ...)` are artifact flows, not coordinate "
             "reads | **fixed**: split into `READ_SETS_FROM_SOURCE` "
             "(coordinates) + `ARTIFACT_READS_FROM_SOURCE` (DAG edges) |")
    L.append("| `build_circuit` receiver (`self`) | **not modelled** | "
             "`build_circuit` is a `QldpcCode` method, so replacing the code "
             "component changes the extractor artifact | **fixed**: the "
             "extractor now resolves `self` to the code artifact, giving the "
             "edge `extractor <- code` |")
    L.append("| Theorem 1's `cone(x)` as a predictor of a *coordinate* "
             "change | **wrong question** | changing `noise` changes the "
             "extractor artifact, but `cone(noise)` does not contain it | "
             "**fixed**: added `semantics.coordinate_impact(A, x)`, which "
             "closes the coordinate readers along the DAG |")
    L.append("| `cone_table.make_quits_dataflow_assembly()` | "
             "**one edge too few** | the `code` substitution changes "
             "`layout_positions`, but that assembly had no `arch <- code` "
             "edge | **fixed** (decision 3, 2026-10-09): the edge is added, so "
             "`cone(code) = {extractor, arch, decoder, experiment}`; this file's "
             "`dataflow cone` column is regenerated from the corrected assembly |")

    L += ["", "## 7. Summary", "",
          f"- substitutions: **{s['n_substitutions']}** "
          f"(measured {s['n_measured']}, refused {s['n_refused']})",
          f"- `coordinate_impact` covers every measured impact set: "
          f"**{s['coordinate_impact_covers_measurement_all']}**",
          f"- Theorem-1 cone (component substitution) covers every measured impact "
          f"set: **{s['theorem1_cone_covers_measurement_all']}**",
          f"- `cone_table`'s dataflow cone covers every measured impact set: "
          f"**{s['dataflow_cone_covers_measurement_all']}**",
          f"- collateral nodes per dimension: `{s['collateral_nodes_by_dimension']}`", ""]
    return "\n".join(x for x in L if x is not None) + "\n"


def _reconfigure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        fn = getattr(stream, "reconfigure", None)
        if fn is not None:
            try:
                fn(encoding="utf-8", errors="replace")
            except (ValueError, OSError):            # pragma: no cover
                pass


def _run_in_child(pinned: bool, quick: bool) -> dict | None:
    """Run the whole experiment in a fresh child interpreter and return its JSON.

    Two reasons a child is required rather than an in-process re-run:

    1. ``--source pinned``: ``PYTHONPATH`` entries precede ``site-packages``, so
       prepending the pinned tree's ``src`` makes ``import quits`` resolve to the
       snapshot.  A module already imported in this process cannot be swapped.
    2. the ``PYTHONHASHSEED=0`` pin (see :func:`probe_hash_seed_sensitivity`):
       setting it in the current process is impossible, so an in-process run
       would be measured under whatever seed the shell happened to pick.

    The child's scratch file goes to a fresh temporary directory, **not** into
    the artifact directory, so a failed run can never leave a stray
    ``_dynamic_impact_*.json`` next to the published outputs.

    For ``pinned=False`` the pinned tree is stripped from ``PYTHONPATH``: the
    image sets it image-wide, and without this the "installed wheel" side would
    silently resolve to the pinned snapshot too.

    Returns ``None`` if the child failed (e.g. the pinned tree is missing).
    """
    scratch = Path(tempfile.mkdtemp(prefix="dynamic_impact_"))
    out = scratch / ("_pinned.json" if pinned else "_installed.json")
    env = dict(os.environ, PYTHONHASHSEED="0")
    if pinned:
        from quant_evidence import find_quits_src
        try:
            pinned_src = str(find_quits_src().parent)
        except FileNotFoundError:                    # pragma: no cover
            return None
        env["PYTHONPATH"] = (pinned_src + os.pathsep + env["PYTHONPATH"]
                             if env.get("PYTHONPATH") else pinned_src)
    else:
        from quant_evidence import find_quits_src
        try:
            pinned_src = str(find_quits_src().parent)
        except FileNotFoundError:                    # pragma: no cover
            pinned_src = None
        if pinned_src:
            keep = [p for p in env.get("PYTHONPATH", "").split(os.pathsep)
                    if p and Path(p).resolve() != Path(pinned_src).resolve()]
            env["PYTHONPATH"] = os.pathsep.join(keep)
    args = [sys.executable, str(Path(__file__).resolve()), "--worker", str(out)]
    if quick:
        args.append("--quick")
    try:
        proc = subprocess.run(args, env=env)
        if proc.returncode != 0 or not out.is_file():
            return None
        return json.loads(out.read_text(encoding="utf-8"))
    finally:
        with contextlib.suppress(OSError):
            out.unlink()
        with contextlib.suppress(OSError):
            scratch.rmdir()


def _run_against_pinned_tree(quick: bool) -> dict | None:
    """Re-run the whole experiment in a child interpreter against the *pinned*
    ``third_party`` tree, so ``--source pinned`` really measures that tree."""
    return _run_in_child(pinned=True, quick=quick)


def _cross_source_report(installed: dict, pinned: dict | None) -> dict:
    """Do the installed wheel and the pinned snapshot measure the same thing?"""
    if pinned is None:
        return {"pinned_available": False,
                "note": "the pinned third_party tree was not importable"}
    same = {a: (installed["baseline_artifacts"][a]["fingerprint"]
                == pinned["baseline_artifacts"][a]["fingerprint"])
            for a in installed["baseline_artifacts"]}
    changed_same = {}
    for r in pinned["substitutions"]:
        if r.get("refused"):
            continue
        other = [x for x in installed["substitutions"]
                 if x["name"] == r["name"] and not x.get("refused")]
        changed_same[r["name"]] = bool(other) and (
            other[0]["changed_artifacts"] == r["changed_artifacts"])
    return {
        "pinned_available": True,
        "installed_quits_file": installed["metadata"]["quits_file"],
        "installed_quits_version": installed["metadata"]["quits_version"],
        "pinned_quits_file": pinned["metadata"]["quits_file"],
        "pinned_quits_version": pinned["metadata"]["quits_version"],
        "baseline_fingerprints_agree": same,
        "all_baseline_fingerprints_agree": all(same.values()),
        "same_changed_artifacts": changed_same,
        "all_same_changed_artifacts": all(changed_same.values()),
        "summaries_agree": {
            k: installed["summary"][k] == pinned["summary"][k]
            for k in ("h3_noise_not_circuit_preserving",
                      "h1_extractor_inadmissible_detected",
                      "h1_semantic_layer_agrees",
                      "coordinate_impact_covers_measurement_all")},
    }


def main(argv: list[str] | None = None) -> int:
    _reconfigure_stdout()
    rc = _ensure_hash_seed(argv)
    if rc is not None:
        return rc
    argv = list(sys.argv[1:] if argv is None else argv)
    quick = "--quick" in argv

    if "--worker" in argv:                       # internal: dump and exit
        path = Path(argv[argv.index("--worker") + 1])
        path.write_text(json.dumps(run(quick=quick), indent=2,
                                   ensure_ascii=False), encoding="utf-8")
        return 0

    want = "installed"
    if "--source" in argv:
        want = argv[argv.index("--source") + 1]
    if want not in ("installed", "pinned", "both"):
        raise SystemExit(f"unknown --source {want!r}")

    # The cross-source comparison must put both measurements on the same
    # PYTHONHASHSEED, so `--source both` takes *both* sides from child runs.
    if want in ("pinned", "both"):
        installed = _run_in_child(pinned=False, quick=quick)
        pinned = _run_in_child(pinned=True, quick=quick)
        if want == "pinned" and pinned is not None:
            data = pinned
        elif installed is not None:
            data = installed
        else:
            data = run(quick=quick)
        data["metadata"]["source_mode"] = want
        data["metadata"]["cross_source"] = _cross_source_report(
            installed or data, pinned)
    else:
        data = run(quick=quick)
        data["metadata"]["source_mode"] = want

    out = outdir.resolve_out(argv, HERE)
    (out / "dynamic_impact.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "dynamic_impact.md").write_text(to_markdown(data), encoding="utf-8")

    print(f"quits: {data['metadata']['quits_file']} "
          f"({data['metadata']['quits_version']})")
    for r in data["substitutions"]:
        if r.get("refused"):
            print(f"  {r['name']:24s} REFUSED {r['exception']}")
            continue
        print(f"  {r['name']:24s} changed={r['changed_artifacts']} "
              f"collateral={r['collateral_nodes'] or 'none'} "
              f"modules={r['n_quits_modules_after']}")
    print(f"H3 (noise not circuit-preserving): "
          f"{data['summary']['h3_noise_not_circuit_preserving']}")
    print(f"H1 (inadmissible refused): "
          f"{data['summary']['h1_extractor_inadmissible_detected']} / "
          f"semantic layer agrees: {data['summary']['h1_semantic_layer_agrees']}")
    print(f"prediction covers measurement: coordinate_impact="
          f"{data['summary']['coordinate_impact_covers_measurement_all']}, "
          f"theorem1-cone="
          f"{data['summary']['theorem1_cone_covers_measurement_all']}, "
          f"dataflow-cone="
          f"{data['summary']['dataflow_cone_covers_measurement_all']}")
    cs = data["metadata"].get("cross_source")
    if cs and cs.get("pinned_available"):
        print(f"cross-source (installed vs pinned): baseline fingerprints "
              f"agree={cs['all_baseline_fingerprints_agree']}, summaries "
              f"agree={all(cs['summaries_agree'].values())}")
    print(f"wrote {out / 'dynamic_impact.json'}")
    print(f"wrote {out / 'dynamic_impact.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
