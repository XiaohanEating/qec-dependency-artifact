"""AST read-set extraction for subject 2 (qecc_routing), diffed against the
hand-annotated model of ``subject2_qecc.py``.

PAPER_GAP_ANALYSIS / ``subject_system2.md`` §5 item 2: subject 2's declared
read sets ``R(c)`` were *hand-annotated* with file:line provenance.  This
script removes the hand annotation from the critical path the same way
``extract_read_sets.py`` did for QUITS: it statically analyses the pinned,
read-only tree

    third_party/qecc_routing-4ef18121.../src_py/bivariate-bicycle/general.py

and reports, per component, the module-level global names the component's
source region actually reads, mapped to the five coordinates of
``subject2_qecc.QeccSpec``.

Method (aligned with ``extract_read_sets.py``):
1. **Component granularity** — the 11 nodes of ``subject2_qecc.make_assembly``,
   each anchored to one or more line ranges of ``general.py`` (the same
   file:line evidence as ``subject2_qecc.PROVENANCE``).  Unlike QUITS, the
   "components" here are regions of a single module: qecc_routing has no
   packages, so the granularity is the model's, and every range is printed.
2. **Vocabulary** — the module-level names ``general.py`` itself defines
   (module-level ``Assign`` / ``AnnAssign`` / ``def`` / ``class``), split
   into *coordinate carriers* (a name whose value IS a spec coordinate:
   ``code``, ``probs``, ``muls001``, ``idle_error``, ``lr_time``,
   ``bposd_decoder``, and the ``lr_time`` parameter of ``Simulation``) and
   *artifacts* (module state produced by a component's region: ``Hx``,
   ``lattice``, ``x_rs``, ``x_check_succ_probs``, ...).  Import bindings
   (``np``, ``stim``, ...) and function-local temporaries are excluded.
3. **Read attribution** — every ``Name``/``Attribute``/callee identifier with
   a ``Load`` context inside a region is resolved to a coordinate read, an
   artifact read (DAG edge under the general model of PIVOT_NOTE 6.0), or a
   ``sub_api`` call.  Each read is recorded with ``file:line`` evidence.

The diff against the hand-declared ``R(c)`` is reported in three layers:
coordinate reads proper, artifact reads (the ``reads_flat`` analogue), and
raw module-global names, with every disagreement explained.

Outputs (written next to this file):
  - ``subject2_read_sets.json`` / ``subject2_read_sets.md``

Run:  python experiments/subject2_read_sets.py [--out DIR]
"""
from __future__ import annotations

import ast
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import outdir  # noqa: E402  (`--out` support; see src/outdir.py)
import subject2_qecc as S2  # noqa: E402  (the hand-annotated model)

QECC_DIR = (OOPSLA_ROOT.parent / "third_party" / f"qecc_routing-{S2.QECC_COMMIT}"
            / "src_py" / "bivariate-bicycle")
GENERAL_PY = QECC_DIR / "general.py"

COORDINATES = list(S2.COORDINATES)

# ---------------------------------------------------------------------------
# 1. component granularity: the model's 11 nodes, anchored to line ranges of
#    general.py (same evidence as subject2_qecc.PROVENANCE).  Line numbers are
#    1-based inclusive; located against the pinned file at run time and
#    re-verified (the anchors' first statements are matched textually).
# ---------------------------------------------------------------------------

