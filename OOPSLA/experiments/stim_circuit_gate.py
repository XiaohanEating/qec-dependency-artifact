"""Real-artifact gate for the semantic layer's toy model (PIVOT_NOTE §5 / §0).

**The problem this experiment closes.**  ``src/semantics.py`` is a *toy model*:
its ``produce`` functions return dicts and strings, not the artifacts a user of
QUITS actually cares about.  Theorem 1's conclusion -- "the artifacts of the
nodes outside ``{x} ∪ cone(x)`` are unchanged when component ``x`` is
substituted" --
is therefore only ever *executed on toy artifacts*.  This script turns the
``experiment`` assembly layer into a **real artifact producer**: every node's
``produce`` calls the pinned QUITS tree and returns genuine objects (a real
``QldpcCode`` instance, a real ``stim.Circuit``, a real detector error model,
a real layout mapping, a real decoder prediction).

The gate then asks one question per (configuration, dimension):

    does the semantic layer's verdict survive contact with real artifacts?

For each (config, dim) we

1. read the **semantic-layer verdict** for that (config, dim) straight out of
   ``experiments/artifact_invariance.py`` -- the same (C1)-(C4) checker, the
   same ``cone``, the same ``provably_unchanged`` set -- so the two levels are
   compared on *identical* input, never on a re-derived approximation;
2. **substitute the component for real** on the real assembly (an alternative
   implementation that is pointwise equal on ``R(x)`` but reached through a
   different QUITS call path);
3. compare, byte for byte, the **stim circuit text** and the **detector error
   model fingerprint** before and after, plus the code matrices, the layout
   payload and the decoder prediction;
4. record whether the real measurement **agrees** with the semantic verdict.

Negative controls keep the gate honest (a gate that can only say "equal" is
worthless):

* **H3** -- changing the ``noise`` *coordinate* (SD6 -> SI1000, not a component
  substitution) changes the real circuit text and the real DEM fingerprint, so
  "replacing the noise component" is local while "replacing the noise value" is
  not.  Both are measured on the same real circuits.
* **H1** -- an inadmissible ``(code, extractor)`` pair is refused by the
  semantic layer's contract *before* assembly; the same pair makes the real
  QUITS call raise.  A second instance of the same shape is ``arch = grid2d``
  on a non-BB family: ``ToricLayout`` only supports ``BbCode``.
* **non-(C4) substitution** -- swapping the BP-OSD *value* for BP-LSD makes the
  checker refuse to apply Theorem 1 (``applicable=False``), which is the
  conservative refusal of PIVOT_NOTE §8.6 claim 2.

**What this does and does not narrow.**  It narrows the toy-model boundary from
"the artifacts are dicts" to "the artifacts are real Stim objects, on these
configurations, for these five call paths".  It does *not* claim that every
configuration in the corpus behaves this way (``--full`` sweeps all 48; the
default run is the 6-configuration gate), and it does not claim the stim
circuit is a *stable* artifact -- ``dynamic_impact.py`` measured that the
circuit text depends on ``PYTHONHASHSEED``, so this script re-executes itself
in a child interpreter with ``PYTHONHASHSEED=0`` (same pattern, same reason).

Object under test: the pinned ``third_party`` tree (``quant_evidence`` puts its
``src`` first on ``sys.path`` and asserts the import comes from there), or the
installed wheel when the pinned tree is absent.

Outputs: ``stim_circuit_gate.json`` and ``stim_circuit_gate.md``.

Run:  python experiments/stim_circuit_gate.py              # 6-config gate
      python experiments/stim_circuit_gate.py --quick      # 2 configs (pytest)
      python experiments/stim_circuit_gate.py --full       # every admissible config
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
REPO_ROOT = OOPSLA_ROOT.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402  (E402: path shim above)

import semantics  # noqa: E402  (E402: path shim above)
import outdir  # noqa: E402  (`--out` support; see src/outdir.py)
from semantics import (  # noqa: E402
    ASSEMBLY_EDGES_FROM_SOURCE, BASELINE_ASSEMBLY, COORDINATES, Assembly,
    Component, FAMILY_STRATEGIES, READ_SETS_FROM_SOURCE, Spec,
    make_source_faithful_assembly,
)

QUITS_COMMIT = "0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452"

#: The real-QUITS operating point, shared with ``dynamic_impact.py`` so the two
#: experiments measure the same object.
NUM_ROUNDS = 2
NUM_SHOTS = 16
SAMPLER_SEED = 7
WINDOW = 3
OVERLAP = 1

#: artifact -> the semantic node that produces it (same attribution as
#: ``dynamic_impact.ARTIFACT_OWNER``; the gate reuses it to label rows).
ARTIFACT_OWNER = {
    "code_matrices": "code",
    "layout_payload": "arch",
    "noise_params": "noise",
    "stim_circuit": "extractor",
    "detector_error_model": "extractor",
    "logical_observables": "extractor",
    "decoder_prediction": "decoder",
}

# ---------------------------------------------------------------------------
# 1. the QUITS-side construction tables (one representative per family)
# ---------------------------------------------------------------------------

#: One representative instance per code family -- the C0 corpus instances used
#: by ``dynamic_impact.py``, so a fingerprint recorded here is comparable with
#: the one recorded there.
CODE_CLASS = {"BB": "BbCode", "HGP": "HgpCode", "QLP": "QlpCode"}

#: Noise parameterisations (identical to ``dynamic_impact.NOISE_PARAMS``).
NOISE_PARAMS = {
    "SD6": {"idle_error": 1e-4, "sqgate_error": 1e-3,
            "tqgate_error": 1e-3, "spam_error": 1e-3},
    "SI1000": {"idle_error": 2e-5, "sqgate_error": 2e-4,
               "tqgate_error": 2e-4, "spam_error": 2e-4},
}

_NOISE_FIELD_ORDER = ("idle_error", "sqgate_error", "tqgate_error", "spam_error")


def _error_model(noise: str):
    """An ``ErrorModel`` for a noise coordinate value (the value spec)."""
    quits = _import_quits()
    params = NOISE_PARAMS[noise]
    return quits.ErrorModel(**params)


def _code_kwargs(family: str, impl: str) -> dict:
    """Constructor arguments for a code family, in one of two spellings.

    The two spellings are *different ways of writing the same construction*.
    QUITS exposes exactly one construction path per family (the family
    constructor), so a (C4)-satisfying second implementation can only be a
    spelling variant -- which is itself a finding: see
    ``stim_circuit_gate.md`` §4 ("what the gate could not do").
    """
    if family == "BB":
        if impl == "baseline":
            return dict(l=6, m=6, A_x_pows=[3], A_y_pows=[1, 2],
                        B_x_pows=[1, 2], B_y_pows=[3])
        return dict(l=6, m=6, A_x_pows=(3,), A_y_pows=(1, 2),
                    B_x_pows=(1, 2), B_y_pows=(3,))
    dtype = int if impl == "baseline" else np.uint8
    if family == "HGP":
        return {"h1": np.array([[1, 1, 0], [0, 1, 1]], dtype=dtype),
                "h2": np.array([[1, 1, 0], [0, 1, 1]], dtype=dtype)}
    if family == "QLP":
        return {"b1": np.array([[0, 0], [0, 3]], dtype=dtype),
                "b2": np.array([[0, 1, 0], [1, 0, 3]], dtype=dtype),
                "lift_size": 12}
    raise KeyError(family)


#: Per-dimension description of the alternative implementation used by the gate.
#: ``available`` is filled in per configuration by :func:`_alt_available`, because
#: the extractor alternative depends on the strategy and the code alternative
#: does not exist as a *distinct* implementation for any family.
ALT_IMPLEMENTATIONS = {
    "code": "the same family constructor, invoked with a different spelling of "
            "the construction arguments (BB: power lists vs tuples; HGP/QLP: "
            "int vs uint8 base matrices)",
    "extractor": "the builder is reached directly through the strategy "
                 "registry (``get_builder``) instead of through "
                 "``QldpcCode.build_circuit``'s dispatch, or the default "
                 "``CircuitBuildOptions`` is materialised by the caller "
                 "instead of the callee",
    "arch": "the layout is constructed with every optional argument spelled "
            "out (``TransversalLayout`` explicit defaults, or the concrete "
            "``BbToricLayout`` instead of the ``ToricLayout`` factory)",
    "noise": "``ErrorModel`` is constructed positionally instead of by "
             "keyword",
    "decoder": "the generic ``sliding_window_circuit_mem`` entry point is "
               "called with an explicit inner-decoder class and parameter "
               "dicts, instead of the ``sliding_window_bposd_circuit_mem`` "
               "convenience wrapper",
}

#: Which QUITS strategies admit the "direct builder" alternative.  For the
#: others the family's ``build_circuit`` sets up the Tanner graph first, so
#: bypassing the dispatch changes the artifact; the gate then uses the
#: "caller materialises the default options" alternative instead.
_DIRECT_BUILDER_STRATEGIES = {"zxcoloration"}


def _quits_src() -> Path:
    """Locate the pinned QUITS tree (``quant_evidence.find_quits_src``)."""
    from quant_evidence import find_quits_src
    return find_quits_src()


#: strong references to the imported `quits` trees, so that evicting a stale
#: entry from ``sys.modules`` cannot make CPython unload it mid-gate
_PINNED: list = []


def _evict_foreign_quits(src: Path) -> None:
    """Drop any already-imported ``quits`` that did *not* come from ``src``.

    Why this is necessary (`SUBMISSION_READINESS.md` §3.4-D/E): the naive
    version of this function was

        sys.path.insert(0, str(src.parent)); import quits

    which silently returns whatever ``sys.modules["quits"]`` already holds.
    ``experiments/test_quits_faithfulness.py`` runs *before* this module's
    tests (pytest collects alphabetically) and measures the **installed
    wheel** on purpose, so by the time the gate runs, ``quits`` is the
    site-packages 1.2.0.  ``import quits`` then returns that module and the
    "did it come from the pinned tree?" assertion below fires — a pure test
    ordering artefact that had nothing to do with the artifact.

    The gate genuinely needs the pinned tree for its whole run (it builds
    live ``QldpcCode`` / ``stim.Circuit`` objects), so unlike
    ``quant_evidence._isolate_pinned_quits`` this cannot restore afterwards;
    it makes the *direction* explicit instead of implicit.  Both trees are
    the same version (``shared/VERSIONS.md``), and
    ``stim_circuit_gate.json`` records which one was actually used.
    """
    existing = sys.modules.get("quits")
    if existing is not None:
        got = Path(getattr(existing, "__file__", "") or "").resolve()
        if src.resolve() in got.parents:
            return                                   # already the pinned tree
    for name in [k for k in sys.modules
                 if k == "quits" or k.startswith("quits.")]:
        del sys.modules[name]


def _import_quits():
    """Import the pinned tree's ``quits`` and assert where it came from."""
    src = _quits_src()
    if str(src.parent) not in sys.path:
        sys.path.insert(0, str(src.parent))
    _evict_foreign_quits(src)
    import quits
    got = Path(quits.__file__).resolve()
    if src.resolve() not in got.parents:
        raise RuntimeError(
            f"quits was imported from {got}, not from the pinned tree {src}")
    if quits not in _PINNED:
        _PINNED.append(quits)
    return quits


