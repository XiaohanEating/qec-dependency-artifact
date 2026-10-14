"""48-configuration cross-product cone table (OOPSLA PIVOT_NOTE §5 next step (1)).

Generates 48 configs from the C0 corpus (3 codes x 2 architectures x 2 extraction
strategies x 2 noise models x 2 decoders; ``--configs 24`` reproduces the earlier
decoder-pinned 24-config corpus), instantiates each as a semantics.Spec, and for
each dimension replacement (code / extractor / arch / noise / decoder) runs the
Theorem-1 checker to produce a cone table.

Four assemblies are compared, and they are **not** interchangeable — the point of
the table is precisely that they disagree (PIVOT_NOTE §4.3 / §11):

  - ``source_faithful``: ``make_source_faithful_assembly()`` — **the baseline**.
    R(c) auto-extracted from the pinned QUITS tree, DAG edges auto-derived.
  - ``clean``          : ``make_assembly()`` — idealised contrast, all pure, no edges.
  - ``quits_faithful`` : ``make_assembly(with_quits_style=True)`` — the H1
    counterexample (impure extractor); unbounded cones *by construction*.
  - ``quits_dataflow`` : hand-modelled conservative H3 model + ``arch <- code``.

``semantics.ASSEMBLY_MODEL_SOURCES`` records, per assembly, where its read sets
and its edges come from; it is stamped into ``cone_table.json`` metadata and
printed in ``cone_table.md`` §1 so a cone size can never be read without knowing
which modelling produced it.

For every (config, dimension, assembly) the checker reports the cone size, the
number of provably-unchanged nodes (the invariant worksheet `N ∖ ({x} ∪ cone(x))`;
the substituted node x itself is never counted — it is unchanged only when (C4)
holds), and whether Theorem 1 is applicable (all four side conditions hold).  The
trigger-2 summary is computed on the
``source_faithful`` baseline and compares the unbounded distribution against the
three contrasts.

Outputs (written next to this file):
  - ``cone_table.json`` — full machine-readable table + summary
  - ``cone_table.md``   — human-readable table + trigger-2 risk summary

Run:  python experiments/cone_table.py [--configs 24]
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from semantics import (  # noqa: E402
    BASELINE_ASSEMBLY, COORDINATES, DOMAIN, Assembly, Component, Spec,
    assembly_model_sources, context_independence, make_assembly,
    inadmissible_pairs, make_source_faithful_assembly, pointwise_equal_on_reads,
    signature_ok, substitute, theorem1_report,
)
import outdir  # noqa: E402  (`--out` support; see src/outdir.py)
from abstraction import (  # noqa: E402
    ArchSpec, CodeSpec, DecoderSpec, ExtractorSpec, NoiseSpec,
    build_configs, load_corpus,
)

# --- cross-product dimensions -------------------------------------------------

CODE_FAMILIES = ("BB", "HGP", "QLP")            # one code per family (C0 corpus)
EXTRACTORS = ("cardinal", "zxcoloration")      # semantic-layer DOMAIN values
ARCHS = ("free", "grid2d")
NOISES = ("SD6", "SI1000")
DECODER_FIXED = "BP-OSD"

#: 决策 2（2026-10-09）之后表里有四个 assembly，其中
#: ``source_faithful`` 是**发布基线**，其余三个是对照。
ASSEMBLY_NAMES = ("clean", "quits_faithful", "quits_dataflow",
                  "source_faithful")


# ---------------------------------------------------------------------------
# 1. cross-product from the C0 corpus
# ---------------------------------------------------------------------------

def pick_codes(corpus: dict) -> list[CodeSpec]:
    """One code per family from the C0 corpus (BB, HGP, QLP)."""
    by_family: dict[str, dict] = {}
    for inst in corpus["instances"]:
        by_family.setdefault(inst["family"], inst)
    return [CodeSpec(by_family[f]["family"], by_family[f]["name"],
                     dict(by_family[f]["quits_ctor"]))
            for f in CODE_FAMILIES]


def _cross_product(decoders: tuple[str, ...]) -> list[dict]:
    """3 codes x 2 archs x 2 extractors x 2 noises x |decoders| configs.

    The two extraction strategies are the semantic-layer DOMAIN values.  We do
    NOT filter by QUITS admissibility (H1): the cross-product is a spec-level
    object, and admissibility is exactly what the semantic layer must expose.
    Under the ``source_faithful`` baseline the admissibility shows up instead as
    a *contract violation* on ``BB + cardinal`` -- see
    ``semantics.inadmissible_pairs()``.
    """
    corpus = load_corpus()
    codes = pick_codes(corpus)
    strategies = {c.name: [ExtractorSpec(s) for s in EXTRACTORS] for c in codes}
    configs: list[dict] = []
    for arch in ARCHS:
        for noise in NOISES:
            for decoder in decoders:
                configs.extend(build_configs(
                    codes, strategies,
                    ArchSpec(arch), NoiseSpec(noise), DecoderSpec(decoder),
                ))
    return configs


def build_configs_all(decoders: tuple[str, ...] = ("BP-OSD", "BP-LSD")) -> list[dict]:
    """48 configs: decoder is a dimension (mirrors P2-4 in ``artifact_invariance``)."""
    return _cross_product(tuple(decoders))


def build_24_configs() -> list[dict]:
    """The historical 24-config corpus (3x2x2x2, decoder pinned to BP-OSD).

    Kept as the default so the published 24-config rows stay comparable; the
    48-config corpus is what the trigger-2 summary now runs on.
    """
    return _cross_product((DECODER_FIXED,))


def config_to_spec(config: dict) -> Spec:
    """Convert a ``build_configs`` dict into a ``semantics.Spec``."""
    return Spec(
        code=config["code"]["family"],
        extractor=config["extractor"]["strategy"],
        arch=config["arch"]["topology"],
        noise=config["noise"]["model"],
        decoder=config["decoder"]["name"],
    )


# ---------------------------------------------------------------------------
# 2. Assemblies
# ---------------------------------------------------------------------------

def make_quits_dataflow_assembly() -> Assembly:
    """Hand-modelled *conservative* H3 dataflow assembly (PIVOT_NOTE §2 H3).

    All components are pure; declared reads AND DAG edges are hand-written and
    deliberately **wider** than what the source requires:

    - extractor reads ``noise`` because ``build_circuit(strategy, error_model=,
      ...)`` bakes the noise model into the circuit;
    - decoder reads everything embedded in the circuit plus its own coordinate.

    DAG edges encode the same dependency: extractor depends on code+noise,
    decoder depends on code+extractor+arch+noise.  This makes cone(noise) =
    {extractor, decoder, experiment} — the H3 non-locality made visible.

    **决策 3（2026-10-09）：``arch <- code`` 边已补上。** 上一轮动态实测证明
    这条边存在——换 code 会改变 ``layout_positions``（``dynamic_impact.json``
    的 ``code`` 行：``layout_positions`` 在 changed_artifacts 里）。补边之前
    ``cone(code)`` 只有 {extractor, decoder, experiment}，漏掉 ``arch``；补边
    之后 ``cone(code) = {extractor, arch, decoder, experiment}``，与
    ``source_faithful`` 的实测/自动提取结果一致。

    注意这个 assembly 仍然**比 source-faithful 更保守**：
    ``extractor <- noise`` 与 ``decoder <- arch`` 都是过近似，
    ``make_source_faithful_assembly()`` 不含它们。
    """
    code = Component("code", ("code",),
                     lambda s: {"kind": "code", "family": s.code},
                     contract=lambda a: a["kind"] == "code")
    extractor = Component("extractor", ("code", "extractor", "noise"),
                          lambda s: f"{s.extractor}@{s.code}+{s.noise}")
    arch = Component("arch", ("arch",),
                     lambda s: {"constraints": {"grid2d": [16, 16]}.get(s.arch, [])})
    noise = Component("noise", ("noise",),
                      lambda s: {"model": s.noise,
                                 "p": {"SD6": 1e-3, "SI1000": 2e-4}[s.noise]})
    decoder = Component("decoder", ("code", "extractor", "arch", "noise", "decoder"),
                        lambda s: {"name": s.decoder, "osd_order": 0},
                        contract=lambda a: a["name"] in {"BP-OSD", "BP-LSD"})
    comps = {"code": code, "extractor": extractor, "arch": arch,
             "noise": noise, "decoder": decoder}
    nodes = dict(comps)
    nodes["experiment"] = Component(
        "experiment", ("code", "extractor", "arch", "noise", "decoder"),
        lambda s: tuple(sorted(
            (n, str(c.produce(s))) for n, c in comps.items())))
    edges = {
        "code": (),
        "extractor": ("code", "noise"),
        # 决策 3：实测换 code 会改 layout_positions ⇒ arch 是 code artifact 的
        # 消费者（Layout(code)），所以 arch 依赖 code。补这条边之前 cone(code)
        # 漏掉 arch，被 dynamic_impact 判为 over-coverage 缺口。
        "arch": ("code",),
        "noise": (),
        "decoder": ("code", "extractor", "arch", "noise"),
        "experiment": tuple(comps),
    }
    return Assembly(nodes=nodes, edges=edges)


def build_assemblies() -> dict[str, Assembly]:
    """The four assemblies compared by this table (see the module docstring).

    ``source_faithful`` is the published baseline since 决策 2 (2026-10-09);
    the other three are retained contrasts, each isolating one modelling choice:

    =====================  ====================================================
    ``clean``              no DAG edges at all -> every cone is a single point
    ``quits_faithful``     same, plus one *impure* component -> unbounded cones
    ``quits_dataflow``     hand-modelled conservative H3 edges (+ ``arch<-code``)
    ``source_faithful``    auto-extracted R(c) + auto-derived edges  ← baseline
    =====================  ====================================================
    """
    return {
        "clean": make_assembly(),
        "quits_faithful": make_assembly(with_quits_style=True),
        "quits_dataflow": make_quits_dataflow_assembly(),
        "source_faithful": make_source_faithful_assembly(),
    }


# ---------------------------------------------------------------------------
# 3. Theorem-1 checker (substitute + all four side conditions)
# ---------------------------------------------------------------------------

def make_alt(dim: str, original: Component) -> Component:
    """Equivalent alternative: same signature and behaviour (pointwise equal)."""
    return Component(dim, original.reads, original.produce, original.contract)


def full_substitute(A: Assembly, dim: str, alt: Component,
                    domain_values: dict[str, list] | None = None) -> dict:
    """The complete Theorem-1 side-condition report, general model.

    The four conditions (PIVOT_NOTE §3, Theorem 1):
      (C1) x   is context-independent,
      (C2) x'  is context-independent,
      (C3) signature_ok(x, x')  — same declared reads and output coordinate,
      (C4) x and x' are pointwise equal on R(x).

    决策 2 之后这张表要跑在 ``source_faithful`` 上，而那个 assembly 有真实
    的 DAG 边（``arch <- code`` 等）。在 arity-1 探测下，一个消费前驱 artifact
    的组件会被误判成 impure，所以这里必须走
    ``semantics.theorem1_report``（它内部用 ``predecessor_inputs`` 供给前驱
    artifact，并在 (C1)/(C2)/(C4) 之间 memoize）。
    """
    return theorem1_report(A, dim, alt,
                           domain_values if domain_values is not None else DOMAIN)


def run_all(assemblies: dict[str, Assembly], configs: list[dict]) -> list[dict]:
    """For every (config, dimension, assembly) run the Theorem-1 checker."""
    rows: list[dict] = []
    for ci, config in enumerate(configs):
        spec = config_to_spec(config)
        for dim in COORDINATES:
            for asm_name in ASSEMBLY_NAMES:
                A = assemblies[asm_name]
                alt = make_alt(dim, A.nodes[dim])
                r = full_substitute(A, dim, alt)
                rows.append({
                    "config_id": ci,
                    "config": {"code": spec.code, "extractor": spec.extractor,
                               "arch": spec.arch, "noise": spec.noise,
                               "decoder": spec.decoder},
                    "dimension": dim,
                    "assembly": asm_name,
                    "cone_size": len(r["cone_nodes_rerun"]),
                    "provably_unchanged": len(r["provably_unchanged_nodes"]),
                    "applicable": r["applicable"],
                    "checks": r["checks"],
                })
    return rows


# ---------------------------------------------------------------------------
# 4. Trigger-2 risk summary
# ---------------------------------------------------------------------------

def summarize(rows: list[dict], baseline: str = BASELINE_ASSEMBLY) -> dict:
    """Count unbounded cones per assembly, and re-derive trigger-2 (决策 4).

    **unbounded** 的定义保持与上一轮一致：``applicable=False``（(C1)–(C4) 任一
    失败 ⇒ checker 拒绝给出"cone 外不变"）。

    **verdict 的口径变了**（这是决策 4 的核心）。上一轮把 ``quits_faithful``
    当作"QUITS-faithful 建模"，而它其实是一个**故意构造的不纯反例**，所以
    verdict 永远是 `localized`。现在：

    - verdict 在 **baseline（``source_faithful``）** 上算，而不是在反例上算；
    - 语义与 PLAN §9 trigger 2 对齐：**unbounded > 0 且 < total ⇒
      localized**（unboundedness 局部化，局部替换仍可判定）；
      **unbounded == total ⇒ 全域 unbounded**，此时 Theorem 1 退化为
      "所有组件都要重验证"，即 trigger 2 命中，触发止损；
      **unbounded == 0 ⇒ bounded**，无局部性风险。

    反例列（``quits_faithful``）保留，但它的 unbounded 分布现在被读作
    "如果建模者像旧版那样把 registry 隐藏依赖当成不存在，会发生什么"。
    """
    summary: dict = {}
    for asm_name in ASSEMBLY_NAMES:
        asm_rows = [r for r in rows if r["assembly"] == asm_name]
        by_dim: dict = {}
        for dim in COORDINATES:
            dr = [r for r in asm_rows if r["dimension"] == dim]
            by_dim[dim] = {
                "total": len(dr),
                "applicable": sum(1 for r in dr if r["applicable"]),
                "unbounded": sum(1 for r in dr if not r["applicable"]),
                "cone_sizes": sorted({r["cone_size"] for r in dr}),
            }
        summary[asm_name] = {
            "total": len(asm_rows),
            "applicable": sum(1 for r in asm_rows if r["applicable"]),
            "unbounded": sum(1 for r in asm_rows if not r["applicable"]),
            "by_dimension": by_dim,
        }
    base = summary[baseline]
    qf = summary["quits_faithful"]
    ub, tot = base["unbounded"], base["total"]
    if ub == 0:
        verdict = "bounded"
    elif ub < tot:
        verdict = "localized"
    else:
        verdict = "unbounded"
    summary["trigger2_risk"] = {
        "baseline_assembly": baseline,
        "verdict": verdict,
        "unbounded_in_baseline": ub,
        "total_in_baseline": tot,
        "applicable_in_baseline": base["applicable"],
        "unbounded_in_quits_faithful": qf["unbounded"],
        "total_in_quits_faithful": qf["total"],
        "unbounded_in_quits_dataflow": summary["quits_dataflow"]["unbounded"],
        "unbounded_in_clean": summary["clean"]["unbounded"],
        "description": (
            f"Verdict on the published baseline `{baseline}`: **{verdict}** "
            f"({ub}/{tot} substitutions unbounded, {base['applicable']}/{tot} "
            f"certified applicable). Cone sizes on that baseline: "
            + ", ".join(f"{dim}="
                        f"{base['by_dimension'][dim]['cone_sizes']}"
                        for dim in COORDINATES)
            + ". "
            "The contrast columns isolate *why* an assembly can be unbounded: "
            f"`clean` has {summary['clean']['unbounded']}/{summary['clean']['total']} "
            f"and `quits_dataflow` has {summary['quits_dataflow']['unbounded']}/"
            f"{summary['quits_dataflow']['total']}, while the hand-built H1 "
            f"counterexample `quits_faithful` has {qf['unbounded']}/{qf['total']} "
            "— every one of them in the `extractor` dimension, because that "
            "component declares reads=('code',) while its registry lookup also "
            "reads the `extractor` coordinate, so (C1)/(C2) fail and Theorem 3 "
            "reports observed ⊄ declared. Faithfulness *alone* therefore does not "
            "cause unboundedness; an under-declared read set does. "
            + ("On the baseline the checker certifies locality for every "
               "configuration and dimension, so PLAN §9 trigger 2 (the theorem "
               "being only stateable as 're-verify everything') is NOT hit."
               if verdict == "bounded" else
               "PLAN §9 trigger 2 is hit on the baseline: the checker cannot "
               "certify locality for any substitution.")
        ),
    }
    return summary


# ---------------------------------------------------------------------------
# 5. Output
# ---------------------------------------------------------------------------

def generate_json(configs: list[dict], rows: list[dict], summary: dict,
                  baseline: str = BASELINE_ASSEMBLY) -> dict:
    decoders = sorted({config_to_spec(c).decoder for c in configs})
    return {
        "metadata": {
            "description": "cross-product cone table over four QUITS assemblies",
            "date": date.today().isoformat(),
            "n_configs": len(configs),
            "n_dimensions": len(COORDINATES),
            "n_rows": len(rows),
            "assemblies": list(ASSEMBLY_NAMES),
            # 决策 2/3：显式记录每个 assembly 的读集合与边的来源，避免本文件
            # 的 cone 数字被与其无关的建模来源误读。
            "baseline_assembly": baseline,
            "assembly_model_sources": assembly_model_sources(ASSEMBLY_NAMES),
            "domain": DOMAIN,
            "decoders": decoders,
            "decoder_is_a_dimension": len(decoders) > 1,
            "cross_product": {
                "codes": list(CODE_FAMILIES),
                "architectures": list(ARCHS),
                "extraction_strategies": list(EXTRACTORS),
                "noise_models": list(NOISES),
                "decoders": decoders,
            },
        },
        "configs": [
            {"id": ci, **config_to_spec(c).__dict__}
            for ci, c in enumerate(configs)
        ],
        "rows": rows,
        "summary": summary,
    }


def _provenance_lines() -> list[str]:
    """The 'which modelling produced this cone?' header block."""
    src = assembly_model_sources(ASSEMBLY_NAMES)
    out = ["## 0. Modelling provenance (which assembly produced which number)",
           "",
           f"Baseline for the published claims and the trigger-2 verdict: "
           f"**`{BASELINE_ASSEMBLY}`**.",
           "",
           "| assembly | baseline | read sets come from | DAG edges come from "
           "| faithful? |",
           "|---|:---:|---|---|---|"]
    for asm in ASSEMBLY_NAMES:
        s = src[asm]
        out.append(f"| `{asm}` | {'**yes**' if s['baseline'] else 'no'} "
                   f"| {s['read_sets']} | {s['edges']} | {s['faithfulness']} |")
    out += ["",
            f"Source of truth for the tables: `semantics.ASSEMBLY_MODEL_SOURCES` "
            f"(regenerated by `python experiments/cone_table.py`).",
            ""]
    return out


def generate_md(configs: list[dict], rows: list[dict], summary: dict,
                baseline: str = BASELINE_ASSEMBLY) -> str:
    L: list[str] = []
    L.append("# Cone Table — Cross-Product over Four QUITS Assemblies")
    L.append("")
    L.append(f"Generated: {date.today().isoformat()}  ")
    L.append(f"Cross-product: {len(CODE_FAMILIES)} codes × {len(ARCHS)} architectures "
             f"× {len(EXTRACTORS)} extraction strategies × {len(NOISES)} noise models "
             f"× {len({config_to_spec(c).decoder for c in configs})} decoders "
             f"= {len(configs)} configs.")
    L.append("")
    L.append(f"Published baseline assembly: **`{baseline}`** "
             f"(see §0; decisions 2-4 of 2026-10-09).")
    L.append("")
    L.extend(_provenance_lines())

    # --- config table ---
    L.append("## 1. Configs")
    L.append("")
    L.append("| id | code | extractor | arch | noise | decoder | admissible (H1) |")
    L.append("|---:|---|---|---|---|---|:---:|")
    inadmissible = set(inadmissible_pairs())
    for ci, c in enumerate(configs):
        s = config_to_spec(c)
        ok = (s.code, s.extractor) not in inadmissible
        L.append(f"| {ci} | {s.code} | {s.extractor} | {s.arch} | {s.noise} "
                 f"| {s.decoder} | {'yes' if ok else '**no**'} |")
    L.append("")
    L.append("The cross-product is a *spec-level* object: QUITS admissibility (H1) "
             "is not filtered out here. Under the `source_faithful` baseline it "
             "surfaces as a `contract violated: extractor` instead, which is the "
             "point — the refusal is a stated obligation, not a runtime raise.")
    L.append("")

    # --- main cone table on the baseline ---
    base_rows = [r for r in rows if r["assembly"] == baseline]
    L.append(f"## 2. Cone table — baseline assembly (`{baseline}`)")
    L.append("")
    L.append("One row per (config, dimension). `provably_unchanged` = nodes outside "
             "`{x} ∪ cone(x)` whose artifacts are guaranteed identical (Theorem 1; "
             "the substituted node x itself is excluded from the worksheet — it "
             "is unchanged only when (C4) holds, PIVOT_NOTE §6.1 Step 1).")
    L.append("")
    L.append("| config | dimension | cone_size | provably_unchanged | applicable |")
    L.append("|---|---|---:|---:|:---:|")
    for r in base_rows:
        c = r["config"]
        label = (f"{c['code']}/{c['extractor']}/{c['arch']}/{c['noise']}"
                 f"/{c['decoder']}")
        L.append(f"| {label} | {r['dimension']} | {r['cone_size']} "
                 f"| {r['provably_unchanged']} | {str(r['applicable']).lower()} |")
    L.append("")
    L.append("Cone sizes on this baseline are constant per dimension (they do not "
             "depend on the configuration), which is the point of the table: the "
             "work sheet is a property of the *assembly*, not of the spec.")
    L.append("")

    # --- assembly comparison ---
    L.append("## 3. Assembly comparison (per dimension)")
    L.append("")
    L.append("| assembly | " + " | ".join(COORDINATES) + " | unbounded |")
    L.append("|---|" + "---:|" * (len(COORDINATES) + 1))
    for asm in ASSEMBLY_NAMES:
        cells = []
        for dim in COORDINATES:
            dr = [r for r in rows
                  if r["assembly"] == asm and r["dimension"] == dim]
            cone = sorted({r["cone_size"] for r in dr})
            appl = all(r["applicable"] for r in dr)
            cells.append(f"{cone[0] if len(cone) == 1 else cone}"
                         f"{'' if appl else ' (!)'}")
        ub = summary[asm]["unbounded"]
        L.append(f"| `{asm}` | " + " | ".join(cells) + f" | {ub} |")
    L.append("")
    L.append("Entries are `cone_size` per dimension; `(!)` marks a dimension whose "
             "side conditions fail on some configurations (applicable=False).")
    L.append("")

    # --- trigger-2 risk summary ---
    t2 = summary["trigger2_risk"]
    L.append("## 4. Trigger-2 risk summary")
    L.append("")
    L.append(f"**Verdict on the baseline `{t2['baseline_assembly']}`: "
             f"{t2['verdict']}**  ")
    L.append("")
    L.append(t2["description"])
    L.append("")
    L.append("| assembly | total | applicable | unbounded |")
    L.append("|---|---:|---:|---:|")
    for asm in ASSEMBLY_NAMES:
        s = summary[asm]
        mark = " (baseline)" if asm == baseline else ""
        L.append(f"| {asm}{mark} | {s['total']} | {s['applicable']} "
                 f"| {s['unbounded']} |")
    L.append("")
    L.append("Unbounded distribution **on the baseline**, per dimension:")
    L.append("")
    L.append("| dimension | total | applicable | unbounded | cone sizes |")
    L.append("|---|---:|---:|---:|---|")
    for dim in COORDINATES:
        d = summary[baseline]["by_dimension"][dim]
        L.append(f"| {dim} | {d['total']} | {d['applicable']} | {d['unbounded']} "
                 f"| {d['cone_sizes']} |")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def _reconfigure_stdout() -> None:
    """让 stdout 能打印非 ASCII（本脚本输出含中文与破折号）。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):        # pragma: no cover - platform dep.
            pass


