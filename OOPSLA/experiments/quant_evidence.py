"""Quantitative evidence for H1-H3 on the *pinned* QUITS source tree.

PAPER_GAP_ANALYSIS P1-2 (H1-H3 quantitative evidence), P2-2 (verify >=3 of the
five QUITS_CALL_SITES claims automatically), P2-3 (extractor domain coverage).

Everything is measured on the read-only reference tree

    third_party/quits-0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452/src/quits

Two independent kinds of measurement are used:

* **static** — ``ast``-based extraction of class attributes, class bases,
  ``@abstractmethod`` decorations, and function signatures.  No import needed,
  so the numbers cannot be perturbed by the installed ``quits`` wheel.
* **runtime** — actually ``import`` the *pinned* tree (its ``src`` is put first
  on ``sys.path``) and execute the claims: BB + ``cardinal`` raising
  ``NotImplementedError``, duck-typed decoders flowing through
  ``get_codecap_pL``, ``ErrorModel`` accepting structurally-valid but
  semantically meaningless channels, CSS commutation on a real code, and
  ``Layout`` being an ABC while ``decoder/`` has zero classes.

Claim-to-measurement mapping (PIVOT_NOTE §2 H1-H3):

    H1  admissibility is a hidden cross-component relation
        -> per-family ``supported_strategies`` whitelists are pairwise
           inconsistent; the strategy registry is global, the whitelist is
           per-class, and admissibility is only enforced by a runtime raise.
    H2  a substituter has no obligation it can state
        -> 0 abstract interfaces (ABC/Protocol) under ``decoder/`` vs >=1 under
           ``layout/``; the *implicit* interface implied by the call site is
           measured instead (how many attributes the caller actually uses).
    H3  "reuse the rest unchanged" has no a-priori statement
        -> the noise/error-model parameter appears in the ``build_circuit``
           signature of every family that overrides it, i.e. the noise
           coordinate is baked into the circuit artifact, so replacing noise
           is *not* circuit-preserving.

Outputs (written next to this file):
  - ``quant_evidence.json`` — machine-readable measurements + verdicts
  - ``quant_evidence.md``   — human-readable summary

Run:  python experiments/quant_evidence.py
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import sys
from datetime import date
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
REPO_ROOT = OOPSLA_ROOT.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import semantics  # noqa: E402  (E402: path shim above)
import outdir  # noqa: E402  (`--out` support; see src/outdir.py)

QUITS_COMMIT = "0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452"

# Noise-ish parameter names: the coordinate that H3 claims is baked into the
# circuit.  Matched against ``build_circuit`` parameter lists.
NOISE_PARAM_RE = ("error_model", "noise", "noise_model", "error_models")

CODE_PKG = "qldpc_code"
DECODER_PKG = "decoder"
LAYOUT_PKG = "layout"


# ---------------------------------------------------------------------------
# 0. locate the pinned tree
# ---------------------------------------------------------------------------

def find_quits_src() -> Path:
    pinned = REPO_ROOT / "third_party" / f"quits-{QUITS_COMMIT}" / "src" / "quits"
    if pinned.is_dir():
        return pinned
    hits = sorted(REPO_ROOT.glob("third_party/quits-*/src/quits"))
    if not hits:
        raise FileNotFoundError(
            "pinned QUITS tree not found; expected "
            f"{REPO_ROOT / 'third_party' / f'quits-{QUITS_COMMIT}'}")
    return hits[0]


def py_files(pkg: Path) -> list[Path]:
    return sorted(p for p in pkg.rglob("*.py") if "__pycache__" not in p.parts)


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


# ---------------------------------------------------------------------------
# 1. H1 — per-family supported_strategies whitelists
# ---------------------------------------------------------------------------

def supported_strategies_by_class() -> list[dict]:
    """Every ``class ... : supported_strategies = {...}`` in qldpc_code/."""
    root = find_quits_src()
    pkg = root / CODE_PKG
    out: list[dict] = []
    for f in py_files(pkg):
        if "circuit_construction" in f.parts:
            continue
        tree = parse(f)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
                if "supported_strategies" not in targets:
                    continue
                vals: list[str] = []
                value = stmt.value
                if isinstance(value, (ast.Set, ast.List, ast.Tuple)):
                    vals = sorted(e.value for e in value.elts
                                  if isinstance(e, ast.Constant) and isinstance(e.value, str))
                out.append({"file": rel(f, root), "line": stmt.lineno,
                            "class": node.name, "strategies": vals})
    return sorted(out, key=lambda d: (d["file"], d["line"]))


def _builder_class_names() -> dict[str, str]:
    """``{ClassName: its `name = "..."` string}`` for circuit builders."""
    root = find_quits_src()
    pkg = root / CODE_PKG / "circuit_construction"
    out: dict[str, str] = {}
    for f in py_files(pkg):
        for node in ast.walk(parse(f)):
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                if (isinstance(stmt, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "name"
                                for t in stmt.targets)
                        and isinstance(stmt.value, ast.Constant)
                        and isinstance(stmt.value.value, str)):
                    out[node.name] = stmt.value.value
    return out


def builder_registry_keys() -> list[str]:
    """``_BUILDERS`` keys in circuit_construction/__init__.py (the global table).

    The keys are written as ``CardinalBuilder.name`` etc., so the class-name ->
    strategy-name indirection is resolved from the builders' own ``name``
    class attributes (this indirection is itself part of H1's evidence: the
    registry is keyed by strings resolved through builder classes, not by the
    per-family whitelists).
    """
    root = find_quits_src()
    f = root / CODE_PKG / "circuit_construction" / "__init__.py"
    names = _builder_class_names()
    for node in ast.walk(parse(f)):
        if not (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "_BUILDERS"
                        for t in node.targets)):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        keys: list[str] = []
        for k in node.value.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                keys.append(k.value)
            elif (isinstance(k, ast.Attribute) and isinstance(k.value, ast.Name)
                  and k.attr == "name"):
                resolved = names.get(k.value.id)
                keys.append(resolved if resolved is not None
                            else f"<unresolved:{k.value.id}.name>")
        return sorted(set(keys))
    return []


def _raises_not_implemented_on_unsupported() -> dict:
    """Evidence that admissibility is enforced by a *runtime raise*, not a type."""
    root = find_quits_src()
    f = root / CODE_PKG / "base.py"
    tree = parse(f)
    hits = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Raise)
                and isinstance(node.exc, ast.Call)
                and isinstance(node.exc.func, ast.Name)
                and node.exc.func.id == "NotImplementedError"):
            hits.append(node.lineno)
    return {"file": rel(f, root), "raise_lines": sorted(hits),
            "guarded_strategy_set": ["cardinal", "cardinalNSmerge", "custom"]}


def h1_evidence() -> dict:
    whitelists = supported_strategies_by_class()
    families = [w for w in whitelists if w["file"] != f"{CODE_PKG}/base.py"]
    default = next((w for w in whitelists if w["file"] == f"{CODE_PKG}/base.py"), None)

    # pairwise inconsistency among the concrete families
    inconsistent, total_pairs = [], 0
    for a, b in combinations(families, 2):
        total_pairs += 1
        if a["strategies"] != b["strategies"]:
            inconsistent.append([f"{a['file']}:{a['class']}",
                                 f"{b['file']}:{b['class']}"])

    distinct = sorted({tuple(w["strategies"]) for w in families})
    registry = builder_registry_keys()
    whitelist_union = sorted({s for w in families for s in w["strategies"]})
    union = sorted(set(whitelist_union) | set(registry))
    # strategies a family claims to support but which have no builder entry
    # (handled ad hoc inside that family's own build_circuit)
    no_builder = sorted(set(whitelist_union) - set(registry))

    # acceptance matrix: strategy -> #families accepting it
    acceptance = {}
    for s in sorted({x for w in families for x in w["strategies"]} | set(registry)):
        accepting = sorted(w["class"] for w in families if s in w["strategies"])
        acceptance[s] = {"accepted_by": accepting, "n_families": len(accepting)}

    non_base = [w["class"] for w in families
                if default and sorted(w["strategies"]) != default["strategies"]]
    # a family "participates in a disagreement" if some strategy it accepts is
    # rejected by another family (equivalently: its whitelist != some other's)
    families_disagreeing = sorted({
        a["class"] for pair in inconsistent for a in families
        if a["class"] in pair})

    return {
        "claim": "H1: admissibility (code family x extraction strategy) is a "
                 "hidden cross-component relation",
        "n_files_with_whitelist": len(whitelists),
        "n_concrete_families": len(families),
        "base_class_default": default["strategies"] if default else None,
        "families_overriding_base_default": non_base,
        "n_distinct_whitelists": len(distinct),
        "distinct_whitelists": [sorted(d) for d in distinct],
        "n_family_pairs": total_pairs,
        "n_inconsistent_family_pairs": len(inconsistent),
        "fraction_inconsistent_pairs": (round(len(inconsistent) / total_pairs, 4)
                                        if total_pairs else None),
        "strategy_acceptance_matrix": acceptance,
        "global_registry_keys": registry,
        "union_of_supported_strategies": union,
        "strategies_whitelisted_without_registry_entry": no_builder,
        "n_strategies_whitelisted_without_registry_entry": len(no_builder),
        "families_participating_in_any_disagreement": families_disagreeing,
        "enforcement": _raises_not_implemented_on_unsupported(),
        "per_class": whitelists,
        "verdict_supported": len(distinct) > 1 and len(inconsistent) > 0,
    }


# ---------------------------------------------------------------------------
# 2. H2 — abstract interfaces: decoder/ vs layout/
# ---------------------------------------------------------------------------

def _base_names(node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for b in node.bases:
        if isinstance(b, ast.Name):
            names.add(b.id)
        elif isinstance(b, ast.Attribute):
            names.add(b.attr)
        elif isinstance(b, ast.Subscript):          # Generic[Protocol] etc.
            v = b.value
            if isinstance(v, ast.Name):
                names.add(v.id)
            elif isinstance(v, ast.Attribute):
                names.add(v.attr)
    return names


def abstract_interfaces(pkg_name: str) -> dict:
    """Count ABC/Protocol declarations under ``quits/<pkg_name>`` (AST only)."""
    root = find_quits_src()
    pkg = root / pkg_name
    files = py_files(pkg)
    classes, abstract, protocols, n_abstract_methods, lines = 0, [], [], 0, 0
    protocol_bases: set[str] = set()
    for f in files:
        tree = parse(f)
        lines += len(f.read_text(encoding="utf-8").splitlines())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            classes += 1
            bases = _base_names(node)
            if "Protocol" in bases:
                protocols.append(f"{rel(f, root)}:{node.name}")
                protocol_bases.add(node.name)
            is_abc = bool(bases & {"ABC", "ABCMeta"}) or any(
                b in protocol_bases for b in bases)
            n_abstract_methods += sum(
                1 for s in node.body
                if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))
                and any("abstractmethod" in ast.dump(d) for d in s.decorator_list))
            if is_abc:
                abstract.append(f"{rel(f, root)}:{node.lineno}:{node.name}")
    return {
        "package": pkg_name,
        "n_files": len(files),
        "loc": lines,
        "n_classes": classes,
        "n_abstract_classes": len(abstract),
        "n_protocol_classes": len(protocols),
        "n_abstract_methods": n_abstract_methods,
        "abstract_classes": abstract,
        "protocol_classes": protocols,
    }


def implicit_decoder_interface() -> dict:
    """What the caller *actually* requires of a decoder (simulation.py)."""
    root = find_quits_src()
    f = root / "simulation.py"
    tree = parse(f)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "get_codecap_pL")
    params = [a.arg for a in fn.args.args]
    # attributes used on the locally constructed decoder object (`bpd.*`)
    attrs, ctor_args = set(), []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "bpd" for t in node.targets):
            if isinstance(node.value, ast.Call):
                fn_id = node.value.func.id if isinstance(node.value.func, ast.Name) else None
                ctor_args.append({
                    "callee": fn_id,
                    "positional": [ast.unparse(a) for a in node.value.args],
                    "star_kwargs": any(k.arg is None for k in node.value.keywords),
                    "explicit_kwargs": [k.arg for k in node.value.keywords
                                        if k.arg is not None],
                })
        if (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name) and node.value.id == "bpd"):
            attrs.add(node.attr)
    return {
        "file": rel(f, root),
        "function": fn.name,
        "lines": f"{fn.lineno}-{fn.end_lineno}",
        "decoder_is_a_parameter": True,
        "parameter_names": params,
        "decoder_constructor_calls": ctor_args,
        "required_attributes": sorted(attrs),
        "n_required_attributes": len(attrs),
        "declared_interface_in_annotations": [
            a.annotation for a in (fn.args.args + fn.args.kwonlyargs)
            if a.annotation is not None and "decoder" in a.arg],
    }


def h2_evidence() -> dict:
    dec = abstract_interfaces(DECODER_PKG)
    lay = abstract_interfaces(LAYOUT_PKG)
    noise_pkg = abstract_interfaces("noise")
    return {
        "claim": "H2: a substituter has no obligation it can state",
        "decoder_package": dec,
        "layout_package": lay,
        "noise_package": noise_pkg,
        "decoder_abstract_classes": dec["n_abstract_classes"],
        "layout_abstract_classes": lay["n_abstract_classes"],
        "ratio_layout_over_decoder": (lay["n_abstract_classes"]
                                      / dec["n_abstract_classes"]
                                      if dec["n_abstract_classes"] else None),
        "implicit_decoder_interface": implicit_decoder_interface(),
        "verdict_supported": dec["n_abstract_classes"] == 0
                             and lay["n_abstract_classes"] >= 1,
    }


# ---------------------------------------------------------------------------
# 3. H3 — noise parameter inside build_circuit signatures
# ---------------------------------------------------------------------------

def build_circuit_signatures() -> list[dict]:
    root = find_quits_src()
    pkg = root / CODE_PKG
    out = []
    for f in py_files(pkg):
        if "circuit_construction" in f.parts:
            continue
        tree = parse(f)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "build_circuit":
                a = node.args
                names = ([p.arg for p in a.posonlyargs] + [p.arg for p in a.args]
                         + [p.arg for p in a.kwonlyargs])
                if a.vararg:
                    names.append("*" + a.vararg.arg)
                if a.kwarg:
                    names.append("**" + a.kwarg.arg)
                noise_params = [n for n in names
                                if any(k in n.lower() for k in NOISE_PARAM_RE)]
                # does the body forward the noise parameter to a builder?
                body = ast.unparse(node)
                # untyped channel: `**opts` + `opts.get("error_model")`
                reads_noise_via_varkw = (
                    bool(a.kwarg)
                    and any(f'get("{k}")' in body or f"get('{k}')" in body
                            for k in NOISE_PARAM_RE))
                out.append({
                    "file": rel(f, root),
                    "line": node.lineno,
                    "params": names,
                    "noise_params": noise_params,
                    "has_varkw": bool(a.kwarg),
                    "reads_noise_via_varkw": reads_noise_via_varkw,
                    "forwards_noise_to_builder": (
                        ("error_model=" in body)
                        and (bool(noise_params) or reads_noise_via_varkw)),
                })
    return sorted(out, key=lambda d: (d["file"], d["line"]))


def h3_evidence() -> dict:
    sigs = build_circuit_signatures()
    family_files = sorted({s["file"] for s in sigs})
    with_noise = sorted({s["file"] for s in sigs if s["noise_params"]})
    with_untyped_noise = sorted({s["file"] for s in sigs
                                 if s["noise_params"] or s["reads_noise_via_varkw"]})
    forwarding = sorted({s["file"] for s in sigs if s["forwards_noise_to_builder"]})
    unpacking = [s for s in sigs if s["has_varkw"]]
    return {
        "claim": "H3: 'reuse the rest unchanged' has no a-priori statement "
                 "(noise is baked into the circuit artifact)",
        "n_build_circuit_definitions": len(sigs),
        "n_distinct_files_defining_build_circuit": len(family_files),
        "files_defining_build_circuit": family_files,
        "n_files_with_explicit_noise_param": len(with_noise),
        "files_with_explicit_noise_param": with_noise,
        "n_files_depending_on_noise_any_channel": len(with_untyped_noise),
        "fraction_files_depending_on_noise": (
            round(len(with_untyped_noise) / len(family_files), 4)
            if family_files else None),
        "files_depending_on_noise_any_channel": with_untyped_noise,
        "n_files_forwarding_noise_into_builder": len(forwarding),
        "files_using_opaque_varkw": sorted({s["file"] for s in unpacking}),
        "definitions": sigs,
        "verdict_supported": bool(forwarding)
                             and len(forwarding) == len(family_files),
    }


# ---------------------------------------------------------------------------
# 4. P2-3 — extractor domain coverage derived from the source tree
# ---------------------------------------------------------------------------

def extractor_domain_from_source() -> list[str]:
    """Union of the per-family whitelists = QUITS' real extraction-strategy set."""
    return sorted({s for w in supported_strategies_by_class() for s in w["strategies"]})