# ---------------------------------------------------------------------------
# 2. fingerprints of real artifacts
# ---------------------------------------------------------------------------

def _sha(text_or_bytes) -> str:
    data = (text_or_bytes if isinstance(text_or_bytes, bytes)
            else str(text_or_bytes).encode("utf-8"))
    import hashlib
    return hashlib.sha256(data).hexdigest()[:16]


def _numpy_matrix_fingerprint(arr) -> str:
    return _sha(np.asarray(arr).tobytes())


def _layout_payload(mapping) -> tuple:
    return tuple(sorted((role, tuple(sorted(getattr(mapping, role).items())))
                        for role in ("data", "zcheck", "xcheck")))


# ---------------------------------------------------------------------------
# 3. the real `produce` functions
# ---------------------------------------------------------------------------
#
# Each one takes ``(spec, inputs, impl)`` and returns a **real** artifact.
# ``impl`` selects the implementation path ("baseline" or "alt"); the two paths
# must agree pointwise (that is side condition (C4) of Theorem 1), otherwise the
# gate would be comparing two different artifacts rather than two
# implementations of one artifact.
#
# The read sets and the DAG edges are *not* chosen here: they are
# ``semantics.READ_SETS_FROM_SOURCE`` and
# ``semantics.ASSEMBLY_EDGES_FROM_SOURCE``, i.e. the ones auto-extracted from
# this very source tree.  The gate therefore inherits the published baseline's
# topology and only replaces the artifacts.

def _produce_code(spec: Spec, inp: dict, impl: str):
    import quits.qldpc_code as qc
    cls = getattr(qc, CODE_CLASS[spec.code])
    return cls(**_code_kwargs(spec.code, impl))


def _code_payload(code) -> dict:
    """A JSON-able view of the code artifact (the object itself is not)."""
    commutes = bool(((code.hz @ code.hx.T) % 2 == 0).all())
    return {
        "family": type(code).__name__,
        "hz_shape": [int(v) for v in code.hz.shape],
        "hx_shape": [int(v) for v in code.hx.shape],
        "n_logical": int(code.lz.shape[0]),
        "hz_sha256": _numpy_matrix_fingerprint(code.hz),
        "hx_sha256": _numpy_matrix_fingerprint(code.hx),
        "lz_sha256": _numpy_matrix_fingerprint(code.lz),
        "lx_sha256": _numpy_matrix_fingerprint(code.lx),
        "css_commutes": commutes,
        "verify_css_logicals": bool(code.verify_css_logicals()),
    }


def _produce_noise(spec: Spec, inp: dict, impl: str):
    quits = _import_quits()
    params = NOISE_PARAMS[spec.noise]
    if impl == "baseline":
        model = quits.ErrorModel(**params)
    else:
        # positional spelling of the same four fields
        model = quits.ErrorModel(*[params[k] for k in _NOISE_FIELD_ORDER])
    return {"kind": "noise", "model": spec.noise,
            "params": tuple(sorted(params.items())),
            "error_model": model}


def _circuit_call_path(spec: Spec, impl: str) -> str:
    """Which QUITS call path produced the circuit -- reported, not compared."""
    strategy = spec.extractor
    if impl == "baseline":
        return "QldpcCode.build_circuit"
    if strategy in _DIRECT_BUILDER_STRATEGIES:
        return f"get_builder({strategy!r}).get_coloration_circuit"
    return "QldpcCode.build_circuit(explicit CircuitBuildOptions())"