def main(argv: list[str] | None = None) -> int:
    _reconfigure_stdout()
    argv = list(sys.argv[1:] if argv is None else argv)
    # 决策 4：默认跑 48 配置（decoder 成一维），`--configs 24` 退回旧口径。
    configs = build_24_configs() if "24" in argv else build_configs_all()
    assemblies = build_assemblies()
    rows = run_all(assemblies, configs)
    summary = summarize(rows, BASELINE_ASSEMBLY)

    data = generate_json(configs, rows, summary, BASELINE_ASSEMBLY)
    out = outdir.resolve_out(argv, HERE)
    json_path = out / "cone_table.json"
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    md_path = out / "cone_table.md"
    md_path.write_text(generate_md(configs, rows, summary, BASELINE_ASSEMBLY),
                       encoding="utf-8")

    # console summary
    print(f"configs: {len(configs)}  rows: {len(rows)}  "
          f"baseline: {BASELINE_ASSEMBLY}")
    for asm in ASSEMBLY_NAMES:
        s = summary[asm]
        mark = "  <- baseline" if asm == BASELINE_ASSEMBLY else ""
        print(f"  {asm:18s} total={s['total']:3d} applicable={s['applicable']:3d} "
              f"unbounded={s['unbounded']:3d}{mark}")
    t2 = summary["trigger2_risk"]
    print(f"trigger-2 verdict on {t2['baseline_assembly']}: {t2['verdict']}")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