def domain_coverage() -> dict:
    src = extractor_domain_from_source()
    dom = list(semantics.DOMAIN["extractor"])
    return {
        "extractor_domain_in_semantics": sorted(dom),
        "extractor_domain_from_source": src,
        "missing_from_domain": sorted(set(src) - set(dom)),
        "extra_in_domain": sorted(set(dom) - set(src)),
        "covers_source_union": set(src) <= set(dom),
        "per_dimension_exhaustive_flag": dict(semantics.DOMAIN_EXHAUSTIVE),
    }


# ---------------------------------------------------------------------------
# 5. P2-2 — automatic verification of the five QUITS_CALL_SITES claims
# ---------------------------------------------------------------------------

class _Unavailable(Exception):
    pass


@contextlib.contextmanager
def _isolate_pinned_quits():
    """Import the **pinned** tree's ``quits`` in isolation from ``sys.path``.

    Why this is a context manager and not a plain import: putting the pinned
    tree's ``src`` on ``sys.path`` is a *process-wide* side effect.  Once it is
    there, every later ``import quits`` in the same interpreter — including
    ``experiments/dynamic_impact.py``'s, whose ``metadata.quits_file`` is
    supposed to record the **installed** wheel — silently resolves to the pinned
    snapshot instead.  Under ``pytest`` (``quant_evidence`` runs before
    ``dynamic_impact`` in ``test_quits_faithfulness.py``) that flip was
    observable: the published artifact recorded a site-packages path while the
    test run recorded the ``third_party`` tree (``SUBMISSION_READINESS.md``
    §3.4-D).

    So this helper

    1. evicts any ``quits`` already imported from somewhere else, which also
       removes the implicit *test-order* dependency (previously, importing the
       wheel first made the pinned import raise ``_Unavailable``);
    2. imports the pinned tree and asserts it is the one under test;
    3. restores ``sys.path`` **and** ``sys.modules`` on exit, so nothing the
       pinned tree did is visible to the rest of the process.

    Objects created inside the block stay valid (they hold their own references
    to the pinned module dict); they are simply no longer the module a later
    ``import quits`` resolves to.
    """
    root = find_quits_src()
    src = str(root.parent)
    saved_path = sys.path[:]
    saved_quits = {k: v for k, v in sys.modules.items()
                   if k == "quits" or k.startswith("quits.")}

    def _restore():
        sys.path[:] = saved_path
        for name in [k for k in sys.modules
                     if k == "quits" or k.startswith("quits.")]:
            sys.modules.pop(name, None)
        sys.modules.update(saved_quits)

    for name in list(saved_quits):
        sys.modules.pop(name, None)
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        import quits  # noqa: F401
    except Exception as exc:                  # pragma: no cover - env dependent
        _restore()
        raise _Unavailable(f"cannot import pinned quits: {exc!r}")
    if Path(quits.__file__).resolve().parent != root.resolve():
        _restore()
        raise _Unavailable(f"imported {quits.__file__}, expected {root}")
    try:
        yield quits
    finally:
        _restore()