def _decoder_entry(impl: str) -> str:
    """Which QUITS decoder entry point was used -- reported, not compared."""
    return ("sliding_window_bposd_circuit_mem" if impl == "baseline"
            else "sliding_window_circuit_mem(BpOsdDecoder, ...)")


def _produce_extractor(spec: Spec, inp: dict, impl: str) -> dict:
    """The real stim circuit (+ its DEM), by one of two call paths.

    ``build_circuit(strategy, error_model=...)`` takes the noise *coordinate's
    value*, not another component's artifact object -- so the noise error model
    is built here from ``spec.noise`` rather than read off ``inp``.  That is
    exactly the distinction the two auto-extracted tables make
    (``READ_SETS_FROM_SOURCE`` vs ``ARTIFACT_READS_FROM_SOURCE``); the ``code``
    artifact, by contrast, *is* a DAG edge and comes from ``inp``.
    """
    from quits.qldpc_code.circuit_construction import (
        CircuitBuildOptions, get_builder)

    code = inp["code"]
    error_model = _error_model(spec.noise)
    strategy = spec.extractor
    if strategy not in FAMILY_STRATEGIES[spec.code]:
        # The semantic layer's value-add (H1): refuse **before** running QUITS,
        # instead of letting the whitelist check surface as a run-time raise
        # inside build_circuit.  Same message as the semantic layer's own
        # faithful extractor contract.
        raise ValueError(
            f"contract violated: extractor (strategy {strategy!r} is not on "
            f"{spec.code}'s whitelist {sorted(FAMILY_STRATEGIES[spec.code])})")
    if impl == "baseline":
        circuit = code.build_circuit(
            strategy=strategy, error_model=error_model,
            num_rounds=NUM_ROUNDS, basis="Z")
    elif strategy in _DIRECT_BUILDER_STRATEGIES:
        builder = get_builder(strategy, code)
        circuit = builder.get_coloration_circuit(
            error_model=error_model, num_rounds=NUM_ROUNDS, basis="Z")
    else:
        circuit = code.build_circuit(
            strategy=strategy, error_model=error_model,
            num_rounds=NUM_ROUNDS, basis="Z",
            circuit_build_options=CircuitBuildOptions())

    dem = circuit.detector_error_model(flatten_loops=True)
    observables = [str(inst) for inst in circuit if inst.name == "OBSERVABLE_INCLUDE"]
    return {
        "kind": "circuit",
        "strategy": strategy,
        "family": type(code).__name__,
        "admissible": strategy in FAMILY_STRATEGIES[spec.code],
        "noise": spec.noise,
        # NOTE: `call_path` is deliberately NOT part of the artifact.  Theorem
        # 1's (C4) is about the artifact *value*; the implementation that
        # produced it is reported separately (see the row's
        # `circuit_call_path_baseline` / `circuit_call_path_after`).  Putting it
        # here would make two implementations of one artifact compare unequal
        # by construction -- i.e. it would make the gate measure nothing.
        "circuit": circuit,
        "circuit_sha256": _sha(str(circuit)),
        "circuit_num_qubits": int(circuit.num_qubits),
        "circuit_num_detectors": int(circuit.num_detectors),
        "circuit_num_observables": int(circuit.num_observables),
        "circuit_num_ticks": int(circuit.num_ticks),
        "circuit_len_chars": len(str(circuit)),
        "dem_sha256": _sha(str(dem)),
        "dem_num_detectors": int(dem.num_detectors),
        "dem_num_observables": int(dem.num_observables),
        "dem_num_errors": sum(1 for _ in dem),
        "logical_observables_sha256": _sha(observables),
        "n_observable_includes": len(observables),
    }


def _produce_arch(spec: Spec, inp: dict, impl: str) -> dict:
    from quits.layout import ToricLayout, TransversalLayout
    from quits.layout.toric_bb import BbToricLayout

    code = inp["code"]
    family = type(code).__name__
    if spec.arch == "free":
        kwargs = {"center_checks": True}
        if impl == "alt":
            kwargs.update(data_rows=1, zcheck_rows=1, xcheck_rows=1)
        layout = TransversalLayout(code, **kwargs)
        label = "TransversalLayout"
        family_ok = True
    elif impl == "baseline":
        # the factory dispatches on the code family -- see the probe below
        layout = ToricLayout(code)
        label = "ToricLayout"
        family_ok = family == "BbCode"
    else:
        layout = BbToricLayout(code)
        label = "BbToricLayout"
        family_ok = family == "BbCode"
    mapping = layout.mapping()
    return {
        "kind": "layout",
        "arch": spec.arch,
        "layout": label,
        "family_ok": family_ok,
        "n_positions": len(mapping.data),
        "payload_sha256": _sha(_layout_payload(mapping)),
    }


def _produce_decoder(spec: Spec, inp: dict, impl: str) -> dict:
    """A real decoder prediction on shots sampled from the real circuit."""
    from quits.simulation import get_stim_mem_result
    import quits.decoder as qdec
    from ldpc.bposd_decoder import BpOsdDecoder
    from quits.decoder.sliding_window import sliding_window_circuit_mem

    circuit = inp["extractor"]["circuit"]
    code = inp["code"]
    det, _obs = get_stim_mem_result(circuit, NUM_SHOTS, seed=SAMPLER_SEED)
    if impl == "baseline":
        pred = qdec.sliding_window_bposd_circuit_mem(
            det.copy(), circuit, code.hz, code.lz, W=WINDOW, F=OVERLAP)
    else:
        cfg = {"bp_method": "product_sum", "max_iter": 2, "schedule": "serial",
               "osd_method": "osd_cs", "osd_order": 0}
        pred = sliding_window_circuit_mem(
            det.copy(), circuit, code.hz, code.lz, WINDOW, OVERLAP,
            BpOsdDecoder, BpOsdDecoder, dict(cfg), dict(cfg),
            "channel_probs", "channel_probs", "decode", "decode")
    arr = np.asarray(pred)
    # NOTE: `entry` is reported, not compared -- see the note in
    # `_produce_extractor`.  It is recorded per row as
    # `decoder_entry_baseline` / `decoder_entry_after`.
    #
    # 2026-10-12 soundness 修复：两条调用路径执行的**都**是 BpOsdDecoder，
    # 与 spec.decoder 坐标值无关，所以 `name` 记录实际执行的解码路径
    # （此前 name 照抄 spec.decoder，在 BP-LSD 配置下标注的是实际没有跑
    # 的解码器——配置标签而非真实路径）；坐标值另存 `spec_label`。
    return {"kind": "decoder", "name": "BP-OSD",
            "spec_label": spec.decoder,
            "prediction_sha256": _sha(arr.tobytes()),
            "n_shots": int(arr.shape[0]), "n_logical": int(arr.shape[1]),
            "n_logical_flips": int(arr.sum())}


