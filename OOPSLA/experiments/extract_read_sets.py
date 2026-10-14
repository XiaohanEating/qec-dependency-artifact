"""Automatic extraction of component read sets R(c) from the pinned QUITS tree.

PAPER_GAP_ANALYSIS **P0-3** / Gap 1.7 / Gap 1.8: the read sets in
``src/semantics.py`` used to be *hand-written*, so the "QUITS-faithful" claim
rested on the accuracy of that hand modelling.  This script removes the hand
modelling from the critical path: it derives the read sets per dimension by
**AST static analysis of the read-only pinned tree**

    third_party/quits-0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452/src/quits

and reports the **diff against the hand-declared** read sets in
``semantics._mk_components`` and against ``cone_table``'s dataflow assembly.

Method
------
1. **Component granularity** is *not* chosen here: it is the pre-registered
   boundary of the frozen measurement protocol (``gate_audit/protocol.md``):
   ``qldpc_code/*`` (Code, Extraction), ``layout`` (Architecture), ``noise``
   (Noise), ``decoder`` (Decoder), ``simulation`` + ``api`` (assembly).  The
   only refinement is splitting ``qldpc_code/*`` into
   ``qldpc_code/circuit_construction/`` (Extraction) and the family modules
   (Code), because that is where the strategy dispatch actually lives.

2. **Vocabulary**, two tiers, both derived from the AST:
   ``api``   -- module-level ``def`` / ``class`` / constant of a package;
   ``state`` -- class-level attributes and every ``self.X = ...`` store.
   Function-local names (arguments, temporaries) are excluded: they are
   implementation detail and collide across dimensions.
   A name published by **two or more** dimensions is *ambiguous* and is
   dropped from every vocabulary rather than guessed at.

3. **Anchors** -- the entry point(s) whose return value is the dimension's
   artifact (``build_circuit`` for Extraction, ``ErrorModel.__post_init__`` for
   Noise, ``get_codecap_pL`` / ``sliding_window_*_circuit_mem`` for Decoder,
   the ``Layout`` constructors and ``QldpcCode.get_layout`` for Architecture,
   the family constructors for Code).  Located by AST search, never by
   hard-coded line numbers.

4. **Read attribution** -- every identifier inside an anchor is resolved to one
   of three kinds, each recorded with ``file:line`` evidence:

   ``coordinate``  the *value* of a spec coordinate enters the artifact.
                   Two sub-cases, both mechanical:
                     (a) the identifier is a coordinate carrier (a parameter
                         that *is* the coordinate value: ``strategy``,
                         ``error_model``, ``decoder``, ``layout``), or a
                         strategy-name literal (``cardinal``, ``zxcoloration``,
                         ...); or
                     (b) the identifier is a **state** name of a dimension --
                         class attribute or ``self.X`` store.  Component state
                         is exactly what a spec coordinate determines, so
                         reading ``.supported_strategies`` (a state name of the
                         *Code* package) is a coordinate read of ``code``.
                         This is H1's mechanism, found automatically.
   ``artifact``    another component's *artifact object* enters the anchor
                   (the ``QldpcCode`` instance, the ``stim.Circuit``,
                   ``hz``/``hx``/``lz``/``lx``).  Under the general model of
                   PIVOT_NOTE 6.0 (``produce : Spec x predecessor artifacts ->
                   Artifact``) this is a DAG **edge**; folding it into R(c) is
                   the arity-1 special case, reported as ``reads_flat``.
   ``sub_api``     a *function* of another package is merely called.  Recorded
                   for audit; not a data dependency.

Outputs (written next to this file):
  - ``read_sets.json`` -- auto read sets + evidence + the auto-vs-manual diff
  - ``read_sets.md``   -- human-readable version of the same

Run:  python experiments/extract_read_sets.py
"""
from __future__ import annotations

import ast
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
REPO_ROOT = OOPSLA_ROOT.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import semantics  # noqa: E402  (E402: path shim above)
import outdir  # noqa: E402  (`--out` support; see src/outdir.py)
from quant_evidence import QUITS_COMMIT, find_quits_src, rel  # noqa: E402

COORDINATES = semantics.COORDINATES

# ---------------------------------------------------------------------------
# 1. component granularity (gate_audit/protocol.md, frozen)
# ---------------------------------------------------------------------------

CODE_MODULES = ("base.py", "bb.py", "bpc.py", "hgp.py", "lcs.py", "mitten.py",
                "qlp.py")

DIMENSION_FILES: dict[str, tuple[str, ...]] = {
    "code": tuple("qldpc_code/" + n for n in CODE_MODULES),
    "extractor": ("qldpc_code/circuit_construction",),
    "arch": ("layout",),
    "noise": ("noise",),
    "decoder": ("decoder",),
    # The assembly layer is not a spec dimension; it is where cross-component
    # call sites live (simulation.get_codecap_pL, api.get_cardinal_circuit).
    "assembly": ("simulation.py", "api.py", "circuit.py", "__init__.py"),
}