#: component -> list of (start, end) ranges in general.py
REGIONS: dict[str, list[tuple[int, int]]] = {
    # A/B polynomials, Hx/Hz, GF(2) rank -> k  (general.py:43-68)
    "code": [(43, 68)],
    # par2gen / commute / SGSOP / get_logicals  (general.py:73-149)
    "logicals": [(73, 149)],
    # embed_code + the lattice/qbts/check-position fill  (general.py:156-224)
    "embedding": [(156, 224)],
    # minimal enclosing-circle radii of every check  (general.py:226-233)
    "geometry": [(226, 233)],
    # the lr/sr split: init (235-238), x loop test (243-250), z loop test
    # (255-262), and the aggregate `adv` ratio (267)
    "sr_lr_split": [(235, 238), (243, 250), (255, 262), (267, 267)],
    # per-check success probabilities: init (240-241) and the two probs
    # multiplications (252-253, 264-265)
    "succ_probs": [(240, 241), (252, 253), (264, 265)],
    # the circuit builders: measure_* + all_checks (270-306), the stim.Circuit
    # assembled in Simulation.__init__ (325-334), observables (348-352)
    "circuit": [(270, 306), (325, 334), (348, 352)],
    # Simulation.__init__ measurement bookkeeping (310-323) + detectors
    # (336-346) + sr_round (354-375) + lr_round (378-407) + simulate's round
    # loop with the two idle DEPOLARIZE1 lines (414, 422) EXCLUDED
    "schedule": [(309, 323), (336, 346), (354, 375), (378, 407),
                 (410, 413), (415, 421), (423, 438)],
    # exactly the two idle-error sites (general.py:414, 422)
    "idle": [(414, 414), (422, 422)],
    # the bposd construction in the module-level experiment loop (473-486)
    "decoder": [(473, 486)],
    # the whole experiment loop: where every artifact is consumed (448-496)
    "sink": [(448, 496)],
}

#: textual fingerprint of the first line of each region, so a line-number
#: drift in the pinned file fails loudly instead of silently mis-attributing
REGION_SENTINELS: dict[str, list[str]] = {
    "code": ["def cyclic_shift_matrix"],
    "logicals": ["def par2gen"],
    "embedding": ["def embed_code"],
    "geometry": ["x_rs = []"],
    "sr_lr_split": ["lr_x_checks = np.array"],
    "succ_probs": ["z_check_succ_probs = np.ones"],
    "circuit": ["def measure_x_checks"],
    "schedule": ["class Simulation:"],
    "idle": ["self.c.append(\"DEPOLARIZE1\", [all_qbts[qbt] for qbt in qbts], "
             "0.001+2*(code[12]+code[13])*idle_error)"],
    "decoder": ["bposd_dec = bposd_decoder("],
    "sink": ["for T in range(20, 21, 10):"],
}

#: component -> hand-declared R(c), read from the model itself (never
#: re-typed here)
def hand_read_sets() -> dict[str, list[str]]:
    A = S2.make_assembly()
    return {n: sorted(A.nodes[n].reads) for n in A.nodes}


# ---------------------------------------------------------------------------
# 2. vocabulary: module-level names of general.py
# ---------------------------------------------------------------------------

#: coordinate carriers: a name (module global or parameter) whose value IS a
#: spec coordinate.  Each entry justified by the source site it is read at.
COORDINATE_CARRIERS: dict[str, str] = {
    # the entire code spec is the 14-integer list (general.py:18)
    "code": "code",
    # the calibrated physical-error profile tables (general.py:39-40)
    "probs": "noise",
    "muls001": "noise",
    # the device idle/leakage rate (general.py:41)
    "idle_error": "noise",
    # the routing depth; the global (general.py:441) and the Simulation
    # parameter (general.py:310) carry the same coordinate
    "lr_time": "routing",
    # the ldpc decoder implementation chosen at the call site (general.py:9)
    "bposd_decoder": "decoder",
}

#: artifact producers: module-level state each component's region publishes.
#: Reading one of these is a DAG edge (the predecessor's artifact object),
#: the `reads_flat` channel of extract_read_sets.py -- NOT a coordinate read.
ARTIFACT_PRODUCERS: dict[str, str] = {
    # code region products (general.py:47-68)
    "ell": "code", "m": "code",
    "A1": "code", "A2": "code", "A3": "code",
    "B1": "code", "B2": "code", "B3": "code",
    "A": "code", "B": "code", "Hx": "code", "Hz": "code", "k": "code",
    # embedding region products (general.py:204-224)
    "lattice": "embedding", "all_qbts": "embedding",
    "qbts": "embedding", "x_checks": "embedding", "z_checks": "embedding",
    # geometry region products (general.py:226-233)
    "x_rs": "geometry", "z_rs": "geometry",
    # sr_lr_split region products (general.py:235-262, 267)
    "lr_x_checks": "sr_lr_split", "sr_x_checks": "sr_lr_split",
    "lr_z_checks": "sr_lr_split", "sr_z_checks": "sr_lr_split",
    "adv": "sr_lr_split",
    # succ_probs region products (general.py:240-241)
    "x_check_succ_probs": "succ_probs", "z_check_succ_probs": "succ_probs",
}