def _produce_experiment(spec: Spec, inp: dict, impl: str) -> dict:
    """**The assembly layer** -- it yields the real circuit and its DEM."""
    ext = inp["extractor"]
    dec = inp["decoder"]
    code = _code_payload(inp["code"])
    return {
        "kind": "experiment",
        "code_matrices_sha256": _sha("".join(
            code[k] for k in ("hz_sha256", "hx_sha256", "lz_sha256", "lx_sha256"))),
        "layout_payload_sha256": inp["arch"]["payload_sha256"],
        "noise_params_sha256": _sha(inp["noise"]["params"]),
        # the two artifacts the paper is about:
        "stim_circuit_sha256": ext["circuit_sha256"],
        "detector_error_model_sha256": ext["dem_sha256"],
        "logical_observables_sha256": ext["logical_observables_sha256"],
        "decoder_prediction_sha256": dec["prediction_sha256"],
        "stim_circuit_len_chars": ext["circuit_len_chars"],
        "code_family": code["family"],
        "css_commutes": code["css_commutes"],
        "verify_css_logicals": code["verify_css_logicals"],
    }


PRODUCERS = {
    "code": _produce_code,
    "extractor": _produce_extractor,
    "arch": _produce_arch,
    "noise": _produce_noise,
    "decoder": _produce_decoder,
    "experiment": _produce_experiment,
}


# ---------------------------------------------------------------------------
# 4. contracts: the obligations QUITS itself enforces only at run time
# ---------------------------------------------------------------------------
#
# Each contract is the *stated* form of something QUITS leaves implicit (the
# five ``QUITS_CALL_SITES`` rows): the CSS commutation of the code, the
# family/strategy admissibility of the extractor, the layout's coverage of the
# code's qubits, the decoder's prediction shape.

def _contract_code(art) -> bool:
    payload = _code_payload(art)
    return bool(payload["css_commutes"] and payload["verify_css_logicals"])


def _contract_extractor(art) -> bool:
    return (art["kind"] == "circuit" and bool(art["admissible"])
            and bool(art["circuit_sha256"]) and bool(art["dem_sha256"]))


def _contract_arch(art) -> bool:
    """Layout coverage, and the family restriction QUITS enforces by dispatch.

    ``ToricLayout`` only supports ``BbCode``; the semantic layer states that as
    an obligation so it is caught *before* the assembly is run.
    """
    return (art["kind"] == "layout" and art["n_positions"] > 0
            and bool(art["family_ok"]))


def _contract_noise(art) -> bool:
    model = art["error_model"]
    rates = [model.idle_error, model.sqgate_error, model.tqgate_error,
             model.spam_error]
    return (art["kind"] == "noise"
            and all(0.0 <= float(r) <= 1.0 for r in rates))


def _contract_decoder(art) -> bool:
    return (art["kind"] == "decoder" and art["n_shots"] == NUM_SHOTS
            and art["n_logical"] > 0 and bool(art["prediction_sha256"]))


def _contract_experiment(art) -> bool:
    return bool(art["kind"] == "experiment"
                and art["stim_circuit_sha256"] and art["detector_error_model_sha256"])


CONTRACTS = {
    "code": _contract_code,
    "extractor": _contract_extractor,
    "arch": _contract_arch,
    "noise": _contract_noise,
    "decoder": _contract_decoder,
    "experiment": _contract_experiment,
}


# ---------------------------------------------------------------------------
# 5. the assembly
# ---------------------------------------------------------------------------

def _stim_component(dim: str, impl: str = "baseline") -> Component:
    """A ``semantics.Component`` whose ``produce`` calls real QUITS.

    ``reads`` / ``writes`` / ``contract`` come from the auto-extracted model,
    so the cone and the Theorem-1 verdicts of the published baseline apply to
    this assembly unchanged.  The assembly layer (``experiment``) reads every
    coordinate, exactly as ``semantics.make_source_faithful_assembly`` models it.
    """
    reads = READ_SETS_FROM_SOURCE.get(dim, COORDINATES)
    return Component(
        dim, reads,
        lambda s, inp, d=dim, i=impl: PRODUCERS[d](s, inp, i),
        contract=CONTRACTS[dim])


def make_stim_assembly(alt_dim: str | None = None) -> Assembly:
    """The real-artifact mirror of ``make_source_faithful_assembly()``.

    Same nodes, same read sets, same DAG edges, same contracts -- but every
    ``produce`` runs QUITS and returns a real object.  ``alt_dim`` swaps one
    node for its alternative implementation (same read set, same contract,
    different call path), which is exactly a Theorem-1 substitution.
    """
    nodes = {d: _stim_component(d, "alt" if d == alt_dim else "baseline")
             for d in COORDINATES}
    nodes["experiment"] = _stim_component("experiment",
                                          "alt" if alt_dim == "experiment"
                                          else "baseline")
    edges = {n: ASSEMBLY_EDGES_FROM_SOURCE[n] for n in COORDINATES}
    edges["experiment"] = tuple(COORDINATES)
    return Assembly(nodes=nodes, edges=edges)


def spec_label(spec: Spec) -> str:
    """The label ``artifact_invariance`` uses, so rows can be joined exactly."""
    return f"{spec.code}/{spec.arch}/{spec.extractor}/{spec.noise}/{spec.decoder}"


# ---------------------------------------------------------------------------
# 6. the configuration corpus
# ---------------------------------------------------------------------------
#
# Every default configuration is (a) admissible -- ``(code, extractor)`` on the
# family whitelist, ``arch`` available for the family -- and (b) a member of the
# 48-configuration cross-product ``artifact_invariance`` runs on, so the
# semantic-layer verdict for the very same (config, dim) exists.

GATE_CONFIGS = [
    # BB (the largest circuit: 144 qubits), both noise/decoder operating points
    {"code": "BB", "extractor": "zxcoloration", "arch": "free",
     "noise": "SD6", "decoder": "BP-OSD"},
    {"code": "BB", "extractor": "zxcoloration", "arch": "free",
     "noise": "SI1000", "decoder": "BP-LSD"},
    # HGP, both admissible strategies for the family
    {"code": "HGP", "extractor": "cardinal", "arch": "free",
     "noise": "SD6", "decoder": "BP-OSD"},
    {"code": "HGP", "extractor": "zxcoloration", "arch": "free",
     "noise": "SI1000", "decoder": "BP-LSD"},
    # QLP, both admissible strategies for the family
    {"code": "QLP", "extractor": "cardinal", "arch": "free",
     "noise": "SD6", "decoder": "BP-OSD"},
    {"code": "QLP", "extractor": "zxcoloration", "arch": "free",
     "noise": "SI1000", "decoder": "BP-LSD"},
]

#: ``--quick`` (used by pytest): two configurations, one small and one large.
QUICK_CONFIGS = [GATE_CONFIGS[0], GATE_CONFIGS[2]]

DIMENSIONS = tuple(COORDINATES)


def _configs_for(mode: str) -> list[Spec]:
    if mode == "quick":
        chosen = QUICK_CONFIGS
    elif mode == "full":
        # every admissible member of the 48-config cross-product
        import artifact_invariance as ai
        chosen = [{"code": s.code, "extractor": s.extractor, "arch": s.arch,
                   "noise": s.noise, "decoder": s.decoder}
                  for s in ai.build_configs(48) if ai.is_admissible(s)]
    else:
        chosen = GATE_CONFIGS
    return [Spec(**c) for c in chosen]