GRANULARITY_SOURCE = (
    "gate_audit/protocol.md (component granularity, frozen): "
    "qldpc_code/* (Code, Extraction) / layout (Architecture) / "
    "noise (Noise) / decoder (Decoder) / simulation+api (assembly). "
    "Refinement: qldpc_code/circuit_construction is the Extraction package, "
    "the remaining qldpc_code family modules are the Code package."
)

#: Identifiers shorter than this are treated as *non-API*: they are loop
#: counters / shift exponents in QUITS and collide across dimensions
#: (``m`` is both a BB length and ``AbstractToricLayout.m``).
MIN_IDENT_LEN = 3

#: A name published by this many dimensions or more is ambiguous and is
#: dropped from every vocabulary.
AMBIGUITY_THRESHOLD = 2


def files_for_entry(entry: str) -> list[Path]:
    root = find_quits_src()
    p = root / entry
    if p.is_dir():
        return sorted(q for q in p.rglob("*.py") if "__pycache__" not in q.parts)
    if p.is_file():
        return [p]
    raise FileNotFoundError(f"missing source entry: {p}")     # pragma: no cover


def files_for(dimension: str) -> list[Path]:
    out: list[Path] = []
    for entry in DIMENSION_FILES[dimension]:
        out.extend(files_for_entry(entry))
    return out


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _snake(name: str) -> str:
    """``ErrorModel`` -> ``error_model``; ``BP-OSD`` -> ``bp_osd``."""
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.replace("-", "_").lower()


# ---------------------------------------------------------------------------
# 2. vocabulary per dimension (two tiers: api / state)
# ---------------------------------------------------------------------------

def _self_stores(class_node: ast.ClassDef) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(class_node):
        if (isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Attribute)
                        and isinstance(t.value, ast.Name)
                        and t.value.id == "self" for t in n.targets)):
            out.update(t.attr for t in n.targets
                       if isinstance(t, ast.Attribute)
                       and isinstance(t.value, ast.Name)
                       and t.value.id == "self")
        if (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Attribute)
                and isinstance(n.target.value, ast.Name)
                and n.target.value.id == "self"):
            out.add(n.target.attr)
    return out


def _class_level_names(class_node: ast.ClassDef) -> set[str]:
    out: set[str] = set()
    for stmt in class_node.body:
        if isinstance(stmt, ast.Assign):
            out.update(t.id for t in stmt.targets if isinstance(t, ast.Name))
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            out.add(stmt.target.id)
    return out


def package_vocabulary(dimension: str) -> dict:
    """Rule 2: the names the dimension's package(s) publish, split into tiers."""
    api: set[str] = set()
    state: set[str] = set()
    strategy_names: set[str] = set()
    n_files = 0

    for f in files_for(dimension):
        n_files += 1
        tree = parse(f)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                api.add(node.name)
            elif isinstance(node, ast.Assign):
                api.update(t.id for t in node.targets if isinstance(t, ast.Name))
            elif (isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name)):
                api.add(node.target.id)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                state |= _class_level_names(node) | _self_stores(node)
            # builder classes publish their registry key as `name = "..."`
            if (isinstance(node, ast.Assign)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                    and any(isinstance(t, ast.Name) and t.id == "name"
                            for t in node.targets)):
                strategy_names.add(node.value.value)

    return {
        "dimension": dimension,
        "n_files": n_files,
        "files": [rel(f, find_quits_src()) for f in files_for(dimension)],
        "api": sorted(api),
        "state": sorted(state),
        "strategy_names": sorted(strategy_names),
    }


def build_vocabularies() -> tuple[dict[str, dict], dict[str, list[str]]]:
    vocabs = {d: package_vocabulary(d) for d in DIMENSION_FILES}
    spec = [d for d in vocabs if d != "assembly"]

    owner_count: Counter[str] = Counter()
    for d in spec:
        for nm in set(vocabs[d]["api"]) | set(vocabs[d]["state"]):
            if len(nm) >= MIN_IDENT_LEN:
                owner_count[nm] += 1
    ambiguous = sorted(nm for nm, c in owner_count.items()
                       if c >= AMBIGUITY_THRESHOLD)
    # record the owners *before* filtering, so the report shows why each name
    # was dropped instead of an empty list.
    owners = {nm: sorted(d for d in spec
                         if nm in vocabs[d]["api"] or nm in vocabs[d]["state"])
              for nm in ambiguous}
    amb = set(ambiguous)
    for v in vocabs.values():
        v["api"] = sorted(nm for nm in v["api"]
                          if nm not in amb and len(nm) >= MIN_IDENT_LEN)
        v["state"] = sorted(nm for nm in v["state"]
                            if nm not in amb and len(nm) >= MIN_IDENT_LEN)
        v["n_names"] = len(v["api"]) + len(v["state"])
    return vocabs, owners


# ---------------------------------------------------------------------------
# 3. anchors (located by AST search)
# ---------------------------------------------------------------------------