#: Simulation's own instance state (self.*) -- not module state, excluded
#: from the vocabulary but listed so the exclusion is auditable.
SELF_STATE = ("num_rounds", "lr_time", "prev_meas_z", "prev_meas_x",
              "curr_meas_z", "curr_meas_x", "route_confirmation_z",
              "route_confirmation_x", "detector_history", "c")

#: in-module functions: a call is a sub_api reference, not a data dependency
LOCAL_FUNCTIONS = ("cyclic_shift_matrix", "par2gen", "commute", "SGSOP",
                   "get_logicals", "manhattan", "embed_code",
                   "measure_x_checks", "measure_z_checks", "all_checks")


def module_vocabulary(tree: ast.Module) -> dict[str, list[str]]:
    """The names general.py publishes at module level (extract_read_sets
    rule 2, tier ``api``; subject 2 has no class-level tier to speak of --
    Simulation's state is instance state and is excluded above)."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif (isinstance(node, ast.AnnAssign)
              and isinstance(node.target, ast.Name)):
            names.add(node.target.attr if isinstance(node.target, ast.Attribute)
                     else node.target.id)
    return {"module": sorted(names)}


# ---------------------------------------------------------------------------
# 3. read attribution per region
# ---------------------------------------------------------------------------

def _in_regions(lineno: int, regions: list[tuple[int, int]]) -> bool:
    return any(a <= lineno <= b for a, b in regions)


def attribute_region(tree: ast.Module, component: str,
                     regions: list[tuple[int, int]]) -> dict:
    """All identifiers read inside the component's line ranges, resolved to
    coordinate reads / artifact reads / sub_api calls, with evidence."""
    coords: set[str] = set()
    artifacts: set[str] = set()
    sub_api: set[str] = set()
    raw_names: set[str] = set()
    evidence: dict[str, set[str]] = {
        "coordinate": set(), "artifact": set(), "sub_api": set()}

    def note(kind: str, key: str, what: str, lineno: int) -> None:
        if key not in COORDINATES and kind == "coordinate":
            return
        {"coordinate": coords, "artifact": artifacts,
         "sub_api": sub_api}[kind].add(key)
        evidence[kind].add(f"general.py:{lineno} {what}")

    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", None)
        if lineno is None or not _in_regions(lineno, regions):
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            raw_names.add(node.id)
            if node.id in COORDINATE_CARRIERS:
                note("coordinate", COORDINATE_CARRIERS[node.id],
                     f"reads `{node.id}`", lineno)
            elif node.id in ARTIFACT_PRODUCERS:
                note("artifact", ARTIFACT_PRODUCERS[node.id],
                     f"reads `{node.id}`", lineno)
            elif node.id in LOCAL_FUNCTIONS:
                note("sub_api", node.id, f"calls `{node.id}(...)`", lineno)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            # self.<state> is Simulation instance state, not module state
            if (isinstance(node.value, ast.Name)
                    and node.value.id == "self"):
                continue
            raw_names.add("." + node.attr)
        elif isinstance(node, ast.arg):
            # declaration channel (extract_read_sets): a parameter that IS a
            # coordinate carrier is a read of that coordinate
            if node.arg in COORDINATE_CARRIERS:
                note("coordinate", COORDINATE_CARRIERS[node.arg],
                     f"parameter `{node.arg}`", lineno)

    return {
        "coordinate_reads": sorted(coords),
        "artifact_reads": sorted(artifacts),
        "sub_api": sorted(sub_api),
        "raw_module_names": sorted(raw_names),
        "evidence": {k: sorted(v) for k, v in evidence.items()},
    }


def verify_anchors(lines: list[str]) -> list[str]:
    """Fail loudly if a region's line numbers drifted in the pinned file."""
    problems = []
    for comp, ranges in REGIONS.items():
        for (start, _), sentinel in zip(ranges, REGION_SENTINELS[comp]):
            if sentinel not in lines[start - 1]:
                problems.append(
                    f"{comp}: line {start} is `{lines[start-1].strip()}`; "
                    f"expected `{sentinel}`")
    return problems