def _semantic_verdicts() -> dict:
    """The semantic layer's rows, keyed exactly like ``spec_label``.

    Runs ``artifact_invariance.run(48)`` -- the published experiment -- so the
    gate reads the *published* verdict rather than recomputing one.
    """
    import artifact_invariance as ai
    summary = ai.run(48)
    out = {}
    for row in summary["rows"]:
        if not row["admissible"]:
            continue
        out[(row["config"], row["dim"])] = {
            "applicable": row["applicable"],
            "cone": row["cone"],
            "invariance_ok": row["invariance_ok"],
            "baseline_assembly": summary["baseline_assembly"],
        }
    return out


# ---------------------------------------------------------------------------
# 7. the gate itself
# ---------------------------------------------------------------------------
#
# For one configuration we
#   (a) evaluate the real assembly once (the baseline artifacts),
#   (b) for each dimension, substitute the alternative implementation and
#       evaluate again,
#   (c) compare the real artifacts, node by node, *and* compare the two
#       artifacts the paper is about -- the stim circuit **text** and the DEM
#       -- byte for byte.

def _evaluate(A: Assembly, spec: Spec) -> dict:
    """``A.evaluate`` plus the circuit text kept for byte comparison.

    The extractor artifact carries the ``stim.Circuit`` object; its text is the
    thing a reader of the circuit would diff, so the gate compares the text
    rather than the object identity.
    """
    art = A.evaluate(spec)
    art["_circuit_text"] = str(art["extractor"]["circuit"])
    art["_dem_text"] = None                 # filled by the caller (DEM rebuild)
    return art


def _dem_text(circuit) -> str:
    return str(circuit.detector_error_model(flatten_loops=True))


def _node_artifacts_comparable(art: dict, name: str):
    """A comparable view of one node's artifact.

    ``code``'s artifact is a live ``QldpcCode`` (two of them are never ``==``
    for numpy reasons), so it is reduced to its fingerprint payload; every other
    node's artifact is already a plain dict of strings/ints/tuples.
    """
    if name == "code":
        return _code_payload(art[name])
    if name == "noise":
        payload = dict(art[name])
        payload.pop("error_model", None)      # the live ErrorModel
        return payload
    if name == "extractor":
        payload = dict(art[name])
        payload.pop("circuit", None)          # the live stim.Circuit
        return payload
    return art[name]


def _compare_nodes(base: dict, after: dict, A: Assembly) -> dict:
    per_node = {}
    for name in A.nodes:
        b = _node_artifacts_comparable(base, name)
        a = _node_artifacts_comparable(after, name)
        per_node[name] = {"equal": b == a,
                          "baseline": b, "after": a}
    return per_node


def gate_one_config(spec: Spec, semantic: dict, quick: bool = False) -> dict:
    """Run the gate for one configuration across all five dimensions."""
    A = make_stim_assembly()
    base = _evaluate(A, spec)
    label = spec_label(spec)

    rows = []
    for dim in DIMENSIONS:
        verdict = semantic.get((label, dim))
        if verdict is None:
            # not in the published 48-config corpus (or inadmissible): skip
            # rather than invent a verdict
            continue
        A_alt = make_stim_assembly(alt_dim=dim)
        after = _evaluate(A_alt, spec)
        per_node = _compare_nodes(base, after, A_alt)

        # the two artifacts the paper is about, compared byte for byte
        circuit_equal = base["_circuit_text"] == after["_circuit_text"]
        dem_equal = _dem_text(base["extractor"]["circuit"]) == \
            _dem_text(after["extractor"]["circuit"])
        code_equal = per_node["code"]["equal"]
        arch_equal = per_node["arch"]["equal"]
        decoder_equal = per_node["decoder"]["equal"]

        # Theorem 1's worksheet: which nodes must be rerun / re-verified.
        # Invariant region = N ∖ ({x} ∪ cone(x)): the substituted node x is
        # excluded even though these rows are all applicable (x is unchanged
        # here only because (C4) holds -- PIVOT_NOTE §6.1 Step 1).
        cone = list(verdict["cone"])
        provably_unchanged = sorted(set(A.nodes) - {dim} - set(cone))
        unchanged_hold = all(per_node[n]["equal"] for n in provably_unchanged)

        rows.append({
            "config": label,
            "dim": dim,
            "spec": spec.__dict__,
            # --- the semantic layer's verdict (published experiment) ---
            "semantic": {
                "applicable": verdict["applicable"],
                "invariance_ok": verdict["invariance_ok"],
                "cone_nodes_rerun": cone,
                "provably_unchanged_nodes": provably_unchanged,
                "baseline_assembly": verdict["baseline_assembly"],
            },
            # --- the real-artifact measurement ---
            "real": {
                "stim_circuit_text_equal": circuit_equal,
                "detector_error_model_text_equal": dem_equal,
                "code_artifact_equal": code_equal,
                "layout_artifact_equal": arch_equal,
                "decoder_artifact_equal": decoder_equal,
                "all_provably_unchanged_nodes_equal": unchanged_hold,
                "per_node_equal": {n: v["equal"] for n, v in per_node.items()},
                "circuit_sha256_baseline": base["experiment"]["stim_circuit_sha256"],
                "circuit_sha256_after": after["experiment"]["stim_circuit_sha256"],
                "dem_sha256_baseline": base["experiment"]["detector_error_model_sha256"],
                "dem_sha256_after": after["experiment"]["detector_error_model_sha256"],
                "circuit_len_chars": base["experiment"]["stim_circuit_len_chars"],
                "circuit_call_path_baseline": _circuit_call_path(spec, "baseline"),
                "circuit_call_path_after": _circuit_call_path(spec, "alt"),
                "decoder_entry_baseline": _decoder_entry("baseline"),
                "decoder_entry_after": _decoder_entry("alt"),
            },
            "alt_implementation": ALT_IMPLEMENTATIONS[dim],
            # --- does the semantic verdict survive? ---
            "gate_agrees": bool(
                verdict["invariance_ok"] == (circuit_equal and dem_equal
                                             and unchanged_hold)),
        })

    baseline_payload = {
        "config": label,
        "stim_circuit_sha256": base["experiment"]["stim_circuit_sha256"],
        "detector_error_model_sha256": base["experiment"]["detector_error_model_sha256"],
        "stim_circuit_len_chars": base["experiment"]["stim_circuit_len_chars"],
        "code_matrices_sha256": base["experiment"]["code_matrices_sha256"],
        "layout_payload_sha256": base["experiment"]["layout_payload_sha256"],
        "decoder_prediction_sha256": base["experiment"]["decoder_prediction_sha256"],
        "circuit_call_path": _circuit_call_path(spec, "baseline"),
        "decoder_entry": _decoder_entry("baseline"),
        "code_family": base["experiment"]["code_family"],
        "css_commutes": base["experiment"]["css_commutes"],
        "verify_css_logicals": base["experiment"]["verify_css_logicals"],
        "code_payload": _code_payload(base["code"]),
    }
    return {"baseline": baseline_payload, "rows": rows}


# ---------------------------------------------------------------------------
# 8. negative controls -- a gate that can only say "equal" is worthless
# ---------------------------------------------------------------------------