#: ``(dimension, directory-or-file, function name)`` -- searched, never pinned.
#: A directory entry means "every ``*.py`` under it".
ANCHOR_SPECS: list[tuple[str, str, str]] = [
    # Extraction: the strategy-dispatch entry point that produces the circuit.
    ("extractor", "qldpc_code", "build_circuit"),
    # Code: family constructors + the shared parity-check entry points.
    ("code", "qldpc_code", "__init__"),
    ("code", "qldpc_code/base.py", "set_parity_checks"),
    ("code", "qldpc_code/base.py", "verify_css_logicals"),
    # Architecture: get_layout's default + every concrete layout entry point.
    ("arch", "qldpc_code/base.py", "get_layout"),
    ("arch", "layout", "__init__"),
    ("arch", "layout/transversal.py", "_build_mapping"),
    ("arch", "layout/toric.py", "__new__"),
    ("arch", "layout/base.py", "node_positions"),
    # Noise: the dataclass that *is* the noise coordinate's artifact.
    ("noise", "noise/error_model.py", "__post_init__"),
    ("noise", "noise/error_model.py", "_validate_single_or_pauli1"),
    ("noise", "noise/error_model.py", "_validate_single_or_pauli2"),
    # Decoder: the circuit-level decoding entries.
    ("decoder", "decoder", "get_codecap_pL"),
    ("decoder", "decoder/bposd.py", "sliding_window_bposd_circuit_mem"),
    ("decoder", "decoder/bplsd.py", "sliding_window_bplsd_circuit_mem"),
    ("decoder", "decoder/base.py", "spacetime"),
]

#: Anchors whose *file* lives outside the dimension's own package because the
#: dimension is invoked through the assembly layer (``simulation.get_codecap_pL``
#: is the decoder call site cited in PIVOT_NOTE §4).
CROSS_PACKAGE_ANCHORS = {("decoder", "simulation.py")}

#: Identifiers that denote *another component's artifact object* rather than a
#: spec coordinate.  Each entry names the producing component; the justification
#: is the producing anchor recorded in the evidence (``build_circuit`` returns a
#: ``stim.Circuit``; ``QldpcCode.__init__`` installs ``hz``/``hx``/``lz``/``lx``;
#: ``decoder/base.py:134 spacetime(circuit, ...)`` consumes the circuit).
_ARTIFACT_ALIASES = {
    "code": "code",
    "circuit": "extractor",
    "circ": "extractor",
    "dem": "extractor",
    "model": "extractor",
    "hz": "code", "hx": "code", "lz": "code", "lx": "code",
    "data_qubits": "code", "zcheck_qubits": "code", "xcheck_qubits": "code",
    "check_qubits": "code", "all_qubits": "code",
}

#: Identifiers that carry the *value* of a spec coordinate.  The only
#: hand-written entries in the extractor, each justified by the source site the
#: evidence records: ``strategy`` is the registry key of
#: ``circuit_construction/_BUILDERS``; ``error_model`` is the parameter that
#: carries the ``noise`` coordinate into ``build_circuit``; ``decoder`` is the
#: decoder implementation chosen by the caller of ``get_codecap_pL``.
_COORDINATE_NAMES = {
    "strategy": "extractor",
    "error_model": "noise",
    "decoder": "decoder",
}

#: Identifiers QUITS uses as *generic implementation* names rather than as
#: component API; emitting a read from these would fabricate a dependency.
#: Recorded in ``read_sets.json`` so the exclusion is auditable.
_GENERIC_IDENTIFIERS = {
    "name": "generic 'subject' parameter (e.g. noise/error_model.py:45 error "
            "message); the Extraction registry key is captured through the "
            "strategy-name channel, not through this spelling",
}

_KIND_COORDINATE = "coordinate"
_KIND_ARTIFACT = "artifact"
_KIND_SUB_API = "sub_api"
_KINDS = (_KIND_COORDINATE, _KIND_ARTIFACT, _KIND_SUB_API)
#: kind -> key used in the per-anchor result dict
_RESULT_KEY = {_KIND_COORDINATE: "coordinates", _KIND_ARTIFACT: "artifacts",
               _KIND_SUB_API: "sub_api"}


def _is_dir_entry(entry: str) -> bool:
    """``layout`` is a package, ``noise/error_model.py`` is a module."""
    return "/" not in entry


def _owner_of_file(relpath: str) -> str | None:
    for d, entries in DIMENSION_FILES.items():
        for e in entries:
            if _is_dir_entry(e):
                if relpath.startswith(e + "/") or relpath == e:
                    return d
            elif relpath == e:
                return d
    return None


def _owner_acceptable(dimension: str, relpath: str, owner: str | None) -> bool:
    """``build_circuit`` overrides live in Code files; ``get_codecap_pL`` lives
    in the assembly layer.  Both are legitimate anchors of a *different*
    dimension than the file they are written in."""
    if owner == dimension:
        return True
    if dimension == "extractor" and owner == "code":
        return True
    return (dimension, relpath) in CROSS_PACKAGE_ANCHORS