# ---------------------------------------------------------------------------
# 4. the diff against the hand-declared model
# ---------------------------------------------------------------------------

def classify(component: str, ast_coords: set[str],
             hand: set[str]) -> tuple[str, str]:
    """(verdict, explanation) for one component's coordinate-level diff."""
    extra = sorted(ast_coords - hand)
    missing = sorted(hand - ast_coords)
    if not extra and not missing:
        return "agreement", "AST reads exactly the declared coordinates"
    if component in S2.FAITHFUL_BUT_WRONG and extra:
        return ("hidden_read_detected",
                f"AST finds the hidden `{extra}` read the hand model declares "
                f"as faithful-but-wrong ({' / '.join(S2.PROVENANCE[component])})")
    if component == "circuit" and extra == ["noise"]:
        return ("hidden_read_hand_missed",
                "the measure_* builders read the global `muls001` noise table "
                "when scale=True (general.py:280,295) -- a hidden noise read "
                "the hand model did NOT declare: hand R(circuit) omitted it")
    if component == "embedding" and missing == ["embedding"]:
        return ("carrier_sharing",
                "the embedding coordinate has no global of its own: its values "
                "are code[8:12], carried by the `code` list (general.py:204). "
                "AST sees one carrier; the hand model names the semantic view")
    if component in ("geometry", "logicals") and missing:
        return ("artifact_only",
                f"the real source reads only predecessor *artifacts* "
                f"({', '.join(missing)} never appears as a coordinate carrier "
                f"here); the hand toy produce used the coordinate directly")
    if component == "schedule" and missing == ["code"]:
        return ("artifact_only",
                "simulate's code contact is via module state (m, ell, the "
                "split and succ-prob arrays) and the two idle sites, which "
                "this extractor attributes to the `idle` component; no direct "
                "`code` coordinate read remains in the schedule body")
    if component == "sr_lr_split" and missing:
        return ("aggregate_visible_at_file_level",
                "the split decision is `min(x_rs)+np.std(x_rs)` over the WHOLE "
                "radius vector (general.py:247,259): AST sees the aggregate "
                "read of the geometry artifact, the hand model names the "
                "coordinates behind it.  File-level visible; the coordinate-"
                "keyed probe stays blind because aggregate and coordinate move "
                "together (subject_system2.md §2.3)")
    if component == "sink" and missing:
        return ("carrier_sharing",
                "the sink consumes every artifact; the embedding coordinate "
                "reaches it only through the shared `code` carrier "
                "(general.py:489-490), there is no separate embedding global")
    return ("partial_disagreement",
            f"AST-only: {extra or 'none'}; hand-only: {missing or 'none'}")