def probe_noise_coordinate_change() -> dict:
    """**H3, on the real circuit**: changing the noise *coordinate* is not local.

    Theorem 1 is about substituting a *component*.  Changing the *value* of the
    ``noise`` coordinate is a different operation, and on the real circuit it
    changes the circuit text and the DEM -- the non-locality PIVOT_NOTE §2 H3
    claims, measured on the artifact itself rather than inferred from the model.
    """
    A = make_stim_assembly()
    spec_a = Spec(code="BB", extractor="zxcoloration", arch="free",
                  noise="SD6", decoder="BP-OSD")
    spec_b = Spec(code="BB", extractor="zxcoloration", arch="free",
                  noise="SI1000", decoder="BP-OSD")
    a = A.evaluate(spec_a)
    b = A.evaluate(spec_b)
    return {
        "name": "noise coordinate change (SD6 -> SI1000)",
        "kind": "coordinate change, not a component substitution",
        "circuit_text_equal": str(a["extractor"]["circuit"]) == str(b["extractor"]["circuit"]),
        "dem_text_equal": _dem_text(a["extractor"]["circuit"]) == _dem_text(b["extractor"]["circuit"]),
        "circuit_sha256_before": a["extractor"]["circuit_sha256"],
        "circuit_sha256_after": b["extractor"]["circuit_sha256"],
        "dem_sha256_before": a["extractor"]["dem_sha256"],
        "dem_sha256_after": b["extractor"]["dem_sha256"],
        "changed_nodes": sorted({ARTIFACT_OWNER[k] for k in
                                 ("stim_circuit", "detector_error_model",
                                  "decoder_prediction")
                                 if a["experiment"][
                                     {"stim_circuit": "stim_circuit_sha256",
                                      "detector_error_model": "detector_error_model_sha256",
                                      "decoder_prediction": "decoder_prediction_sha256"}[k]]
                                 != b["experiment"][
                                     {"stim_circuit": "stim_circuit_sha256",
                                      "detector_error_model": "detector_error_model_sha256",
                                      "decoder_prediction": "decoder_prediction_sha256"}[k]]}),
        "note": "H3 confirmed on the real artifact: the noise coordinate is "
                "baked into the circuit, so changing it is NOT "
                "circuit-preserving -- while substituting the noise "
                "*component* (an equal-valued ErrorModel built by a different "
                "call path) is.",
    }


def probe_inadmissible_pair() -> dict:
    """**H1**: an inadmissible ``(code, extractor)`` pair, on the real call."""
    quits = _import_quits()
    import quits.qldpc_code as qc
    from semantics import inadmissible_pairs
    bb = qc.BbCode(**_code_kwargs("BB", "baseline"))
    import contextlib
    import io
    out = {"name": "H1: BB + cardinal is inadmissible",
           "family_whitelist": sorted(bb.supported_strategies),
           "global_registry_strategies": sorted(semantics.DOMAIN["extractor"]),
           "semantic_layer_refuses": ("BB", "cardinal") in inadmissible_pairs()}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            bb.build_circuit(strategy="cardinal")
            out["quits_outcome"] = "assembled"
        except NotImplementedError as exc:
            out["quits_outcome"] = "refused"
            out["exception"] = type(exc).__name__
            out["message"] = str(exc).strip().splitlines()[-1]
    # the semantic layer refuses it *before* the assembly is run
    A = make_stim_assembly()
    try:
        A.evaluate(Spec(code="BB", extractor="cardinal", arch="free",
                        noise="SD6", decoder="BP-OSD"))
        out["semantic_outcome"] = "assembled"
    except ValueError as exc:
        out["semantic_outcome"] = "refused"
        out["semantic_message"] = str(exc)
    return out


def probe_arch_family_restriction() -> dict:
    """**H1, second instance**: ``arch = grid2d`` is only defined for ``BbCode``.

    ``ToricLayout`` dispatches on the code family, so the admissibility of a
    layout is -- like the strategy whitelist -- a property of *another*
    component.  The semantic layer states it as a contract; QUITS raises it.
    """
    import quits.qldpc_code as qc
    from quits.layout import ToricLayout
    out = {"name": "arch = grid2d on a non-BB family", "results": {}}
    for family in ("BB", "HGP", "QLP"):
        code = getattr(qc, CODE_CLASS[family])(**_code_kwargs(family, "baseline"))
        try:
            layout = ToricLayout(code)
            out["results"][family] = {
                "quits_outcome": "assembled",
                "layout": type(layout).__name__,
                "n_positions": len(layout.mapping().data),
                "semantic_contract": True,
            }
        except ValueError as exc:
            out["results"][family] = {
                "quits_outcome": "refused",
                "exception": type(exc).__name__,
                "message": str(exc),
                "semantic_contract": False,
            }
    out["note"] = ("a second hidden cross-component dependency of exactly the "
                   "H1 shape: whether a layout can be used is a property of the "
                   "code component, checked by QUITS at run time and by the "
                   "semantic layer's arch contract before assembly")
    return out


def probe_non_c4_substitution() -> dict:
    """A substitution that violates (C4) must be *refused*, not silently applied.

    A component that writes the ``decoder`` coordinate to a **different value**
    (``BP-OSD`` -> ``BP-LSD``) is a real substitution that is *not* pointwise
    equal on ``R(decoder)``, so Theorem 1 does not apply: (C4) fails and the
    checker refuses.  This is PIVOT_NOTE §8.6 claim 2 -- the checker's job in
    this situation is to *refuse*, and the gate shows that it does.
    """
    toy = make_source_faithful_assembly()
    alt = Component(
        "decoder", READ_SETS_FROM_SOURCE["decoder"],
        lambda s, inp: {"kind": "decoder", "name": "BP-LSD",
                        "hz_shape": (int(inp["code"]["n_data"]) // 2,
                                     int(inp["code"]["n_data"])),
                        "circuit": inp["extractor"]["strategy"]},
        contract=lambda a: a["kind"] == "decoder")
    rep = semantics.theorem1_report(toy, "decoder", alt, semantics.DOMAIN)
    return {
        "name": "decoder value swap (BP-OSD -> BP-LSD)",
        "kind": "a substitution that is NOT pointwise equal on R(x)",
        "checker_applicable": rep["applicable"],
        "checks": rep["checks"],
        "cone_nodes_rerun": rep["cone_nodes_rerun"],
        "note": "the checker's job is to refuse here, and it does: (C4) fails, "
                "so no 'cone 外不变' claim is made",
    }


# ---------------------------------------------------------------------------
# 9. driver
# ---------------------------------------------------------------------------