def find_anchors() -> list[dict]:
    root = find_quits_src()
    out: list[dict] = []
    for dimension, target, func_name in ANCHOR_SPECS:
        base = root / target
        candidates = ([base] if base.is_file()
                      else sorted(p for p in base.rglob("*.py")
                                  if "__pycache__" not in p.parts))
        if base.is_file() is False and base.is_dir() is False:
            raise FileNotFoundError(f"anchor target: {base}")  # pragma: no cover
        seen = set(candidates)
        extra = sorted(e for (d, e) in CROSS_PACKAGE_ANCHORS if d == dimension)
        for entry in extra:
            candidates.extend(p for p in files_for_entry(entry) if p not in seen)
            seen.update(files_for_entry(entry))
        for f in sorted(candidates):
            r = rel(f, root)
            owner = _owner_of_file(r)
            if not _owner_acceptable(dimension, r, owner):
                continue
            for cls, node in _methods(parse(f)):
                if node.name != func_name:
                    continue
                out.append({
                    "dimension": dimension, "file": r, "line": node.lineno,
                    "qualname": (f"{cls.name}.{node.name}" if cls else node.name),
                    "node": node,
                    # `self` inside a method is an instance of the *enclosing*
                    # class, i.e. the artifact of whichever component owns the
                    # class's file.  This is how `build_circuit` (a method on
                    # QldpcCode) is found to consume the code artifact.
                    "self_owner": owner,
                })
    seen, uniq = set(), []
    for a in sorted(out, key=lambda x: (x["dimension"], x["file"], x["line"])):
        key = (a["dimension"], a["file"], a["line"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(a)
    return uniq


def _methods(tree: ast.Module):
    """Yield ``(enclosing ClassDef or None, FunctionDef)`` pairs, in source order."""
    stack: list[ast.ClassDef | None] = [None]
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            yield from ((node, m) for m in _direct_methods(node))
    for node in tree.body:                       # module-level functions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield None, node


def _direct_methods(cls: ast.ClassDef):
    for stmt in cls.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield stmt


# ---------------------------------------------------------------------------
# 4. read attribution
# ---------------------------------------------------------------------------

class Attributor:
    """Resolves a bare identifier to ``(kind, dimension)``."""

    def __init__(self, vocabs: dict[str, dict]):
        self.state_owner: dict[str, str] = {}
        self.api_owner: dict[str, str] = {}
        self.state_folded: dict[str, str] = {}
        self.api_folded: dict[str, str] = {}
        for d, v in vocabs.items():
            if d == "assembly":
                continue
            for nm in v["state"]:
                self.state_owner.setdefault(nm, d)
                self.state_folded.setdefault(_snake(nm), nm)
            for nm in v["api"]:
                self.api_owner.setdefault(nm, d)
                self.api_folded.setdefault(_snake(nm), nm)
        self.strategy_names: set[str] = set()
        for d in ("code", "extractor"):
            self.strategy_names |= set(vocabs[d]["strategy_names"])

    def classify(self, ident: str) -> tuple[str, str] | None:
        if ident in _GENERIC_IDENTIFIERS:
            return None
        if ident in _ARTIFACT_ALIASES:
            return (_KIND_ARTIFACT, _ARTIFACT_ALIASES[ident])
        if ident in _COORDINATE_NAMES:
            return (_KIND_COORDINATE, _COORDINATE_NAMES[ident])
        if ident in self.strategy_names:
            return (_KIND_COORDINATE, "extractor")
        folded = _snake(ident)
        if ident in self.state_owner or folded in self.state_folded:
            return (_KIND_COORDINATE, self.state_owner.get(ident)
                    or self.state_owner[self.state_folded[folded]])
        if ident in self.api_owner or folded in self.api_folded:
            return (_KIND_SUB_API, self.api_owner.get(ident)
                    or self.api_owner[self.api_folded[folded]])
        return None


def _callee_name(node: ast.Call) -> str | None:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _param_names(node) -> list[str]:
    a = node.args
    names = ([p.arg for p in a.posonlyargs] + [p.arg for p in a.args]
             + [p.arg for p in a.kwonlyargs])
    if a.vararg:
        names.append("*" + a.vararg.arg)
    if a.kwarg:
        names.append("**" + a.kwarg.arg)
    return names


def attribute_reads(anchor: dict, attrib: Attributor) -> dict:
    """Read sets exhibited by one anchor, with ``file:line`` evidence."""
    node = anchor["node"]
    self_owner = anchor.get("self_owner")
    reads: dict[str, set[str]] = {k: set() for k in _KINDS}
    evidence: dict[str, set[str]] = defaultdict(set)
    site = f"{anchor['file']}:{anchor['line']}"

    def note(kind: str, coord: str, channel: str, what: str) -> None:
        if coord not in COORDINATES:
            return
        reads[kind].add(coord)
        evidence[coord].add(f"{site} [{channel}/{kind}] {what}")

    def note_ident(ident: str, channel: str, what: str) -> None:
        if ident == "self":
            # `self` is an instance of the enclosing class, so it carries that
            # class's artifact: `build_circuit` is a method on QldpcCode and
            # therefore reads the code artifact.
            if self_owner:
                note(_KIND_ARTIFACT, self_owner, "receiver",
                     "`self` is an instance of the enclosing class")
            return
        got = attrib.classify(ident)
        if got:
            note(got[0], got[1], channel, what)

    for p in _param_names(node):
        note_ident(p.lstrip("*"), "declaration", f"parameter `{p}`")

    for n in ast.walk(node):
        if isinstance(n, ast.Attribute):
            note_ident(n.attr, "attribute", f"reads `.{n.attr}`")
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            note_ident(n.id, "name", f"reads `{n.id}`")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            note_ident(n.value, "string", f"string literal `{n.value}`")
        elif isinstance(n, ast.keyword) and n.arg:
            note_ident(n.arg, "string", f"keyword `{n.arg}=`")
        elif isinstance(n, ast.Call):
            callee = _callee_name(n)
            if callee is None:
                continue
            note_ident(callee, "callee", f"calls `{callee}(...)`")
            for arg in list(n.args) + [k.value for k in n.keywords if k.arg]:
                for sub in ast.walk(arg):
                    if (isinstance(sub, ast.Name)
                            and isinstance(sub.ctx, ast.Load)):
                        note_ident(sub.id, "argument",
                                   f"`{sub.id}` flows into `{callee}(...)`")

    return {
        "coordinates": sorted(reads[_KIND_COORDINATE]),
        "artifacts": sorted(reads[_KIND_ARTIFACT]),
        "sub_api": sorted(reads[_KIND_SUB_API]),
        "reads": sorted(reads[_KIND_COORDINATE]),
        "reads_flat": sorted(reads[_KIND_COORDINATE] | reads[_KIND_ARTIFACT]),
        "evidence": {k: sorted(v) for k, v in sorted(evidence.items())},
    }


def _obligation_clues(anchor: dict) -> list[dict]:
    """Obligation clues: the checks a substituter must satisfy at this anchor."""
    out: list[dict] = []
    for n in ast.walk(anchor["node"]):
        if isinstance(n, ast.Raise) and n.exc is not None:
            exc = None
            if isinstance(n.exc, ast.Call) and isinstance(n.exc.func, ast.Name):
                exc = n.exc.func.id
            elif isinstance(n.exc, ast.Name):
                exc = n.exc.id
            if exc:
                out.append({"kind": "raise", "what": exc,
                            "site": f"{anchor['file']}:{n.lineno}"})
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "isinstance" and len(n.args) >= 2):
            out.append({"kind": "isinstance", "what": ast.unparse(n.args[1]),
                        "site": f"{anchor['file']}:{n.lineno}"})
    return out


# ---------------------------------------------------------------------------
# 5. assemble
# ---------------------------------------------------------------------------

def _blank_slot() -> dict:
    return {_KIND_COORDINATE: set(), _KIND_ARTIFACT: set(), _KIND_SUB_API: set(),
            "evidence": defaultdict(set), "anchors": [], "obligations": set()}


def extract_read_sets() -> dict:
    vocabs, ambiguous = build_vocabularies()
    attrib = Attributor(vocabs)
    anchors = find_anchors()

    per_dim: dict[str, dict] = {}
    for a in anchors:
        d = a["dimension"]
        res = attribute_reads(a, attrib)
        slot = per_dim.setdefault(d, _blank_slot())
        for k in _KINDS:
            slot[k].update(res[_RESULT_KEY[k]])
        for k, v in res["evidence"].items():
            slot["evidence"][k].update(v)
        slot["anchors"].append({"file": a["file"], "line": a["line"],
                                "qualname": a["qualname"],
                                "self_owner": a.get("self_owner"),
                                "coordinates_here": res["coordinates"],
                                "artifacts_here": res["artifacts"]})
        slot["obligations"].update(
            (o["kind"], o["what"], o["site"]) for o in _obligation_clues(a))

    read_sets: dict[str, dict] = {}
    for d in COORDINATES:
        slot = per_dim.get(d) or _blank_slot()
        read_sets[d] = {
            # R(c) proper: the spec-coordinate read set.
            "reads": sorted(slot[_KIND_COORDINATE]),
            # Cross-component artifact objects: DAG edges under the general model.
            "artifact_reads": sorted(slot[_KIND_ARTIFACT]),
            # R(c) + artifacts: the arity-1 flattening.
            "reads_flat": sorted(slot[_KIND_COORDINATE] | slot[_KIND_ARTIFACT]),
            "sub_api": sorted(slot[_KIND_SUB_API]),
            "anchors": sorted(slot["anchors"], key=lambda x: (x["file"], x["line"])),
            "evidence": {k: sorted(v) for k, v in sorted(slot["evidence"].items())},
            "obligation_clues": [{"kind": k, "what": w, "site": s}
                                 for k, w, s in sorted(slot["obligations"])],
        }

    return {
        "metadata": {
            "description": "Read sets R(c) auto-extracted from the pinned QUITS tree",
            "date": date.today().isoformat(),
            "quits_commit": QUITS_COMMIT,
            "quits_src": str(find_quits_src()),
            "method": "AST static analysis; component granularity from "
                      "gate_audit/protocol.md; anchors located by AST search; "
                      "coordinate / artifact / sub_api attribution",
            "granularity_source": GRANULARITY_SOURCE,
            "coordinates": list(COORDINATES),
            "kinds": list(_KINDS),
            "min_ident_len": MIN_IDENT_LEN,
            "ambiguity_threshold": AMBIGUITY_THRESHOLD,
            "generic_identifiers_excluded": dict(_GENERIC_IDENTIFIERS),
            "artifact_aliases": dict(_ARTIFACT_ALIASES),
            "coordinate_carriers": dict(_COORDINATE_NAMES),
        },
        "vocabularies": {
            d: {"n_files": v["n_files"], "n_names": v["n_names"],
                "names": sorted(set(v["api"]) | set(v["state"])),
                "api": v["api"], "state": v["state"],
                "strategy_names": v["strategy_names"]}
            for d, v in vocabs.items()},
        "ambiguous_names_dropped": ambiguous,
        "read_sets": read_sets,
    }


# ---------------------------------------------------------------------------
# 6. diff against the hand-declared model
# ---------------------------------------------------------------------------

def hand_declared_read_sets() -> dict[str, tuple[str, ...]]:
    """The read sets exactly as hand-written in ``semantics._mk_components``."""
    return {n: tuple(c.reads) for n, c in semantics._mk_components().items()
            if n != "extractor_quits"}


def dataflow_read_sets() -> dict[str, tuple[str, ...]]:
    from cone_table import make_quits_dataflow_assembly
    return {n: tuple(c.reads)
            for n, c in make_quits_dataflow_assembly().nodes.items()
            if n != "experiment"}


def diff(auto: set[str], manual: set[str]) -> dict:
    missing = sorted(manual - auto)     # hand model declares, source does not read
    extra = sorted(auto - manual)       # source reads, hand model omits
    if not missing and not extra:
        verdict = "agreement"
    elif extra and not missing:
        verdict = "manual_under_approximates"
    elif missing and not extra:
        verdict = "manual_over_approximates"
    else:
        verdict = "partial_disagreement"
    return {"auto": sorted(auto), "manual": sorted(manual),
            "in_manual_not_auto": missing, "in_auto_not_manual": extra,
            "verdict": verdict, "agrees": not missing and not extra}


def build_diff(extraction: dict) -> dict:
    hand = hand_declared_read_sets()
    flow = dataflow_read_sets()
    rows = {}
    for d in COORDINATES:
        rs = extraction["read_sets"][d]
        rows[d] = {
            "vs_hand_declared": diff(set(rs["reads"]), set(hand.get(d, ()))),
            "vs_hand_declared_flat": diff(set(rs["reads_flat"]),
                                          set(hand.get(d, ()))),
            "vs_dataflow_assembly": diff(set(rs["reads"]), set(flow.get(d, ()))),
            "vs_dataflow_assembly_flat": diff(set(rs["reads_flat"]),
                                              set(flow.get(d, ()))),
            # 决策 1：自动提取器是**交叉验证**，动态实测是 ground truth。这里
            # 明确记录"本提取器的结果直接成为发布基线"，避免读者以为这三个
            # 模型里有一个是"官方版本"。
            "is_published_baseline": d in semantics.ASSEMBLY_MODEL_SOURCES[
                semantics.BASELINE_ASSEMBLY]["_baseline_dimensions"],
        }
    return {
        "rows": rows,
        "hand_declared": {k: list(v) for k, v in hand.items()},
        "dataflow_assembly": {k: list(v) for k, v in flow.items()},
        "all_hand_agree": all(rows[d]["vs_hand_declared"]["agrees"]
                              for d in COORDINATES),
        "n_hand_disagreements": sum(1 for d in COORDINATES
                                    if not rows[d]["vs_hand_declared"]["agrees"]),
        "all_hand_agree_flat": all(rows[d]["vs_hand_declared_flat"]["agrees"]
                                   for d in COORDINATES),
        "n_hand_disagreements_flat": sum(
            1 for d in COORDINATES
            if not rows[d]["vs_hand_declared_flat"]["agrees"]),
        "n_dataflow_disagreements": sum(
            1 for d in COORDINATES
            if not rows[d]["vs_dataflow_assembly"]["agrees"]),
    }


def collect() -> dict:
    extraction = extract_read_sets()
    data = dict(extraction)
    data["diff"] = build_diff(extraction)
    data["role"] = {
        # 决策 1（2026-10-09）：自动提取器是**交叉验证**，不是 ground truth。
        "status": "cross-validation",
        "ground_truth": "experiments/dynamic_impact.py (runs QUITS and measures "
                        "the impact surface of five real substitutions)",
        "claim": "the read sets reported here are correct with respect to the "
                 "pinned QUITS source; the dynamic experiment independently "
                 "confirms the dependency structure they imply",
        "published_baseline_assembly": semantics.BASELINE_ASSEMBLY,
        "assembly_model_sources": semantics.assembly_model_sources(
            ("source_faithful", "quits_dataflow")),
        "scope_limits": "the evidence channels are "
                        "declaration/attribute/name/string/keyword/callee/argument; "
                        "ambiguous names are dropped rather than guessed, so the "
                        "result is a conservative *under*-approximation "
                        "(PIVOT_NOTE section 8.6 item 8)",
    }
    data["summary"] = {
        "auto_read_sets": {d: extraction["read_sets"][d]["reads"]
                           for d in COORDINATES},
        "auto_artifact_reads": {d: extraction["read_sets"][d]["artifact_reads"]
                                for d in COORDINATES},
        "auto_read_sets_flat": {d: extraction["read_sets"][d]["reads_flat"]
                                for d in COORDINATES},
        "n_ambiguous_names_dropped": len(extraction["ambiguous_names_dropped"]),
        "n_anchors": sum(len(extraction["read_sets"][d]["anchors"])
                         for d in COORDINATES),
        "hand_declared_all_agree": data["diff"]["all_hand_agree"],
        "n_hand_disagreements": data["diff"]["n_hand_disagreements"],
        "hand_declared_all_agree_flat": data["diff"]["all_hand_agree_flat"],
        "n_hand_disagreements_flat": data["diff"]["n_hand_disagreements_flat"],
        "n_dataflow_disagreements": data["diff"]["n_dataflow_disagreements"],
    }
    return data


# ---------------------------------------------------------------------------
# 7. markdown
# ---------------------------------------------------------------------------

def _channels(sites: list[str]) -> list[str]:
    out = set()
    for s in sites:
        m = re.search(r"\[([a-z]+)/", s)
        if m:
            out.add(m.group(1))
    return sorted(out)


def to_markdown(data: dict) -> str:
    m, rs, df = data["metadata"], data["read_sets"], data["diff"]
    role = data.get("role", {})
    L = ["# Read Sets R(c) - auto-extracted from the pinned QUITS tree", "",
         f"Generated: {m['date']}  ",
         f"QUITS commit: `{m['quits_commit']}`  ",
         f"Source: `{m['quits_src']}`  ",
         f"Method: {m['method']}", "",
         "> The component granularity is **not** chosen by this script: it is "
         "the pre-registered boundary of `gate_audit/protocol.md`.", "",
         "`R(c)` is the **spec-coordinate** read set (what "
         "`semantics.Component.reads` denotes).  `artifact_reads` are references "
         "to another component's *artifact object* (the `QldpcCode` instance, the "
         "`stim.Circuit`, `hz`/`lx`): under the general model of PIVOT_NOTE 6.0 "
         "(`produce : Spec x predecessor artifacts -> Artifact`) those are DAG "
         "**edges**, not coordinate reads.  `reads_flat` is the arity-1 "
         "flattening of the two.", ""]
    if role:
        src = role["assembly_model_sources"]
        base = src[role["published_baseline_assembly"]]
        L += ["## 0. Role: cross-validation, not ground truth", "",
              f"This extractor's status is **{role['status']}**. The ground truth "
              f"is `{role['ground_truth']}`, which runs QUITS and *measures* the "
              "impact surface of five real substitutions.", "",
              f"What it claims: {role['claim']}", "",
              f"Since decision 2 (2026-10-09) these read sets **are** the "
              f"published baseline (`{role['published_baseline_assembly']}`):",
              f"- read sets: {base['read_sets']}",
              f"- DAG edges: {base['edges']}", "",
              f"Hand-modelled counterpart `{src['quits_dataflow']['builder']}`: "
              f"read sets = {src['quits_dataflow']['read_sets']}; "
              f"edges = {src['quits_dataflow']['edges']}", "",
              f"Scope limits: {role['scope_limits']}", ""]
    L += ["## 1. Auto-extracted read sets", "",
         "| dimension | R(c) (coordinates) | artifact_reads | reads_flat | "
         "sub_api | anchors |",
         "|---|---|---|---|---|---:|"]
    for d in COORDINATES:
        L.append(f"| `{d}` | `{', '.join(rs[d]['reads']) or '-'}` "
                 f"| `{', '.join(rs[d]['artifact_reads']) or '-'}` "
                 f"| `{', '.join(rs[d]['reads_flat']) or '-'}` "
                 f"| `{', '.join(rs[d]['sub_api']) or '-'}` "
                 f"| {len(rs[d]['anchors'])} |")

    L += ["", "### Per-dimension detail", ""]
    for d in COORDINATES:
        L += [f"**`{d}`** - anchors and what each one reads:", "",
              "| anchor | R(c) here | artifact reads here |", "|---|---|---|"]
        for a in rs[d]["anchors"]:
            L.append(f"| `{a['file']}:{a['line']}` `{a['qualname']}` "
                     f"| `{', '.join(a['coordinates_here']) or '-'}` "
                     f"| `{', '.join(a['artifacts_here']) or '-'}` |")
        L += ["", "<details><summary>evidence</summary>", ""]
        for coord, sites in rs[d]["evidence"].items():
            L.append(f"- `{coord}`:")
            for s in sites[:18]:
                L.append(f"    - `{s}`")
            if len(sites) > 18:
                L.append(f"    - ... {len(sites) - 18} more")
        L += ["", "</details>", ""]
        if rs[d]["obligation_clues"]:
            L += ["Obligation clues (candidate `contract`s) at these anchors:",
                  ""]
            for o in rs[d]["obligation_clues"]:
                L.append(f"- `{o['kind']}` `{o['what']}` - `{o['site']}`")
            L.append("")

    L += ["## 2. Diff against the hand-declared model", "",
          "`hand` = `semantics._mk_components()`; `dataflow` = "
          "`cone_table.make_quits_dataflow_assembly()` (the assembly used for the "
          "H3 dataflow experiment).", "",
          "### 2a. R(c) proper (spec coordinates only)", "",
          "| dimension | auto | hand | verdict | in auto not in hand |",
          "|---|---|---|---|---|"]
    for d in COORDINATES:
        r = df["rows"][d]["vs_hand_declared"]
        L.append(f"| `{d}` | `{', '.join(r['auto']) or '-'}` "
                 f"| `{', '.join(r['manual']) or '-'}` | **{r['verdict']}** "
                 f"| `{', '.join(r['in_auto_not_manual']) or '-'}` |")
    L += ["", "### 2b. Flattened (coordinates + artifact objects)", "",
          "| dimension | auto | hand | verdict | in auto not in hand |",
          "|---|---|---|---|---|"]
    for d in COORDINATES:
        r = df["rows"][d]["vs_hand_declared_flat"]
        L.append(f"| `{d}` | `{', '.join(r['auto']) or '-'}` "
                 f"| `{', '.join(r['manual']) or '-'}` | **{r['verdict']}** "
                 f"| `{', '.join(r['in_auto_not_manual']) or '-'}` |")
    L += ["", "### 2c. vs the dataflow assembly (R(c) proper)", "",
          "| dimension | auto | dataflow | verdict | in auto not in dataflow |",
          "|---|---|---|---|---|"]
    for d in COORDINATES:
        r = df["rows"][d]["vs_dataflow_assembly"]
        L.append(f"| `{d}` | `{', '.join(r['auto']) or '-'}` "
                 f"| `{', '.join(r['manual']) or '-'}` | **{r['verdict']}** "
                 f"| `{', '.join(r['in_auto_not_manual']) or '-'}` |")

    L += ["", "## 3. Vocabulary sanity check", "",
          f"A name published by {AMBIGUITY_THRESHOLD} or more dimensions is "
          f"ambiguous and is dropped from every vocabulary "
          f"({len(data['ambiguous_names_dropped'])} names):",
          "",
          ", ".join(f"`{n}`" for n in sorted(data["ambiguous_names_dropped"])[:40])
          or "-", "",
          f"Identifiers shorter than {MIN_IDENT_LEN} characters are treated as "
          "non-API (loop counters / shift exponents).", "",
          "Generic identifiers excluded from attribution: "
          + ", ".join(f"`{n}`" for n in sorted(_GENERIC_IDENTIFIERS)) + ".", ""]
    L += ["| dimension | package entries | files | published names | api | state |",
          "|---|---:|---:|---:|---:|---:|"]
    for d, v in data["vocabularies"].items():
        L.append(f"| `{d}` | {len(DIMENSION_FILES[d])} | {v['n_files']} "
                 f"| {v['n_names']} | {len(v['api'])} | {len(v['state'])} |")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    data = collect()
    out = outdir.resolve_out(argv, HERE)
    (out / "read_sets.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "read_sets.md").write_text(to_markdown(data), encoding="utf-8")
    print(f"quits src: {data['metadata']['quits_src']}")
    for d in COORDINATES:
        r = data["diff"]["rows"][d]
        print(f"  {d:10s} R(c)={r['vs_hand_declared']['auto']} "
              f"artifacts={data['summary']['auto_artifact_reads'][d]} "
              f"hand={r['vs_hand_declared']['manual']} "
              f"verdict={r['vs_hand_declared']['verdict']}")
    print("hand-declared disagreements (R(c)): "
          f"{data['summary']['n_hand_disagreements']}/{len(COORDINATES)}")
    print("hand-declared disagreements (flattened): "
          f"{data['summary']['n_hand_disagreements_flat']}/{len(COORDINATES)}")
    print("dataflow-assembly disagreements: "
          f"{data['summary']['n_dataflow_disagreements']}/{len(COORDINATES)}")
    print(f"wrote {out / 'read_sets.json'}")
    print(f"wrote {out / 'read_sets.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())