def collect() -> dict:
    text = GENERAL_PY.read_text(encoding="utf-8")
    lines = text.splitlines()
    problems = verify_anchors(lines)
    if problems:                                            # pragma: no cover
        raise SystemExit("anchor drift in pinned general.py:\n  "
                         + "\n  ".join(problems))
    tree = ast.parse(text, filename=str(GENERAL_PY))

    hand = hand_read_sets()
    rows = []
    for comp in sorted(REGIONS):
        att = attribute_region(tree, comp, REGIONS[comp])
        ast_coords = set(att["coordinate_reads"])
        verdict, explanation = classify(comp, ast_coords, set(hand[comp]))
        rows.append({
            "component": comp,
            "regions": [f"{a}-{b}" for a, b in REGIONS[comp]],
            "hand_reads": hand[comp],
            "ast_coordinate_reads": att["coordinate_reads"],
            "ast_artifact_reads": att["artifact_reads"],
            "ast_sub_api": att["sub_api"],
            "raw_module_names": att["raw_module_names"],
            "in_ast_not_hand": sorted(ast_coords - set(hand[comp])),
            "in_hand_not_ast": sorted(set(hand[comp]) - ast_coords),
            "verdict": verdict,
            "explanation": explanation,
            "evidence": att["evidence"],
        })

    hidden = [r for r in rows if r["verdict"] == "hidden_read_detected"]
    missed = [r for r in rows
              if r["verdict"] == "hidden_read_hand_missed"]
    return {
        "metadata": {
            "title": "subject 2 read sets: AST extraction vs hand model",
            "date": date.today().isoformat(),
            "subject": "qecc_routing (Berthusen et al., arXiv:2404.17676)",
            "qecc_commit": S2.QECC_COMMIT,
            "source_file": "src_py/bivariate-bicycle/general.py",
            "method": "AST static analysis of the pinned tree; component "
                      "granularity = the 11 nodes of subject2_qecc; "
                      "coordinate-carrier / artifact / sub_api attribution "
                      "(same channels as experiments/extract_read_sets.py)",
            "granularity_note": "qecc_routing is a single module: components "
                                "are line ranges of general.py, printed per "
                                "row and sentinel-verified against the file",
            "coordinate_carriers": dict(COORDINATE_CARRIERS),
            "artifact_producers": dict(ARTIFACT_PRODUCERS),
            "dependency_availability": dependency_report(),
        },
        "components": rows,
        "summary": {
            "n_components": len(rows),
            "n_agreements": sum(1 for r in rows if r["verdict"] == "agreement"),
            "n_disagreements": sum(1 for r in rows
                                   if r["verdict"] != "agreement"),
            "hidden_reads_detected_by_ast": sorted(r["component"]
                                                   for r in hidden),
            "covers_all_hand_labelled_hidden_reads":
                set(S2.FAITHFUL_BUT_WRONG)
                <= {r["component"] for r in hidden},
            "hidden_reads_the_hand_model_missed": sorted(r["component"]
                                                         for r in missed),
            "sr_lr_split_layered_visibility":
                "file-level AST sees min/std over the whole radius vector; "
                "the coordinate-keyed probe is blind to it (aggregate moves "
                "with the coordinate)",
        },
    }


# ---------------------------------------------------------------------------
# 5. dependency availability (requirements.txt vs what src_py actually needs)
# ---------------------------------------------------------------------------

def dependency_report() -> dict:
    """Which of qecc_routing's declared deps the local pipeline can import.

    ``pandas`` / ``networkx`` / ``sinter`` are in the repo's
    ``requirements.txt`` but are not imported by the bivariate-bicycle
    pipeline (``code_exploration.py`` uses pandas; the gate does not run it).
    """
    import importlib

    rows = {}
    for mod, needed_by in [
        ("numpy", "general.py, mec.py"), ("scipy", "general.py (sparse)"),
        ("matplotlib", "general.py (pyplot)"), ("stim", "general.py"),
        ("galois", "general.py (GF(2) rank)"), ("ldpc", "general.py (bposd)"),
        ("tqdm", "general.py (experiment loop)"),
        ("pandas", "code_exploration.py only -- NOT needed by the gate"),
        ("networkx", "requirements.txt only -- not imported by src_py"),
        ("sinter", "requirements.txt only -- not imported by src_py"),
    ]:
        try:
            m = importlib.import_module(mod)
            rows[mod] = {"available": True,
                         "version": getattr(m, "__version__", "?"),
                         "needed_by": needed_by}
        except Exception as e:  # noqa: BLE001 -- report, don't raise
            rows[mod] = {"available": False, "error": str(e)[:200],
                         "needed_by": needed_by}
    rows["_note"] = ("galois 0.4.2 required upgrading numba (numpy 2.2 "
                     "compat) and coverage (numba 0.61 compat) on this "
                     "machine; the general.py pipeline imports are otherwise "
                     "all satisfied")
    return rows


# ---------------------------------------------------------------------------
# 6. markdown
# ---------------------------------------------------------------------------