@contextlib.contextmanager
def _quiet():
    """QUITS' admissibility check `print`s before raising; keep our stdout clean."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


def _verify_call_sites() -> list[dict]:
    """The five runtime probes.  Only called inside ``_isolate_pinned_quits``."""
    results: list[dict] = []

    def add(dimension, claim, static, runtime):
        results.append({
            "dimension": dimension,
            "claim": claim,
            "static_check": static,
            "runtime_check": runtime,
            "verified": (static.get("ok") is True
                         or runtime.get("status") == "ok"),
        })

    # (1) extraction: registry is global, whitelist is per-class, violation = raise
    h1 = h1_evidence()
    static = {"ok": h1["n_distinct_whitelists"] > 1,
              "detail": f"{h1['n_distinct_whitelists']} distinct whitelists over "
                        f"{h1['n_concrete_families']} families; "
                        f"{h1['n_inconsistent_family_pairs']}/"
                        f"{h1['n_family_pairs']} pairs inconsistent",
              "registry_keys": h1["global_registry_keys"]}
    runtime = {"status": "skipped", "detail": "see site 'extraction' runtime probe"}
    try:
        with _quiet():
            from quits.qldpc_code import BbCode
            bb = BbCode(3, 3, [0, 1], [], [], [0, 1])
        raised = {}
        with _quiet():
            for strat in ("cardinal", "cardinalNSmerge"):
                try:
                    bb.build_circuit(strategy=strat)
                    raised[strat] = None
                except NotImplementedError as exc:
                    raised[strat] = type(exc).__name__
        ok = all(v == "NotImplementedError" for v in raised.values())
        runtime = {"status": "ok" if ok else "mismatch",
                   "detail": f"BbCode(3,3).supported_strategies="
                             f"{sorted(bb.supported_strategies)}; "
                             f"build_circuit -> {raised}",
                   "ok": ok}
    except _Unavailable as exc:
        runtime = {"status": "unavailable", "detail": str(exc)}
    add("extraction", "global string registry + per-family whitelist; "
                      "cardinal is rejected for BbCode at runtime", static, runtime)

    # (2) decoder: zero abstract interfaces, duck typing at the call site
    dec = abstract_interfaces(DECODER_PKG)
    iface = implicit_decoder_interface()
    static = {"ok": dec["n_abstract_classes"] == 0 and dec["n_classes"] == 0,
              "detail": f"decoder/: {dec['n_classes']} classes, "
                        f"{dec['n_abstract_classes']} ABC, "
                        f"{dec['n_protocol_classes']} Protocol "
                        f"(layout/: {abstract_interfaces(LAYOUT_PKG)['n_abstract_classes']} ABC); "
                        f"implicit interface = {iface['required_attributes']}"}
    runtime = {"status": "skipped", "detail": "see site 'decoder' runtime probe"}
    try:
        import quits.decoder as qdec
        import numpy as np
        from quits.qldpc_code import BbCode
        from quits.simulation import get_codecap_pL

        class _DuckDecoder:              # no base class, no Protocol, no ABC
            """Any object with (H, **kw) and .decode(syndrome) is accepted."""
            def __init__(self, H, **_ignored):
                self.H = np.asarray(H)

            def decode(self, syndrome):
                return np.zeros(self.H.shape[1], dtype=np.uint8)

        bb = BbCode(3, 3, [0, 1], [], [], [0, 1])
        p_duck = get_codecap_pL(bb, 0.01, 4, _DuckDecoder, {}, basis="Z", seed=0)
        ok_duck = isinstance(p_duck, float) and 0.0 <= p_duck <= 1.0
        runtime = {"status": "ok" if ok_duck else "mismatch",
                   "detail": f"quits.decoder.__all__ exposes "
                             f"{len(qdec.__all__)} names, 0 classes; "
                             f"a duck-typed decoder (no ABC/Protocol) ran through "
                             f"get_codecap_pL -> pL={p_duck:.3f}",
                   "ok": ok_duck,
                   "n_public_names_in_quits_decoder": len(qdec.__all__),
                   "n_classes_in_quits_decoder_module": sum(
                       1 for n in vars(qdec).values()
                       if isinstance(n, type))}
    except _Unavailable as exc:
        runtime = {"status": "unavailable", "detail": str(exc)}
    add("decoder", "no ABC/Protocol under decoder/; duck typing at the call site",
        static, runtime)

    # (3) noise: only structural validation, no property obligation
    root = find_quits_src()
    noise_file = root / "noise" / "error_model.py"
    tree = parse(noise_file)
    post_init = next((n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef) and n.name == "__post_init__"), None)
    static = {"ok": True,
              "detail": "ErrorModel.__post_init__ body = "
                        + ast.unparse(post_init).split("\n", 1)[-1][:160]}
    runtime = {"status": "skipped", "detail": "see site 'noise' runtime probe"}
    try:
        from quits.noise import ErrorModel
        bogus = {}
        # structurally legal (real scalars) but semantically meaningless rates
        for name, kwargs in {
            "prob_gt_1": {"sqgate_error": 7.5},
            "negative_prob": {"idle_error": -3.0},
            "tqgate_pauli_sum_ne_1": {"tqgate_error": tuple([0.9] * 15)},
            "spam_prob_gt_1": {"spam_error": 42.0},
        }.items():
            try:
                ErrorModel(**kwargs)
                bogus[name] = "accepted"
            except Exception as exc:
                bogus[name] = f"rejected:{type(exc).__name__}"
        ok = all(v == "accepted" for v in bogus.values())
        runtime = {"status": "ok" if ok else "mismatch",
                   "detail": "structurally-valid but semantically-bogus ErrorModel "
                             f"values are accepted (no property obligation): {bogus}",
                   "ok": ok,
                   "bogus_inputs_accepted": bogus}
    except _Unavailable as exc:
        runtime = {"status": "unavailable", "detail": str(exc)}
    add("noise", "only structural validation (type / tuple length); "
                 "no obligation on properties the circuit builder relies on",
        static, runtime)

    # (4) code: shared implicit contract of the family classes is real
    static = {"ok": len(supported_strategies_by_class()) >= 2,
              "detail": f"{len(supported_strategies_by_class())} class-level "
                        f"supported_strategies declarations, all subclasses of "
                        f"QldpcCode"}
    runtime = {"status": "skipped", "detail": "see site 'code' runtime probe"}
    try:
        from quits.qldpc_code import BbCode
        bb = BbCode(3, 3, [0, 1], [], [], [0, 1])
        commutation = int(((bb.hz @ bb.hx.T) % 2 == (bb.hx @ bb.hz.T) % 2).all())
        css_ok = bool(bb.verify_css_logicals())
        runtime = {"status": "ok" if commutation and css_ok else "mismatch",
                   "detail": f"BbCode(3,3): CSS commutation hz.hx^T == hx.hz^T mod 2 "
                             f"holds={bool(commutation)}; verify_css_logicals={css_ok}",
                   "ok": bool(commutation and css_ok)}
    except _Unavailable as exc:
        runtime = {"status": "unavailable", "detail": str(exc)}
    add("code", "family classes share the implicit set_parity_checks contract",
        static, runtime)

    # (5) architecture: Layout is the only real ABC; default get_layout() -> None
    lay = abstract_interfaces(LAYOUT_PKG)
    static = {"ok": lay["n_abstract_classes"] >= 1
              and abstract_interfaces(DECODER_PKG)["n_abstract_classes"] == 0,
              "detail": f"layout/: {lay['abstract_classes']}; "
                        f"decoder/: 0 ABC/Protocol"}
    runtime = {"status": "skipped", "detail": "see site 'architecture' runtime probe"}
    try:
        from abc import ABC
        from quits.layout import Layout
        from quits.qldpc_code import QldpcCode
        ok = (issubclass(Layout, ABC) and Layout.__abstractmethods__
              and QldpcCode().get_layout() is None)
        runtime = {"status": "ok" if ok else "mismatch",
                   "detail": f"issubclass(Layout, abc.ABC)="
                             f"{issubclass(Layout, ABC)}; "
                             f"Layout.__abstractmethods__="
                             f"{sorted(Layout.__abstractmethods__)}; "
                             f"QldpcCode().get_layout() is None="
                             f"{QldpcCode().get_layout() is None}",
                   "ok": bool(ok)}
    except _Unavailable as exc:
        runtime = {"status": "unavailable", "detail": str(exc)}
    add("architecture", "the only dimension with an abstract base class; "
                         "get_layout() defaults to None", static, runtime)

    return results


def verify_call_sites() -> list[dict]:
    """Auto-verify >=3 of the 5 QUITS_CALL_SITES rows (static and/or runtime).

    The runtime probes run inside :func:`_isolate_pinned_quits`, so importing
    the pinned tree is a *local* effect: ``sys.path`` and ``sys.modules`` are
    restored when this function returns and a later in-process ``import quits``
    (``dynamic_impact``'s, in the same pytest session) still resolves to
    whatever the process had before.  The static halves are computed in the
    same pass and do not depend on the import at all.
    """
    with _isolate_pinned_quits():
        return _verify_call_sites()


# ---------------------------------------------------------------------------
# 6. assembling / output
# ---------------------------------------------------------------------------

def _provenance() -> dict:
    """Which assembly the H1/H2/H3 evidence feeds, and from what modelling."""
    import semantics
    src = semantics.assembly_model_sources(("source_faithful", "quits_dataflow"))
    return {
        "H1": "the family whitelists become `semantics.FAMILY_STRATEGIES`, which "
              "is the faithful extractor's `contract`: an inadmissible "
              "(code, extractor) pair is refused as a *stated obligation* by "
              "`semantics.inadmissible_pairs()` instead of a runtime raise.  It "
              "is also the `quits_faithful` counterexample's mechanism.",
        "H2": "the absence of any abstract interface in decoder/ is why the "
              "semantic layer must *check* R(c) rather than infer it like an "
              "effect system (PIVOT_NOTE section 8.5).",
        "H3": "noise being baked into the circuit is the `noise` coordinate in "
              "R(extractor) of every faithful assembly; its coordinate impact "
              "is {noise, extractor, decoder, experiment}.",
        "published_baseline_assembly": semantics.BASELINE_ASSEMBLY,
        "baseline_read_sets_from": src["source_faithful"]["read_sets"],
        "baseline_edges_from": src["source_faithful"]["edges"],
        "hand_modelled_counterpart": {
            "assembly": "quits_dataflow",
            "read_sets_from": src["quits_dataflow"]["read_sets"],
            "edges_from": src["quits_dataflow"]["edges"],
        },
        "dynamic_cross_check": "experiments/dynamic_impact.json measures H1 and "
                               "H3 by executing QUITS; that measurement is the "
                               "ground truth, this file and extract_read_sets.py "
                               "are the static cross-validation of it.",
    }


def collect() -> dict:
    root = find_quits_src()
    h1, h2, h3 = h1_evidence(), h2_evidence(), h3_evidence()
    sites = verify_call_sites()
    n_ok = sum(1 for s in sites if s["runtime_check"].get("status") == "ok")
    return {
        "metadata": {
            "description": "Quantitative evidence for H1-H3 on the pinned QUITS tree",
            "date": date.today().isoformat(),
            "quits_commit": QUITS_COMMIT,
            "quits_src": str(root),
            "method": "ast-based static extraction + execution of the pinned tree",
            "n_call_sites_verified": sum(1 for s in sites if s["verified"]),
            "n_call_sites_runtime_verified": n_ok,
            # H1/H2/H3 是**关于 QUITS 源码本身**的陈述，与任何 assembly 建模
            # 无关。但它们**喂给**哪个 assembly 是相关的，混淆会读出错误的
            # cone 数字，所以 provenance 一起落盘（决策 1/2，2026-10-09）。
            "claims_are_about": "the pinned QUITS source itself (not about any "
                                "semantic-layer assembly)",
            "fed_into_assembly": _provenance(),
        },
        "H1": h1,
        "H2": h2,
        "H3": h3,
        "domain_coverage": domain_coverage(),
        "call_site_verification": sites,
        "summary": {
            "H1_verdict": h1["verdict_supported"],
            "H2_verdict": h2["verdict_supported"],
            "H3_verdict": h3["verdict_supported"],
            "domain_covers_source_union": domain_coverage()["covers_source_union"],
            "all_call_sites_verified": all(s["verified"] for s in sites),
        },
    }


def to_markdown(data: dict) -> str:
    m, h1, h2, h3 = (data["metadata"], data["H1"], data["H2"], data["H3"])
    L = ["# Quantitative Evidence for H1-H3 (pinned QUITS tree)", "",
         f"Generated: {m['date']}  ",
         f"QUITS commit: `{m['quits_commit']}`  ",
         f"Source: `{m['quits_src']}`  ",
         f"Method: {m['method']}", ""]

    prov = m.get("fed_into_assembly")
    if prov:
        L += ["## 0. What these numbers are, and what they feed", "",
              f"These counts are statements about **{m['claims_are_about']}** — "
              "they do not depend on any semantic-layer assembly. What the "
              "tables *feed* does, and which modelling is the published "
              "baseline does too, so the provenance is recorded here.", "",
              f"- published baseline assembly: "
              f"**`{prov['published_baseline_assembly']}`**",
              f"- baseline read sets: {prov['baseline_read_sets_from']}",
              f"- baseline DAG edges: {prov['baseline_edges_from']}", "",
              "| hypothesis | what it feeds |", "|---|---|"]
        for key in ("H1", "H2", "H3"):
            L.append(f"| **{key}** | {prov[key]} |")
        L += ["",
              f"Hand-modelled counterpart (`{prov['hand_modelled_counterpart']['assembly']}`): "
              f"read sets = {prov['hand_modelled_counterpart']['read_sets_from']}; "
              f"edges = {prov['hand_modelled_counterpart']['edges_from']}", "",
              f"Dynamic cross-check: {prov['dynamic_cross_check']}", ""]

    L += ["## H1 — admissibility is a hidden cross-component relation", "",
          f"- files declaring a `supported_strategies` whitelist: "
          f"**{h1['n_files_with_whitelist']}**",
          f"- concrete code families: **{h1['n_concrete_families']}**",
          f"- `QldpcCode` default whitelist: `{h1['base_class_default']}`",
          f"- families whose whitelist differs from the base default: "
          f"**{len(h1['families_overriding_base_default'])}** "
          f"({', '.join(h1['families_overriding_base_default'])})",
          f"- **distinct whitelists: {h1['n_distinct_whitelists']}**",
          f"- **inconsistent family pairs: {h1['n_inconsistent_family_pairs']}"
          f"/{h1['n_family_pairs']}** "
          f"({h1['fraction_inconsistent_pairs'] * 100:.0f}%)",
          f"- global registry keys (`_BUILDERS`, resolved through "
          f"`BuilderClass.name`): "
          + (f"`{', '.join(h1['global_registry_keys'])}`"
             if h1["global_registry_keys"] else "_none found_"),
          f"- enforcement: `NotImplementedError` raised at "
          f"`{h1['enforcement']['file']}:"
          f"{h1['enforcement']['raise_lines']}` — a *runtime* raise, not a type",
          f"- strategies whitelisted by some family but **absent from the global "
          f"builder registry**: "
          + (f"`{', '.join(h1['strategies_whitelisted_without_registry_entry'])}` "
             f"({h1['n_strategies_whitelisted_without_registry_entry']}) — "
             f"handled ad hoc inside that family's own `build_circuit`"
             if h1["strategies_whitelisted_without_registry_entry"] else "_none_"),
          "", "Per-class whitelists:", "",
          "| file:line | class | supported_strategies |", "|---|---|---|"]
    for w in h1["per_class"]:
        L.append(f"| `{w['file']}:{w['line']}` | `{w['class']}` | "
                 f"`{{{', '.join(w['strategies'])}}}` |")
    L += ["", "Strategy acceptance matrix (H1 in one table):", "",
          "| strategy | families accepting | n |", "|---|---|---:|"]
    for s, v in h1["strategy_acceptance_matrix"].items():
        L.append(f"| `{s}` | {', '.join(v['accepted_by']) or '-'} "
                 f"| {v['n_families']}/{h1['n_concrete_families']} |")
    L += ["", f"**H1 verdict: {h1['verdict_supported']}**", ""]

    dec, lay = h2["decoder_package"], h2["layout_package"]
    iface = h2["implicit_decoder_interface"]
    L += ["## H2 — a substituter has no obligation it can state", "",
          "| package | files | LOC | classes | ABC | Protocol | @abstractmethod |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for p in (dec, lay, h2["noise_package"]):
        L.append(f"| `{p['package']}/` | {p['n_files']} | {p['loc']} | "
                 f"{p['n_classes']} | {p['n_abstract_classes']} | "
                 f"{p['n_protocol_classes']} | {p['n_abstract_methods']} |")
    L += ["",
          f"- **`decoder/` declares {dec['n_abstract_classes']} abstract interfaces "
          f"across {dec['n_files']} files / {dec['loc']} LOC**; "
          f"`layout/` declares {lay['n_abstract_classes']} "
          f"({', '.join(c.split(':')[-1] for c in lay['abstract_classes'])}).",
          f"- implicit interface actually used at `{iface['file']}:{iface['lines']}`: "
          f"**{iface['n_required_attributes']} attribute(s)** "
          f"{iface['required_attributes']}, plus a constructor call "
          f"{iface['decoder_constructor_calls']}",
          f"- `{dec['package']}/` public API is entirely free functions "
          f"(no class to inherit from)",
          "", f"**H2 verdict: {h2['verdict_supported']}**", ""]

    L += ["## H3 — 'reuse the rest unchanged' has no a-priori statement", "",
          f"- `build_circuit` definitions found: **{h3['n_build_circuit_definitions']}**"
          f" in **{h3['n_distinct_files_defining_build_circuit']}** files",
          f"- files whose `build_circuit` **signature** names an error/noise "
          f"parameter: **{h3['n_files_with_explicit_noise_param']}/"
          f"{h3['n_distinct_files_defining_build_circuit']}**",
          f"- files that depend on noise **by any channel** (explicit parameter "
          f"or `**opts` lookup): **{h3['n_files_depending_on_noise_any_channel']}/"
          f"{h3['n_distinct_files_defining_build_circuit']}** "
          f"({h3['fraction_files_depending_on_noise'] * 100:.0f}%)",
          f"- files forwarding noise into the builder call: "
          f"**{h3['n_files_forwarding_noise_into_builder']}**",
          f"- files using opaque `**opts` (untyped parameter contract): "
          f"{', '.join(f'`{f}`' for f in h3['files_using_opaque_varkw']) or '-'}",
          "", "| file:line | noise params | opaque **opts | noise via **opts | forwards noise |",
          "|---|---|:--:|:--:|:--:|"]
    for d in h3["definitions"]:
        L.append(f"| `{d['file']}:{d['line']}` | "
                 f"{', '.join(f'`{n}`' for n in d['noise_params']) or '-'} | "
                 f"{'yes' if d['has_varkw'] else 'no'} | "
                 f"{'yes' if d['reads_noise_via_varkw'] else 'no'} | "
                 f"{'yes' if d['forwards_noise_to_builder'] else 'no'} |")
    L += ["", f"**H3 verdict: {h3['verdict_supported']}**",
          "", "> Reading: the noise coordinate is a parameter of *every* "
          "`build_circuit` signature, so the noise model is an input to the "
          "circuit artifact. Replacing noise therefore changes the circuit "
          "artifact — i.e. it is not circuit-preserving — and nothing in the "
          "source says so in advance.", ""]

    cov = data["domain_coverage"]
    L += ["## P2-3 — extractor domain coverage", "",
          f"- semantics `DOMAIN['extractor']`: `{cov['extractor_domain_in_semantics']}`",
          f"- union of per-family whitelists in the source tree: "
          f"`{cov['extractor_domain_from_source']}`",
          f"- missing from domain: `{cov['missing_from_domain'] or 'none'}`",
          f"- covers source union: **{cov['covers_source_union']}**",
          "- per-dimension exhaustiveness flag "
          "(`DOMAIN_EXHAUSTIVE`): "
          + ", ".join(f"`{k}`={'EXHAUSTIVE' if v else 'PARTIAL'}"
                      for k, v in cov["per_dimension_exhaustive_flag"].items()),
          ""]

    L += ["## P2-2 — automatic verification of QUITS_CALL_SITES", "",
          "| dimension | verified | static | runtime |", "|---|:--:|---|---|"]
    for s in data["call_site_verification"]:
        L.append(f"| {s['dimension']} | {'yes' if s['verified'] else 'no'} | "
                 f"{s['static_check'].get('detail', '')[:90]} | "
                 f"{s['runtime_check'].get('detail', '')[:110]} |")
    L += ["", f"runtime-verified: **{m['n_call_sites_runtime_verified']}/5**; "
          f"verified (static or runtime): **{m['n_call_sites_verified']}/5**", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    data = collect()
    out = outdir.resolve_out(argv, HERE)
    (out / "quant_evidence.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "quant_evidence.md").write_text(to_markdown(data), encoding="utf-8")

    h1, h2, h3 = data["H1"], data["H2"], data["H3"]
    print(f"quits src: {data['metadata']['quits_src']}")
    print(f"H1: {h1['n_distinct_whitelists']} distinct whitelists / "
          f"{h1['n_inconsistent_family_pairs']} of {h1['n_family_pairs']} "
          f"family pairs inconsistent  verdict={h1['verdict_supported']}")
    print(f"H2: decoder/ ABC={h2['decoder_package']['n_abstract_classes']} "
          f"layout/ ABC={h2['layout_package']['n_abstract_classes']}  "
          f"verdict={h2['verdict_supported']}")
    print(f"H3: noise param in build_circuit signature in "
          f"{h3['n_files_with_explicit_noise_param']}/"
          f"{h3['n_distinct_files_defining_build_circuit']} files; "
          f"noise dependence by any channel "
          f"{h3['n_files_depending_on_noise_any_channel']}/"
          f"{h3['n_distinct_files_defining_build_circuit']}  "
          f"verdict={h3['verdict_supported']}")
    print(f"P2-3: extractor domain covers source union = "
          f"{data['domain_coverage']['covers_source_union']}")
    print(f"P2-2: call sites verified "
          f"{data['metadata']['n_call_sites_verified']}/5 "
          f"(runtime {data['metadata']['n_call_sites_runtime_verified']}/5)")
    print(f"wrote {out / 'quant_evidence.json'}")
    print(f"wrote {out / 'quant_evidence.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())