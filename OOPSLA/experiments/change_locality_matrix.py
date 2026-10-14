"""Change-locality measurement matrix (OOPSLA PLAN §5).

For each change scenario x dimension, produce {QUITS, hand-written, ours}
change-locality measurements. QUITS side uses the pre-registered static
attribution from gate_audit/audit_results.json; hand-written Stim assumes
the full monolith is touched (no component boundaries); ours uses
abstraction.measure_cl over the pre-registered 6-component inventory.

**Provenance (why there are two "ours" columns).**  The CL table has two
different "ours" numbers and they come from different models, which used to be
easy to conflate:

* ``ours_cl`` — ``abstraction.measure_cl`` over the **pre-registered 6-component
  inventory** of the (killed) DSL track: "how many components does a change
  scenario touch".  This is a *design-time* count and does not depend on any
  source-derived read set.
* ``semantic_cl`` — ``|cone(x)| / |N|`` on the **source-faithful assembly**
  (``semantics.make_source_faithful_assembly()``, baseline since decision 2 of
  2026-10-09): "how many components must be *re-run* when component x is
  replaced", computed from read sets AST-extracted from the pinned QUITS tree.
  This is a *checker output* and does depend on the modelling, so its source is
  recorded in the output.

Both are recorded in the JSON and the Markdown, each labelled with where its
number comes from.  Neither is a performance claim; see `PIVOT_NOTE` §8.6 item 5
(we do not claim to be more local than QUITS — that was refuted by `gate_audit`).

Output: OOPSLA/experiments/change_locality_matrix.json + .md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from abstraction import measure_cl  # noqa: E402
import outdir  # noqa: E402  (`--out` support; see src/outdir.py)

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent / "gate_audit" / "audit_results.json"

SCENARIO_TO_COMPONENT = {
    "code": ["code"],
    "extraction": ["extractor"],
    "architecture": ["arch"],
    "noise": ["noise"],
    "decoder": ["decoder"],
}


def _reconfigure_stdout() -> None:
    """让 stdout 能打印中文（Windows 默认 cp1252/gbk）。失败则静默忽略。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):        # pragma: no cover - platform dependent
            pass


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    dims = audit["dimensions"]
    # 决策 2 之后：cone-based CL 挂在 source-faithful 基线上，必须记录来源。
    import semantics
    faithful = semantics.make_source_faithful_assembly()
    n_nodes = len(faithful.nodes)
    src = semantics.assembly_model_sources(("source_faithful",))
    rows = []
    for dim, comp in SCENARIO_TO_COMPONENT.items():
        coord = semantics.CALL_SITE_DIMENSIONS.get(dim, dim)
        touched_quits = dims[dim]["touched_packages_est"]
        # normalize QUITS CL by its distinct package count (6 packets incl. decoder/sim/api)
        quits_packages = sorted({p for d in dims.values() for p in d["touched_packages_est"]})
        quits_cl = len(set(touched_quits)) / len(quits_packages)
        ours = measure_cl({"touched": comp})
        cone = faithful.cone(coord)
        rows.append({
            "scenario": dim,
            "semantic_coordinate": coord,
            "quits": {"touched": sorted(set(touched_quits)), "cl": quits_cl},
            "hand_written": {"touched": ["monolith"], "cl": 1.0},
            "ours": {"touched": ours["modified_components"], "cl": ours["cl"]},
            "semantic": {
                "assembly": semantics.BASELINE_ASSEMBLY,
                "cone": sorted(cone),
                "n_nodes": n_nodes,
                "cl": len(cone) / n_nodes,
                "provably_unchanged": sorted(set(faithful.nodes) - {coord} - cone),
                "question": "replace component x (Theorem 1 work sheet)",
            },
            "semantic_coordinate_impact": {
                "impact": sorted(semantics.coordinate_impact(faithful, coord)),
                "cl": len(semantics.coordinate_impact(faithful, coord)) / n_nodes,
                "question": "change coordinate x (QUITS users' actual question)",
            },
        })
    report = {
        "protocol": "gate_audit/protocol.md",
        "baseline_assembly": semantics.BASELINE_ASSEMBLY,
        "baseline_assembly_sources": src,
        "column_provenance": {
            "quits.cl": "pre-registered static attribution from "
                        "gate_audit/audit_results.json (not measured)",
            "hand_written.cl": "assumption: the monolith is touched in full",
            "ours.cl": "abstraction.measure_cl over the pre-registered "
                       "6-component inventory (DSL track; design-time count, "
                       "independent of any source-derived read set)",
            "semantic.cl": f"size of cone(x) divided by the node count on the "
                           f"`{semantics.BASELINE_ASSEMBLY}` assembly; read sets "
                           f"{src['source_faithful']['read_sets']}",
            "semantic_coordinate_impact.cl": "same assembly, but the impact of "
                                             "*changing* a coordinate "
                                             "(PIVOT_NOTE section 4.3) — this, "
                                             "not the cone, is what a QUITS user "
                                             "asks",
        },
        "rows": rows,
    }
    out = outdir.resolve_out(argv, HERE)
    (out / "change_locality_matrix.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

    md = ["# Change Locality Matrix (预对比)", "",
          "## 0. 每列的数字来自哪里", "",
          "| 列 | 建模来源 |", "|---|---|"]
    for col, provenance in report["column_provenance"].items():
        md.append(f"| `{col}` | {provenance} |")
    md += ["",
           f"发布基线 assembly：**`{semantics.BASELINE_ASSEMBLY}`**",
           f"（读集合：{src['source_faithful']['read_sets']}；"
           f"边：{src['source_faithful']['edges']}）", "",
           "两个 ours 的区别是**建模不同**而不是数字冲突："
           "`ours.cl` 是设计期计数（DSL 轨道的 6 组件清单），"
           "`semantic.cl` 是 checker 从源码自动提取的读集合算出来的重跑工作表。"
           "本表是**预对比**；不主张「我们比 QUITS 更局部」（`gate_audit` 已证伪，"
           "见 `PIVOT_NOTE` §8.6 第 5 条）。", "",
           "| 变更场景 | QUITS CL | hand-written CL | ours CL (设计期) "
           "| semantic CL (cone) | semantic CL (改坐标) |",
           "|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['scenario']} | {r['quits']['cl']:.3f} "
                  f"| {r['hand_written']['cl']:.1f} | {r['ours']['cl']:.3f} "
                  f"| {r['semantic']['cl']:.3f} "
                  f"| {r['semantic_coordinate_impact']['cl']:.3f} |")
    md += ["",
           "`semantic CL (cone)` = 替换该组件需要重跑的比例（Theorem 1）；"
           "`semantic CL (改坐标)` = 改该坐标的影响面。"
           "两者在 `noise` 上不同：改 noise 会连带改 extractor 的产物，"
           "而 `cone(noise)` 里没有 extractor（`PIVOT_NOTE` §4.3）。", ""]
    (out / "change_locality_matrix.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    # 表格里有中文；Windows 控制台默认 cp1252，直接 print 会 UnicodeEncodeError。
    _reconfigure_stdout()
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