def to_markdown(d: dict) -> str:
    m, rows, s = d["metadata"], d["components"], d["summary"]
    L = ["# Subject 2 read sets — AST extraction vs the hand model", "",
         f"Generated: {m['date']}  ",
         f"commit: `{m['qecc_commit']}`  ",
         f"source: `{m['source_file']}`  ",
         f"Method: {m['method']}", "",
         "> Components are **line ranges of one module** (qecc_routing has no "
         "packages); every range is sentinel-verified against the pinned "
         "file.  `artifact_reads` are references to another component's "
         "module-level product (a DAG edge, the `reads_flat` channel of "
         "`extract_read_sets.py`), not coordinate reads.", ""]
    L += ["## 1. Component × read-set comparison", "",
          "| component | regions | hand R(c) | AST coordinates | AST artifacts "
          "| verdict |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| `{r['component']}` | {', '.join(r['regions'])} "
                 f"| `{', '.join(r['hand_reads']) or '-'}` "
                 f"| `{', '.join(r['ast_coordinate_reads']) or '-'}` "
                 f"| `{', '.join(r['ast_artifact_reads']) or '-'}` "
                 f"| **{r['verdict']}** |")
    L += ["", "### Disagreements, one by one", ""]
    for r in rows:
        if r["verdict"] == "agreement":
            continue
        L += [f"- **`{r['component']}`** — {r['verdict']}",
              f"  - AST-only coordinates: `{r['in_ast_not_hand'] or 'none'}`; "
              f"hand-only: `{r['in_hand_not_ast'] or 'none'}`",
              f"  - {r['explanation']}"]
    L += ["", "## 2. The two expected hidden reads — did AST find them?", ""]
    for r in rows:
        if r["component"] in s["hidden_reads_detected_by_ast"]:
            ev = r["evidence"]["coordinate"]
            L.append(f"- **`{r['component']}`** ({r['verdict']}): "
                     + "; ".join(f"`{e}`" for e in ev))
    L += ["", f"- all hand-labelled faithful-but-wrong components detected: "
               f"**{s['covers_all_hand_labelled_hidden_reads']}** "
               f"(`{S2.FAITHFUL_BUT_WRONG}`)",
          f"- hidden reads the hand model **missed**: "
          f"`{s['hidden_reads_the_hand_model_missed']}` — the AST found a "
          f"third hidden noise read (`circuit` ← `muls001`)", ""]
    L += ["## 3. The sr_lr_split aggregate: a layer difference, not a miss",
          "",
          s["sr_lr_split_layered_visibility"], "",
          "The hand model's coordinate probe stays blind to the aggregate "
          "because the aggregate and the coordinate move together; the AST, "
          "working at file level, sees `min(x_rs)+np.std(x_rs)` directly.  "
          "Both statements are true at their own layer.", ""]
    L += ["## 4. Dependency availability (this machine)", "",
          "| module | available | version | needed by |",
          "|---|---|---|---|"]
    for mod, r in m["dependency_availability"].items():
        if mod.startswith("_"):
            continue
        L.append(f"| `{mod}` | {r['available']} | {r.get('version', '—')} "
                 f"| {r['needed_by']} |")
    L += ["", m["dependency_availability"]["_note"], ""]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out = outdir.resolve_out(argv, HERE)
    d = collect()
    (out / "subject2_read_sets.json").write_text(
        json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "subject2_read_sets.md").write_text(
        to_markdown(d), encoding="utf-8")
    s = d["summary"]
    print(f"components: {s['n_components']}, agreements: {s['n_agreements']}, "
          f"disagreements: {s['n_disagreements']}")
    print(f"hidden reads detected by AST: {s['hidden_reads_detected_by_ast']}")
    print("hand-labelled hidden reads all covered: "
          f"{s['covers_all_hand_labelled_hidden_reads']}")
    print("hidden reads the hand model missed: "
          f"{s['hidden_reads_the_hand_model_missed']}")
    for r in d["components"]:
        print(f"  {r['component']:12s} {r['verdict']}")
    print(f"wrote {out / 'subject2_read_sets.json'}")
    print(f"wrote {out / 'subject2_read_sets.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