def _summarize(rows: list[dict], baselines: list[dict], probes: dict) -> dict:
    measured = [r for r in rows]
    return {
        "n_configs": len(baselines),
        "n_substitutions": len(measured),
        "n_circuit_text_equal": sum(1 for r in measured
                                    if r["real"]["stim_circuit_text_equal"]),
        "n_dem_text_equal": sum(1 for r in measured
                                if r["real"]["detector_error_model_text_equal"]),
        "n_all_unchanged_equal": sum(1 for r in measured
                                     if r["real"]["all_provably_unchanged_nodes_equal"]),
        "n_gate_agrees": sum(1 for r in measured if r["gate_agrees"]),
        "all_circuit_text_equal": all(r["real"]["stim_circuit_text_equal"]
                                      for r in measured),
        "all_dem_text_equal": all(r["real"]["detector_error_model_text_equal"]
                                  for r in measured),
        "all_gate_agrees": all(r["gate_agrees"] for r in measured),
        "per_dimension": {
            dim: {
                "substitutions": sum(1 for r in measured if r["dim"] == dim),
                "circuit_text_equal": sum(1 for r in measured
                                          if r["dim"] == dim
                                          and r["real"]["stim_circuit_text_equal"]),
                "dem_text_equal": sum(1 for r in measured
                                      if r["dim"] == dim
                                      and r["real"]["detector_error_model_text_equal"]),
                "gate_agrees": sum(1 for r in measured if r["dim"] == dim
                                   and r["gate_agrees"]),
            } for dim in DIMENSIONS},
        "h3_noise_coordinate_change_is_not_local": not probes["noise_coordinate_change"]["circuit_text_equal"],
        "h1_inadmissible_pair_refused": probes["inadmissible_pair"]["quits_outcome"] == "refused",
        "h1_semantic_layer_agrees": probes["inadmissible_pair"]["semantic_outcome"] == "refused",
        "h1_arch_family_restriction_detected": any(
            v["quits_outcome"] == "refused"
            for v in probes["arch_family_restriction"]["results"].values()),
        "non_c4_substitution_refused_by_checker": not probes["non_c4_substitution"]["checker_applicable"],
        "non_c4_pointwise_equality_fails": probes["non_c4_substitution"]["checks"]["pointwise_equal_on_reads"] is False,
    }


def run(mode: str = "default", quick: bool = False) -> dict:
    """Run the gate.  Results are memoised per ``mode`` so pytest pays once."""
    cache_key = (mode, quick)
    if cache_key in _RUN_CACHE:
        return _RUN_CACHE[cache_key]
    quits = _import_quits()
    semantic = _semantic_verdicts()
    baselines, rows = [], []
    for spec in _configs_for("quick" if quick else mode):
        out = gate_one_config(spec, semantic)
        baselines.append(out["baseline"])
        rows.extend(out["rows"])
    probes = {
        "noise_coordinate_change": probe_noise_coordinate_change(),
        "inadmissible_pair": probe_inadmissible_pair(),
        "arch_family_restriction": probe_arch_family_restriction(),
        "non_c4_substitution": probe_non_c4_substitution(),
    }
    data = {
        "metadata": {
            "description": "Real-artifact gate: Theorem 1's verdict, executed "
                           "on real stim circuits / DEMs",
            "date": date.today().isoformat(),
            "quits_file": quits.__file__,
            "quits_version": getattr(quits, "__version__", "unknown"),
            "pinned_commit": QUITS_COMMIT,
            "mode": "quick" if quick else mode,
            "num_rounds": NUM_ROUNDS,
            "sampler_seed": SAMPLER_SEED,
            "num_shots": NUM_SHOTS,
            "window": WINDOW,
            "overlap": OVERLAP,
            "baseline_assembly": BASELINE_ASSEMBLY,
            "semantic_verdicts_from": "experiments/artifact_invariance.run(48)",
            "assembly_model_sources": semantics.assembly_model_sources(
                [BASELINE_ASSEMBLY]),
            "alt_implementations": ALT_IMPLEMENTATIONS,
        },
        "baselines": baselines,
        "rows": rows,
        "probes": probes,
        "summary": _summarize(rows, baselines, probes),
    }
    _RUN_CACHE[cache_key] = data
    return data


_RUN_CACHE: dict = {}


# ---------------------------------------------------------------------------
# 10. markdown
# ---------------------------------------------------------------------------

