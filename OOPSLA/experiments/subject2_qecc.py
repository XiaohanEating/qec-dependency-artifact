"""Second subject system: modelling + minimal validation
(`OOPSLA/subject_system2.md`).

The first subject (QUITS) has a *string registry*: components register
themselves by name and a dispatcher picks them up.  The second candidate —
``third_party/qecc_routing-4ef18121...`` (Berthusen et al., arXiv:2404.17676),
pinned as baseline B2 in ``shared/VERSIONS.md`` — has **no registry at all**:
``src_py/bivariate-bicycle/general.py`` is a single module whose 14 integers
live in a module-level list called ``code`` and whose components are module-level
functions reading those globals.  If the same phenomena (hidden
cross-component dependence, obligations nobody states, locality that is only
visible after the fact) exist there too, they are properties of *runtime
assembly* and not of QUITS's particular extension mechanism.

This script is the executable half of that claim.  It does three things:

1. builds a ``Spec`` / ``Assembly`` for qecc_routing in exactly the terms of
   ``section3_semantics.md`` (Def. 3.1-3.10) — **reusing** ``semantics.py``
   unchanged apart from three additive, default-valued parameters
   (``Component.coordinates``, ``_cartesian(spec_cls=)``,
   ``detect_hidden_dependency(coordinates=)`` and ``spec_cls`` threading),
2. runs the same three operations the QUITS experiments run —
   ``detect_hidden_dependency`` (Theorem 3), ``theorem1_report`` (Theorem 1)
   and ``cone`` (Def. 3.7) — and
3. writes ``subject2_qecc.json`` / ``.md``.

``--constants`` instead dumps the QUITS assembly's DAG, cones and coordinate
impacts, which is where the numbers in ``section3_semantics.md``'s figures come
from.  Running this file does **not** import or execute qecc_routing (its
Stim/C++ products were never built on this platform, ``shared/VERSIONS.md``);
the model is annotated *from the pinned source* and its ``produce`` layer is a
toy in the same sense as QUITS's, with the real-artifact gate deferred to
``stim_circuit_gate.py`` (§5 of ``subject_system2.md``).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import semantics  # noqa: E402  (path shim above)
import outdir  # noqa: E402  (`--out` support; see src/outdir.py)
from semantics import Assembly, Component  # noqa: E402

QECC_COMMIT = "4ef18121c39492414b85ff36b3a61c83f9ebf95f"

# ---------------------------------------------------------------------------
# 0. the pinned tree, and where every annotation comes from
# ---------------------------------------------------------------------------

#: qecc_routing file:line provenance for each modelled component.  Read off the
#: pinned snapshot (read-only); every entry is a claim a reviewer can check.
PROVENANCE = {
    "code": "src_py/bivariate-bicycle/general.py:18 (`code` global) "
            ":53-64 (Hx, Hz from A/B polynomials)",
    "embedding": "general.py:156-202 `embed_code(code, init)`, driven by "
                 "code[8:12] (emb_m, emb_l, A_ind, B_ind)",
    "geometry": "general.py:226-233 x_rs/z_rs = minimal enclosing circle "
                "radius of every check's qubits",
    "sr_lr_split": "general.py:247,259 `if x_rs[i] > min(x_rs)+np.std(x_rs)` "
                   "-- an aggregate over the WHOLE radius vector",
    "succ_probs": "general.py:253,265 `probs[manhattan(...)+1]` -- reads the "
                  "global `probs` table, i.e. the noise coordinate",
    "idle": "general.py:414,422 `0.001+2*code[12]*idle_error` -- noise "
            "multiplied by a code polynomial",
    "logicals": "general.py:139-149 `get_logicals` -> SGSOP on Hx/Hz",
    "schedule": "general.py:309-438 `Simulation(num_rounds, lr_time)`, "
                "`lr_time` = the routing depth",
    "circuit": "general.py:332-334,354-407,410-438 -> stim.Circuit",
    "decoder": "general.py:473-486 `bposd_decoder(pcm, channel_probs=...)`",
}

#: the analogue of `semantics.DOMAIN_EXHAUSTIVE`: which of the five coordinate
#: sets below are exhaustive for the subject system.  code / embedding are
#: exhaustive over the repository's own code list; noise is a parameter table,
#: routing depth and decoder are open-ended -- exactly the PARTIAL situation
#: Theorem 3 (T3-c) has to be honest about.
DOMAIN_EXHAUSTIVE = {
    "code": True,        # the paper enumerates its code list in the repo
    "embedding": True,   # emb_(m,l) x {A_ind,B_ind} are drawn from As/Bs
    "noise": False,      # `probs` / `muls001` are calibrated arrays, not an enum
    "routing": False,    # routing depth is any positive integer
    "decoder": False,    # any ldpc decoder
}


@dataclass(frozen=True)
class QeccSpec:
    """Subject 2's spec domain (Def. 3.1).  Same protocol as ``semantics.Spec``
    -- an immutable value with a ``coords`` projection -- so that every
    semantic routine accepts it via the ``spec_cls`` parameter."""
    code: str = "bb_9_5"
    embedding: str = "toric_4_5_A1B1"
    noise: str = "depolarizing_p1e-3"
    routing: str = "lr5"
    decoder: str = "bposd_ms_osd_cs"

    def coords(self, names) -> dict:
        return {n: getattr(self, n) for n in names}


#: finite domain.  Two code instances and two embeddings (enough for a
#: distinguishable pair on every component that has one), two noise tables,
#: two routing depths, one decoder -- 8 points, so the whole probe is
#: instantaneous.
DOMAIN: dict[str, list] = {
    "code": ["bb_9_5", "bb_12_3"],
    "embedding": ["toric_4_5_A1B1", "toric_6_3_A2B0"],
    "noise": ["depolarizing_p1e-3", "depolarizing_p2e-3"],
    "routing": ["lr5", "lr10"],
    "decoder": ["bposd_ms_osd_cs"],
}
COORDINATES = tuple(sorted(DOMAIN))


# ---------------------------------------------------------------------------
# 1. the model
# ---------------------------------------------------------------------------
#
# Each `produce` below is a *toy* in the same sense QUITS's are: it computes a
# small, faithful-shaped object from the spec coordinate and the predecessor
# artifacts, using exactly the formulas the pinned source uses.  The point is
# not to reproduce a circuit -- it is to make the declared read sets `R(c)`
# either correct or detectably wrong, which is what Theorem 3 decides.

#: general.py:39-40 -- the physical error-rate profile per manhattan distance
_PROBS = {"depolarizing_p1e-3": [0.99, 0.98, 0.97, 0.96, 0.95, 0.94],
          "depolarizing_p2e-3": [0.98, 0.96, 0.94, 0.92, 0.90, 0.88]}
#: general.py:41 `idle_error` -- the idle (leakage) rate of the device
_IDLE = {"depolarizing_p1e-3": 2e-4, "depolarizing_p2e-3": 4e-4}
#: general.py:18 -- the 14 integers: (l, m, a1,a2,a3, b1,b2,b3, emb_l, emb_m,
#: A_ind, B_ind, k_x, k_z).  Only a few are needed for the shape.
_CODE_PARAM = {"bb_9_5": (9, 5, 6), "bb_12_3": (12, 3, 8)}
_EMBED = {"toric_4_5_A1B1": (4, 5, 1, 1), "toric_6_3_A2B0": (6, 3, 2, 0)}


def _make_components() -> dict[str, Component]:
    def code(spec, inp):
        ell, m, _ = _CODE_PARAM[spec.code]
        return {"checks": (ell * m, 2 * ell * m), "data": 2 * ell * m}

    def embedding(spec, inp):
        emb_l, emb_m, _, _ = _EMBED[spec.embedding]
        ell, m, _ = _CODE_PARAM[spec.code]
        return {"lattice": (2 * emb_m, 2 * emb_l), "anchors": ell * m}

    def geometry(spec, inp):
        # general.py:226-233 -- radius of each check's minimal enclosing circle
        _, _, k_x = _CODE_PARAM[spec.code]
        emb_l, emb_m, _, _ = _EMBED[spec.embedding]
        return {"radii": (k_x, emb_l + emb_m)}

    def sr_lr_split(spec, inp):
        # general.py:247,259 -- **the aggregate**: min and std over the whole
        # radius vector decide which checks are long-range.  Note this really
        # does read only {code, embedding}: it is reported under
        # `AGGREGATE_ONLY` because it exhibits the *other* pathology -- a
        # dependency on a whole aggregate of a declared coordinate -- which a
        # coordinate-keyed probe cannot see (see subject_system2.md §5).
        r = inp["geometry"]["radii"]
        return {"split": ("radius > mean+std", r)}

    def succ_probs(spec, inp):
        # general.py:253,265 -- success probability per check, multiplied over
        # its data qubits, indexed by the *physical error profile* `probs`.
        k_x, _, _ = _CODE_PARAM[spec.code]
        return {"p": (k_x, tuple(_PROBS[spec.noise]))}

    def idle(spec, inp):
        # general.py:414,422 -- `0.001 + 2*code[12]*idle_error`: a noise
        # constant times a code polynomial.  A second, independent place where
        # the noise coordinate is baked into a component that reads only
        # `code`.
        _, _, k_z = _CODE_PARAM[spec.code]
        return {"idle_rate": 1e-3 + 2 * k_z * _IDLE[spec.noise]}

    def logicals(spec, inp):
        _, m, _ = _CODE_PARAM[spec.code]
        return {"k": 2 * m, "from": inp["code"]["checks"]}

    def schedule(spec, inp):
        # general.py:309-438 -- the round schedule.  Reads the split, the
        # success probabilities, the idle rate and the routing depth.
        depth = int(spec.routing.removeprefix("lr"))
        return {"lr_time": depth,
                "lr": len(inp["sr_lr_split"]["split"][1]) > 0,
                "p0": inp["succ_probs"]["p"],
                "idle": inp["idle"]["idle_rate"]}

    def circuit(spec, inp):
        k = inp["logicals"]["k"]
        return {"n_rounds_markers": (inp["schedule"]["lr_time"], 2 * k),
                "obs": k}

    def decoder(spec, inp):
        return {"name": spec.decoder,
                "n_err": sum(inp["circuit"]["n_rounds_markers"])}

    def sink(spec, inp):
        return tuple(sorted((k, str(v)) for k, v in inp.items()))

    # NOTE the entries marked FAITHFUL-BUT-WRONG: they declare only what a
    # reader of the source would call "their" coordinate, and they are *wrong*
    # -- the source reads `probs` / `idle_error` inside them.  That is the
    # instance of hypothesis H3 on a system that has no registry at all.
    specs = [
        ("code", ("code",), code, lambda a: a["checks"][0] > 0),
        ("embedding", ("code", "embedding"), embedding,
         lambda a: a["anchors"] > 0),
        ("geometry", ("embedding",), geometry, lambda a: True),
        ("sr_lr_split", ("code", "embedding"), sr_lr_split, lambda a: True),
        ("logicals", ("code",), logicals, lambda a: a["k"] >= 0),
        ("succ_probs", ("code",), succ_probs, lambda a: a["p"][1][0] > 0),
        ("idle", ("code",), idle, lambda a: a["idle_rate"] > 0),
        ("schedule", ("code", "routing"), schedule, lambda a: True),
        ("circuit", ("code", "embedding"), circuit, lambda a: True),
        ("decoder", ("decoder",), decoder, lambda a: True),
        ("sink", COORDINATES, sink, lambda a: True),
    ]
    out = {}
    for name, reads, produce, contract in specs:
        out[name] = Component(name, reads, produce, contract=contract,
                              coordinates=COORDINATES)
    return out


#: dependency edges -- which component consumes whose artifact.  Derived from
#: the call graph above (the DAG `produce` functions read `inp[...]`).
EDGES = {
    "code": (),
    "embedding": ("code",),
    "geometry": ("embedding",),
    "sr_lr_split": ("geometry",),
    "logicals": ("code",),
    "succ_probs": ("code",),
    "idle": ("code",),
    "schedule": ("sr_lr_split", "succ_probs", "idle"),
    "circuit": ("schedule", "logicals"),
    "decoder": ("circuit",),
    "sink": ("code", "embedding", "geometry", "sr_lr_split", "logicals",
             "succ_probs", "idle", "schedule", "circuit", "decoder"),
}


def make_assembly() -> Assembly:
    """The qecc_routing assembly, in the objects of ``section3_semantics.md``."""
    return Assembly(nodes=_make_components(), edges=dict(EDGES))


def inputs_for(A: Assembly, name: str):
    """General-model predecessor supply (Def. 3.10's ``iota``), same contract
    as ``semantics.predecessor_inputs``."""
    return semantics.predecessor_inputs(A, name)


# ---------------------------------------------------------------------------
# 2. the three operations
# ---------------------------------------------------------------------------

#: Components whose declared ``R(c)`` is what a source-reading human would
#: write, and is nevertheless **wrong**: the pinned source reads the global
#: ``probs`` / ``idle_error`` tables inside them (general.py:253, 265, 414,
#: 422).  This is the instance of hypothesis H3 on a system with no registry.
FAITHFUL_BUT_WRONG = ("succ_probs", "idle")

#: Components that are declared correctly but depend on a whole **aggregate**
#: of a declared coordinate (``min``/``std`` over every check's radius,
#: general.py:247,259).  A coordinate-keyed probe is structurally blind to
#: this: both the aggregate and the coordinate move together, so no bucket
#: ever collides.  Recorded as a limitation, not as a detection.
AGGREGATE_ONLY = ("sr_lr_split",)


def readers_of(A: Assembly, coord: str) -> list[str]:
    """Nodes whose declared read set contains ``coord``."""
    return sorted(n for n in A.nodes if coord in set(A.nodes[n].reads))


def probe_hidden_reads(A: Assembly) -> list[dict]:
    """Theorem 3 on every node, general model (Def. 3.10)."""
    rows = []
    for name in sorted(A.nodes):
        rep = semantics.detect_hidden_dependency(
            A.nodes[name], DOMAIN, inputs_for=inputs_for(A, name),
            coordinates=COORDINATES, spec_cls=QeccSpec)
        rows.append({
            "component": name,
            "declared_reads": rep["declared_reads"],
            "observed_extensions": rep["observed_extensions"],
            "observed_reads_subset_declared": rep["observed_reads_subset_declared"],
            "verdict": rep["verdict"],
            "faithful_but_wrong": name in FAITHFUL_BUT_WRONG,
            "aggregate_only": name in AGGREGATE_ONLY,
        })
    return rows


def _alt_component(A: Assembly, name: str) -> Component:
    """A (C4)-satisfying alternative for `name`: same R(c), same output
    coordinate, same artifact on every point of R(c) -- written differently.

    For subject 2 this is the honest analogue of QUITS's
    ``stim_circuit_gate`` "spelling variant" alternative: qecc_routing has one
    construction path per quantity, so (C4) can only be satisfied by a
    re-spelling.  That the alternative is *available at all* is what
    ``gate_audit`` showed for QUITS and this reproduces."""
    node = A.nodes[name]
    return Component(name, node.reads, node.produce,
                     contract=node.contract, coordinates=COORDINATES)


def run_theorem1(A: Assembly) -> list[dict]:
    """(C1)-(C4) + cone, general model, for every node."""
    rows = []
    for name in sorted(A.nodes):
        rep = semantics.theorem1_report(A, name, _alt_component(A, name),
                                        domain_values=DOMAIN,
                                        inputs_for=inputs_for(A, name),
                                        spec_cls=QeccSpec)
        rows.append({
            "component": name,
            "checks": rep["checks"],
            "applicable": rep["applicable"],
            "cone": rep["cone_nodes_rerun"],
            "cone_size": len(rep["cone_nodes_rerun"]),
            "provably_unchanged": rep["provably_unchanged_nodes"],
            "n_nodes": rep["n_nodes"],
            "cl_cone": len(rep["cone_nodes_rerun"]) / rep["n_nodes"],
        })
    return rows


def run_cone_table(A: Assembly) -> list[dict]:
    """Def. 3.12 vs. Def. 3.13 on subject 2.

    QUITS maps one component node onto each coordinate, so ``cone(coord)`` is
    literally the cone of the node with that name.  qecc_routing does **not**:
    ``noise`` has no node of its own (two nodes read it), ``routing`` has none
    (one node reads it), and ``sr_lr_split`` is a node with no coordinate of
    its own.  The general form used here is therefore

        cone_of_coordinate(k)  =  ⋃ { cone(v) : k ∈ R(v) }

    which reduces to ``cone(node)`` whenever a node with that name exists, and
    is what a checker should report in general.
    """
    rows = []
    for coord in COORDINATES:
        readers = readers_of(A, coord)
        cone = sorted({u for v in readers for u in A.cone(v)})
        impact = sorted(semantics.coordinate_impact(A, coord))
        rows.append({
            "coordinate": coord,
            "declared_readers": readers,
            "has_node_of_same_name": coord in A.nodes,
            "cone": cone,
            "cone_size": len(cone),
            "coordinate_impact": impact,
            "impact_size": len(impact),
            "agree": cone == impact,
            "nodes_a_cone_report_would_miss": sorted(set(impact) - set(cone)),
            "cone_covers_everything": len(cone) >= len(A.nodes),
        })
    return rows


def structural_comparison(A: Assembly) -> dict:
    """The shape difference that forced ``cone_of_coordinate`` above.

    QUITS is *bijective* on dimensions: five coordinates, five component
    nodes, one-to-one.  qecc_routing is not, and the mismatch is itself a
    finding: it means "which component do I replace?" has no single answer
    here, so Def. 3.12 has to be stated for a *set* of nodes."""
    coords = set(COORDINATES)
    nodes = set(A.nodes)
    return {
        "n_coordinates": len(coords),
        "n_nodes": len(nodes),
        "coordinates_with_a_node": sorted(coords & nodes),
        "coordinates_without_a_node": sorted(coords - nodes),
        "nodes_without_a_coordinate": sorted(nodes - coords),
        "coordinates_with_several_readers": {
            c: readers_of(A, c) for c in COORDINATES
            if len(readers_of(A, c)) > 1},
        "bijective": coords == nodes,
    }


# ---------------------------------------------------------------------------
# 3. QUITS constants (for the figures in section3_semantics.md)
# ---------------------------------------------------------------------------

def quits_constants() -> dict:
    """Read (never transcribe) the numbers drawn in `section3_semantics.md`."""
    A = semantics.make_source_faithful_assembly()
    return {
        "assembly": "source_faithful",
        "nodes": sorted(A.nodes),
        "edges": {k: list(v) for k, v in sorted(A.edges.items())},
        "reads": {k: list(A.nodes[k].reads) for k in sorted(A.nodes)},
        "cone": {x: sorted(A.cone(x)) for x in sorted(A.nodes)},
        "coordinate_impact": {c: sorted(semantics.coordinate_impact(A, c))
                              for c in semantics.COORDINATES},
        "cone_size": {x: len(A.cone(x)) for x in sorted(A.nodes)},
        "n_nodes": len(A.nodes),
    }


# ---------------------------------------------------------------------------
# 4. reporting
# ---------------------------------------------------------------------------

def collect() -> dict:
    A = make_assembly()
    probes = probe_hidden_reads(A)
    detected = {r["component"] for r in probes
                if not r["observed_reads_subset_declared"]}
    t1_rows = run_theorem1(A)
    cone_rows = run_cone_table(A)
    return {
        "metadata": {
            "title": "second subject system: qecc_routing modelled as an assembly",
            "date": date.today().isoformat(),
            "subject": "qecc_routing (Berthusen et al., arXiv:2404.17676)",
            "qecc_commit": QECC_COMMIT,
            "semantics_module": "OOPSLA/src/semantics.py",
            "reuse": "unchanged except three additive default-valued parameters "
                     "(Component.coordinates, _cartesian(spec_cls=), "
                     "detect_hidden_dependency(coordinates=) + spec_cls threading)",
            "modelling_provenance": PROVENANCE,
            "produce_layer": "toy (same sense as QUITS's toy layer); the real "
                             "artifact is a stim.Circuit built by the pinned "
                             "module, never executed on this platform",
        },
        "domain": DOMAIN,
        "domain_exhaustive": DOMAIN_EXHAUSTIVE,
        "coordinates": list(COORDINATES),
        "edges": EDGES,
        "nodes": sorted(A.nodes),
        "n_nodes": len(A.nodes),
        "probe": probes,
        "theorem1": run_theorem1(A),
        "structure": structural_comparison(A),
        "cone_table": cone_rows,
        "summary": {
            "hidden_dependencies_detected": sorted(detected),
            "declared_faithful_but_wrong": sorted(FAITHFUL_BUT_WRONG),
            "probe_covers_all_faithful_but_wrong":
                set(FAITHFUL_BUT_WRONG) <= detected,
            "false_positives": sorted(detected - set(FAITHFUL_BUT_WRONG)),
            "aggregate_only_blind_spot": sorted(AGGREGATE_ONLY),
            "coordinate_node_map_is_bijective":
                structural_comparison(A)["bijective"],
            "cone_vs_impact_agree_on": sum(1 for r in cone_rows if r["agree"]),
            "cone_vs_impact_disagree_on": sorted(
                r["coordinate"] for r in cone_rows if not r["agree"]),
            "nodes_a_cone_report_would_miss": {
                r["coordinate"]: r["nodes_a_cone_report_would_miss"]
                for r in cone_rows if r["nodes_a_cone_report_would_miss"]},
            "max_nodes_a_cone_report_would_miss": max(
                (len(r["nodes_a_cone_report_would_miss"]) for r in cone_rows),
                default=0),
            "theorem1_applicable_on": sum(1 for r in t1_rows if r["applicable"]),
            "n_nodes_total": len(A.nodes),
        },
    }


def to_markdown(d: dict) -> str:
    m, s = d["metadata"], d["summary"]
    md = [f"# Second subject system — {m['subject']}", "",
          f"Generated: {m['date']}  ",
          f"commit: `{m['qecc_commit']}`  ",
          f"formal core: `{m['semantics_module']}`  ", "",
          f"Reuse of the formal core: {m['reuse']}", "",
          "> " + m["produce_layer"], "",
          "Modelling provenance (pinned file:line):", ""]
    for k, v in m["modelling_provenance"].items():
        md.append(f"- `{k}` — {v}")
    md += ["", f"## 0. domain ({len(d['coordinates'])} coordinates, "
              f"{d['n_nodes']} nodes)", "",
           "| coordinate | exhaustive? | values | declared readers |",
           "|---|---|---|---|"]
    readers = {r["coordinate"]: r["declared_readers"]
               for r in d["cone_table"]}
    for c in d["coordinates"]:
        md.append(f"| `{c}` | {d['domain_exhaustive'][c]} | "
                  f"{len(d['domain'][c])} | {readers[c]} |")
    st = d["structure"]
    md += ["", "### structure: coordinates vs. component nodes", "",
           f"- coordinates: {st['n_coordinates']}, nodes: {st['n_nodes']}",
           f"- bijective (QUITS's shape): **{st['bijective']}**",
           f"- coordinates with **no** node of the same name: "
           f"`{st['coordinates_without_a_node']}`",
           f"- nodes with **no** coordinate of the same name: "
           f"`{st['nodes_without_a_coordinate']}`",
           f"- coordinates read by more than one node: "
           f"`{st['coordinates_with_several_readers']}`", "",
           "## 1. Theorem 3 — hidden reads on a system with no registry", "",
           "| component | declared R(c) | observed ⊄ declared | extensions | "
           "class |", "|---|---|---|---|---|"]
    for r in d["probe"]:
        if r["component"] in s["declared_faithful_but_wrong"]:
            cls = "**faithful-but-wrong**"
        elif r["component"] in s["aggregate_only_blind_spot"]:
            cls = "aggregate-only (probe-blind)"
        else:
            cls = "faithful"
        md.append(f"| `{r['component']}` | {r['declared_reads']} | "
                  f"{not r['observed_reads_subset_declared']} | "
                  f"{r['observed_extensions'] or '—'} | {cls} |")
    md += ["", f"- **detected**: `{s['hidden_dependencies_detected']}`",
           f"- **declared faithful-but-wrong**: "
           f"`{s['declared_faithful_but_wrong']}`",
           f"- **all of them detected**: {s['probe_covers_all_faithful_but_wrong']}",
           f"- **false positives**: {s['false_positives'] or 'none'}",
           f"- **declared correctly but probe-blind (aggregate dependence)**: "
           f"`{s['aggregate_only_blind_spot']}`", "",
           "## 2. Theorem 1 — side conditions and cone", "",
           "| component | cone | \\|cone\\|/\\|N\\| | applicable |",
           "|---|---|---|---|"]
    for r in d["theorem1"]:
        md.append(f"| `{r['component']}` | {r['cone']} | {r['cl_cone']:.3f} | "
                  f"{r['applicable']} |")
    md += ["", f"applicable on {s['theorem1_applicable_on']}/"
               f"{s['n_nodes_total']} nodes", "",
           "## 3. cone vs. coordinate impact (Def. 3.12 vs. 3.13)", "",
           "| coordinate | readers | cone | impact | agree |",
           "|---|---|---|---|---|"]
    for r in d["cone_table"]:
        md.append(f"| `{r['coordinate']}` | {r['declared_readers']} | "
                  f"{r['cone_size']} | {r['impact_size']} | {r['agree']} |")
    md += ["", f"agree on {s['cone_vs_impact_agree_on']}/"
               f"{len(d['coordinates'])}; disagree on "
               f"{s['cone_vs_impact_disagree_on']}", "",
           "The two notions differ by construction whenever a coordinate is read "
           "by a node other than one of the same name (that is the case for "
           "every coordinate here).  The actionable number is the third column: "
           "**how many nodes a cone-only report would have missed**.", "",
           "| coordinate | readers | cone | impact | missed by a cone report |",
           "|---|---|---|---|---|"]
    for r in d["cone_table"]:
        md.append(f"| `{r['coordinate']}` | {len(r['declared_readers'])} | "
                  f"{r['cone_size']} | {r['impact_size']} | "
                  f"{r['nodes_a_cone_report_would_miss']} |")
    md += ["", f"largest miss: "
               f"{s['max_nodes_a_cone_report_would_miss']} nodes", ""]
    return "\n".join(md)


def _reconfigure_stdout() -> None:
    """让 stdout 能打印中文/数学符号（Windows 默认 cp1252）。失败则静默忽略。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):        # pragma: no cover - platform dependent
            pass


def main(argv: list[str] | None = None) -> int:
    _reconfigure_stdout()
    argv = list(sys.argv[1:] if argv is None else argv)
    out = outdir.resolve_out(argv, HERE)
    if "--constants" in argv:
        (out / "figures_constants.json").write_text(
            json.dumps(quits_constants(), indent=2), encoding="utf-8")
        print(f"wrote {out / 'figures_constants.json'}")
        return 0
    d = collect()
    (out / "subject2_qecc.json").write_text(
        json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "subject2_qecc.md").write_text(to_markdown(d), encoding="utf-8")
    for line in to_markdown(d).splitlines():
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())