def to_markdown(data: dict) -> str:
    m, s = data["metadata"], data["summary"]
    L = ["# Real-Artifact Gate for the Toy Model", "",
         f"Generated: {m['date']}  ",
         f"Object under test: `{m['quits_file']}` (quits {m['quits_version']})  ",
         f"Pinned reference: `{m['pinned_commit']}`  ",
         f"Mode: **{m['mode']}**  ",
         f"Baseline assembly: **`{m['baseline_assembly']}`**  ",
         f"Semantic verdicts read from: `{m['semantic_verdicts_from']}`  ",
         f"Circuit: num_rounds={m['num_rounds']}, sampler seed="
         f"{m['sampler_seed']}, {m['num_shots']} shots, sliding window "
         f"W={m['window']} F={m['overlap']}",
         "",
         "## 0. What this experiment is", "",
         "The semantic layer's ``produce`` functions are a toy model: they "
         "return dicts and strings.  This file rebuilds the same assembly with "
         "**real** QUITS artifacts (a real ``stim.Circuit``, a real detector "
         "error model, real code matrices, a real layout mapping, a real "
         "decoder prediction) and asks whether the semantic layer's verdicts "
         "survive.  The verdict itself is not recomputed here: it is read from "
         "the published ``artifact_invariance`` experiment, so the two levels "
         "are compared on identical input.", "",
         "Per (configuration, dimension) the gate substitutes an alternative "
         "implementation that is **pointwise equal on ``R(x)``** but reached "
         "through a different QUITS call path, and compares, byte for byte:", "",
         "| compared quantity | how |",
         "|---|---|",
         "| stim circuit text | ``str(circuit_before) == str(circuit_after)`` |",
         "| detector error model | ``str(dem_before) == str(dem_after)`` |",
         "| code matrices / layout / decoder | per-node artifact equality |",
         "| Theorem 1 worksheet | every node outside ``{x} ∪ cone(x)`` must be equal |",
         "",
         "## 1. The gate, per configuration", "",
         "| config | dim | semantic verdict | circuit text equal | DEM equal | "
         "all unchanged nodes equal | gate agrees |",
         "|---|---|---|---|:---:|:---:|:---:|:---:|"]
    for r in data["rows"]:
        real, sem = r["real"], r["semantic"]
        L.append(f"| `{r['config']}` | `{r['dim']}` "
                 f"| applicable={sem['applicable']} "
                 f"invariance_ok={sem['invariance_ok']} "
                 f"| **{real['stim_circuit_text_equal']}** "
                 f"| **{real['detector_error_model_text_equal']}** "
                 f"| **{real['all_provably_unchanged_nodes_equal']}** "
                 f"| **{r['gate_agrees']}** |")

    L += ["", "## 2. Baselines (the artifacts both sides must agree on)", "",
          "| config | circuit sha256 | DEM sha256 | circuit chars | "
          "code-family | CSS commutes |",
          "|---|---|---|---:|---|---|"]
    for b in data["baselines"]:
        L.append(f"| `{b['config']}` | `{b['stim_circuit_sha256']}` "
                 f"| `{b['detector_error_model_sha256']}` "
                 f"| {b['stim_circuit_len_chars']} | {b['code_family']} "
                 f"| {b['css_commutes']} |")

    L += ["", "## 3. Alternative implementations (one per dimension)", "",
          "| dimension | alternative call path |", "|---|---|"]
    for dim, text in m["alt_implementations"].items():
        L.append(f"| `{dim}` | {text} |")

    L += ["", "## 4. Negative controls", ""]
    p = data["probes"]
    nc = p["noise_coordinate_change"]
    L += [f"### 4.1 {nc['name']} ({nc['kind']})", "",
          f"- circuit text equal: **{nc['circuit_text_equal']}** "
          f"(`{nc['circuit_sha256_before']}` -> `{nc['circuit_sha256_after']}`)",
          f"- DEM text equal: **{nc['dem_text_equal']}** "
          f"(`{nc['dem_sha256_before']}` -> `{nc['dem_sha256_after']}`)",
          f"- changed nodes: `{', '.join(nc['changed_nodes']) or '-'}`",
          f"- {nc['note']}", ""]
    ip = p["inadmissible_pair"]
    L += [f"### 4.2 {ip['name']}", "",
          f"- family whitelist: `{ip['family_whitelist']}`",
          f"- global registry: `{ip['global_registry_strategies']}`",
          f"- QUITS outcome: **{ip['quits_outcome']}**"
          f"{' (' + ip.get('exception', '') + ')' if ip.get('exception') else ''}",
          f"- semantic layer outcome (before assembly): "
          f"**{ip['semantic_outcome']}**", ""]
    af = p["arch_family_restriction"]
    L += [f"### 4.3 {af['name']}", "",
          "| family | QUITS outcome | semantic contract | n_positions |",
          "|---|:---:|:---:|---:|"]
    for fam, v in af["results"].items():
        L.append(f"| `{fam}` | **{v['quits_outcome']}** "
                 f"| {v['semantic_contract']} "
                 f"| {v.get('n_positions', '-')} |")
    L += ["", f"- {af['note']}", ""]
    n4 = p["non_c4_substitution"]
    L += [f"### 4.4 {n4['name']} ({n4['kind']})", "",
          f"- checker ``applicable``: **{n4['checker_applicable']}** "
          f"(cone: `{', '.join(n4['cone_nodes_rerun']) or '-'}`)",
          f"- (C4) ``pointwise_equal_on_reads``: "
          f"**{n4['checks']['pointwise_equal_on_reads']}** -- this is the side "
          f"condition that fails, and it is why the checker refuses",
          f"- {n4['note']}", ""]

    L += ["## 5. Summary", "",
          f"- configurations: **{s['n_configs']}**, substitutions: "
          f"**{s['n_substitutions']}**",
          f"- stim circuit text equal on every substitution: "
          f"**{s['all_circuit_text_equal']}** "
          f"({s['n_circuit_text_equal']}/{s['n_substitutions']})",
          f"- DEM text equal on every substitution: "
          f"**{s['all_dem_text_equal']}** "
          f"({s['n_dem_text_equal']}/{s['n_substitutions']})",
          f"- every provably-unchanged node equal: "
          f"**{s['n_all_unchanged_equal']}/{s['n_substitutions']}**",
          f"- **gate agrees with the semantic verdict on every row: "
          f"{s['all_gate_agrees']}** "
          f"({s['n_gate_agrees']}/{s['n_substitutions']})",
          "",
          "| dimension | substitutions | circuit equal | DEM equal | gate agrees |",
          "|---|---:|---:|---:|---:|"]
    for dim, v in s["per_dimension"].items():
        L.append(f"| `{dim}` | {v['substitutions']} | {v['circuit_text_equal']} "
                 f"| {v['dem_text_equal']} | {v['gate_agrees']} |")
    L += ["",
          f"- **H3** a noise *coordinate* change is not local (real circuit "
          f"text differs): **{s['h3_noise_coordinate_change_is_not_local']}**",
          f"- **H1** an inadmissible pair is refused by QUITS "
          f"({s['h1_inadmissible_pair_refused']}) and the semantic layer "
          f"refuses the same pair before assembly "
          f"({s['h1_semantic_layer_agrees']})",
          f"- **H1 (second instance)** ``arch = grid2d`` on a non-BB family is "
          f"refused: **{s['h1_arch_family_restriction_detected']}**",
          f"- a non-(C4) substitution is refused by the checker: "
          f"**{s['non_c4_substitution_refused_by_checker']}** "
          f"(pointwise equality holds: "
          f"{not s['non_c4_pointwise_equality_fails']})", "",
          "## 6. What the gate does and does not narrow", "",
          "**Narrowed.** The artifacts are no longer dicts: the assembly layer "
          "produces real stim circuits and detector error models, and Theorem "
          "1's \"unchanged outside `{x} ∪ cone(x)`\" holds byte-for-byte on them "
          "for these configurations.  The toy-model boundary moves from \"the "
          "artifacts are toy\" to \"the artifacts are real, on these "
          "configurations, via these five call paths\".", "",
          "**Not narrowed.** (a) ``--full`` sweeps all 48 configurations; the "
          "default run is the six listed above.  (b) A *distinct* second "
          "implementation of a code family does not exist in QUITS -- the family "
          "constructor is the only path -- so the ``code`` row is a spelling "
          "variant, which is direct evidence for PIVOT_NOTE §8.6 claim 2 "
          "(\"(C4) is not a practical substitution condition\").  (c) The stim "
          "circuit is not a stable artifact: ``dynamic_impact.py`` measured that "
          "its text depends on ``PYTHONHASHSEED``, so this script re-executes "
          "itself with ``PYTHONHASHSEED=0`` and the fingerprints here are "
          "reproducible only under that pin.", ""]
    return "\n".join(L) + "\n"


def _reconfigure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        fn = getattr(stream, "reconfigure", None)
        if fn is None:
            continue
        try:
            fn(encoding="utf-8", errors="replace")
        except (ValueError, OSError):        # pragma: no cover - platform dep.
            pass


def _ensure_hash_seed(argv: list[str] | None = None) -> int | None:
    """Re-run in a child interpreter with ``PYTHONHASHSEED=0``.

    Same reason and same mechanism as ``dynamic_impact._ensure_hash_seed``:
    QUITS' circuit text is not stable under hash randomisation, so the
    fingerprints recorded in this file must be produced under a pinned seed.
    """
    if os.environ.get("PYTHONHASHSEED") == "0":
        return None
    env = dict(os.environ, PYTHONHASHSEED="0")
    script = str(Path(__file__).resolve())
    args = list(sys.argv[1:] if argv is None else argv)
    proc = subprocess.run([sys.executable, script, *args], env=env)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    _reconfigure_stdout()
    rc = _ensure_hash_seed(argv)
    if rc is not None:
        return rc
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = "full" if "--full" in argv else (
        "quick" if "--quick" in argv else "default")
    quick = "--quick" in argv
    data = run(mode, quick=quick)
    out = outdir.resolve_out(argv, HERE)
    (out / "stim_circuit_gate.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "stim_circuit_gate.md").write_text(
        to_markdown(data), encoding="utf-8")
    s = data["summary"]
    print(f"quits: {data['metadata']['quits_file']} "
          f"({data['metadata']['quits_version']})  mode={data['metadata']['mode']}")
    for r in data["rows"]:
        print(f"  {r['config']:36s} {r['dim']:10s} "
              f"circuit_equal={r['real']['stim_circuit_text_equal']} "
              f"dem_equal={r['real']['detector_error_model_text_equal']} "
              f"agrees={r['gate_agrees']}")
    print(f"gate agrees on every row: {s['all_gate_agrees']} "
          f"({s['n_gate_agrees']}/{s['n_substitutions']})")
    print(f"H3 noise coordinate change is not local: "
          f"{s['h3_noise_coordinate_change_is_not_local']}")
    print(f"H1 inadmissible refused by QUITS: "
          f"{s['h1_inadmissible_pair_refused']} / semantic layer: "
          f"{s['h1_semantic_layer_agrees']}")
    print(f"wrote {out / 'stim_circuit_gate.json'}")
    print(f"wrote {out / 'stim_circuit_gate.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())







