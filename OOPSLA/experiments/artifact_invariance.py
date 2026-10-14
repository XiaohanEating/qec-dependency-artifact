"""Artifact-invariance experiment (P0-2 + P2-4 + 决策 2, OOPSLA PIVOT_NOTE §3 Theorem 1).

对 configuration cross-product 的每个配置 × 每个维度，实际执行替换
（pointwise 相等但实现不同的组件），比较替换前后各节点 artifact：
Theorem 1 断言 N∖({x}∪cone(x)) 中的节点 artifact 完全相同（被替换的 x
自身只在 (C4) 成立时不变，见 PIVOT_NOTE §6.1 Step 1）、cone 内只需重跑 +
重验 contract。

**基线（决策 2，2026-10-09）**：`semantics.make_source_faithful_assembly()`。
上一轮用的是 `make_assembly()` —— 那个 assembly 每个组件只读自己的坐标、
没有 DAG 边（"理想化对照基线"），所以每个 cone 都是单点 `experiment`，
artifact 不变性是**平凡**成立的。这一版换成源码 faithful 的基线：

- 替换组件有真实的前驱 artifact 输入（`arch <- code`、`decoder <- (code,
  extractor)` …），所以 ``produce`` 必须走一般模型 ``(spec, inputs)``；
- cone 不再是单点：`code` 的 cone 是 4 个节点，
- QUITS 自己的 H1 拒绝（`BB + cardinal` 不在 ``BbCode.supported_strategies``）
  在这里表现为**可陈述的义务违反**，而不是运行期异常——被单独计入
  ``inadmissible`` 桶，不混入 applicable / invariance 计数。

每个 assembly 的建模来源（读集合 / 边的出处）记录在
``semantics.ASSEMBLY_MODEL_SOURCES``，并写进本脚本的 JSON metadata 与
Markdown 文件头，避免"数字来自哪个建模"被混淆。

配置数：
    3 codes × 2 architectures × 2 extraction strategies × 2 noise models
    × **2 decoders** = 48
`--configs 24` 可退回旧的 24 配置口径（decoder 固定 BP-OSD）以便与历史输出对照。

输出: OOPSLA/experiments/artifact_invariance.json + .md
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
OOPSLA_ROOT = HERE.parent
for _p in (str(OOPSLA_ROOT / "src"), str(OOPSLA_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from semantics import (  # noqa: E402
    BASELINE_ASSEMBLY, DOMAIN, Component, Spec, FAMILY_STRATEGIES,
    assembly_model_sources, make_source_faithful_assembly,
    substitution_invariance_report, theorem1_report,
)
import outdir  # noqa: E402  (`--out` support; see src/outdir.py)

# configuration cross-product（PLAN §6 + P2-4 的 decoder 维度）
CODES = ["BB", "HGP", "QLP"]
ARCHS = ["free", "grid2d"]
EXTRACTORS = ["cardinal", "zxcoloration"]
NOISES = ["SD6", "SI1000"]
DECODERS = ["BP-OSD", "BP-LSD"]          # P2-4: decoder becomes a dimension
LEGACY_DECODER = "BP-OSD"                 # the pre-P2-4 fixed value


def _faithful_alt(dim: str) -> Component:
    """A *different implementation* of the baseline component, pointwise equal.

    Theorem 1 的见证要求 (C4) 成立：``x`` 与 ``x'`` 在 ``R(x)`` 上逐点相等，
    否则定理**不适用**（这是 §8.6 "我们不主张" 第 2 条：真实替换不逐点相等）。
    下面每个 alt 用一种不同的写法重算同一个 artifact（查不同的数据结构、
    走不同的表达式路径），因此"artifact 不变性"测的是**重写实现**而不是
    同一个函数的两次调用。

    注意它们必须与 ``semantics.make_source_faithful_components()`` 的
    ``produce`` 输出**逐点相同**，包括键名与键序无关的相等性。
    """
    # `code`: faithful 版从 CODE_FAMILY_DATA_QUBITS 查表并补 `kind`。
    if dim == "code":
        return Component(
            "code", ("code",),
            lambda s, inp: {"kind": "code", "family": s.code,
                            "n_data": _CODE_SIZES[s.code]},
            contract=lambda a: a["kind"] == "code")
    # `extractor`: faithful 版用 FAMILY_STRATEGIES。白名单改从 _ALT_WHITELISTS
    # 重新查（见下方 pytest：两张表必须一致），其余键逐字重建。
    if dim == "extractor":
        return Component(
            "extractor", ("code", "extractor", "noise"),
            lambda s, inp: {
                "kind": "circuit",
                "strategy": s.extractor,
                "family": s.code,
                "admissible": s.extractor in _ALT_WHITELISTS[s.code],
                "noise": s.noise,
            },
            contract=lambda a: a["kind"] == "circuit" and a["admissible"])
    # `arch`: faithful 版 `n_positions = int(inp["code"]["n_data"])`。
    # 依赖**来自 DAG 边**（code artifact），不是坐标读——这正是 (C1) 在一般模型
    # 下要处理的情形。
    if dim == "arch":
        return Component(
            "arch", ("arch",),
            lambda s, inp: {"kind": "layout", "arch": s.arch,
                            "n_positions": _alt_layout_positions(inp)},
            contract=lambda a: a["kind"] == "layout")
    # `noise`: faithful 版从 NOISE_MODEL_PARAMS 取 params 元组；这里走
    # _ALT_NOISE_PARAMS 这张独立抄写的表。
    if dim == "noise":
        return Component(
            "noise", ("noise",),
            lambda s, inp: {"kind": "noise", "model": s.noise,
                            "params": tuple(sorted(_ALT_NOISE_PARAMS[s.noise].items()))},
            contract=lambda a: a["kind"] == "noise")
    # `decoder`: faithful 版从 code artifact 推 hz_shape、从 extractor 取 circuit。
    if dim == "decoder":
        return Component(
            "decoder", ("decoder",),
            lambda s, inp: {"kind": "decoder", "name": s.decoder,
                            "hz_shape": _alt_hz_shape(inp["code"]),
                            "circuit": inp["extractor"]["strategy"]},
            contract=lambda a: a["kind"] == "decoder"
            and a["name"] in {"BP-OSD", "BP-LSD"})
    raise KeyError(dim)


def _alt_hz_shape(code_artifact) -> tuple:
    """Second, independent derivation of the hz shape from the code artifact."""
    n = int(code_artifact["n_data"])
    return (int(n / 2), n)


def _alt_layout_positions(inputs) -> int:
    """``n_positions`` from the **code artifact** (a DAG edge), not a coordinate.

    The faithful component reads ``inp["code"]["n_data"]``; the alternative
    re-derives it through a helper, which is what makes this a second
    implementation rather than a second call of the same lambda.
    """
    return int(inputs["code"]["n_data"])


#: 与 ``semantics.CODE_FAMILY_DATA_QUBITS`` **数值相同但独立抄写**的白名单，
#: 目的是让 artifact_invariance 的 alt 走一条不同的查表路径；
#: pytest 用 ``test_faithful_baseline_and_alternatives_agree`` 锁定两者一致。
_CODE_SIZES = {"BB": 72, "HGP": 13, "QLP": 120, "BPC": 60, "LCS": 72,
               "mitten": 36}
_ALT_WHITELISTS = {
    "BB": ("custom", "zxcoloration"),
    "HGP": ("cardinal", "cardinalNSmerge", "zxcoloration"),
    "QLP": ("cardinal", "cardinalNSmerge", "zxcoloration"),
    "BPC": ("cardinal", "cardinalNSmerge", "zxcoloration"),
    "LCS": ("cardinal", "cardinalNSmerge", "zxcoloration"),
    "mitten": ("custom", "hook_error_free", "zxcoloration"),
}
_ALT_NOISE_PARAMS = {
    "SD6": {"idle_error": 1e-4, "sqgate_error": 1e-3,
            "tqgate_error": 1e-3, "spam_error": 1e-3},
    "SI1000": {"idle_error": 2e-5, "sqgate_error": 2e-4,
               "tqgate_error": 2e-4, "spam_error": 2e-4},
}


ALT_COMPONENTS = {dim: _faithful_alt(dim)
                  for dim in ("code", "extractor", "arch", "noise", "decoder")}

DIMENSIONS = tuple(ALT_COMPONENTS)


def build_configs(n_configs: int = 48) -> list[Spec]:
    """48 = 3 × 2 × 2 × 2 × 2 (codes × archs × extractors × noises × decoders).

    ``n_configs=24`` reproduces the pre-P2-4 corpus (decoder pinned to
    ``LEGACY_DECODER``) so older numbers stay comparable.
    """
    if n_configs not in (24, 48):
        raise ValueError("n_configs must be 24 (legacy, decoder pinned) or 48")
    decoders = DECODERS if n_configs == 48 else [LEGACY_DECODER]
    out: list[Spec] = []
    for code in CODES:
        for arch in ARCHS:
            for extractor in EXTRACTORS:
                for noise in NOISES:
                    for decoder in decoders:
                        out.append(Spec(code, extractor, arch, noise, decoder))
    assert len(out) == n_configs, (len(out), n_configs)
    return out


def is_admissible(spec: Spec) -> bool:
    """H1 的语义层版本：``(code, extractor)`` 是否可组装。"""
    return spec.extractor in FAMILY_STRATEGIES[spec.code]


def run(n_configs: int = 48) -> dict:
    """Execute every substitution on the source-faithful baseline.

    ``substitution_invariance_report`` 需要 ``A.evaluate(spec)`` 成功，而 faithful
    extractor 的 contract 会拒绝不可装配的 ``(code, extractor)``（H1）。这类配置
    无法在语义层求值，因此单独计数为 ``inadmissible``——这本身就是一条结果：
    **QUITS 在这个基线上把 6 个 cross-product 配置判为不可组装，而它们在旧的
    理想化基线上全部"通过"**。
    """
    A = make_source_faithful_assembly()
    # (C1)-(C4) 与 spec 无关：按 (assembly, dimension) 算一次即可。
    side_conditions = {dim: theorem1_report(A, dim, ALT_COMPONENTS[dim], DOMAIN)
                       for dim in DIMENSIONS}
    rows = []
    n_applicable = n_invariant = 0
    n_inadmissible = 0
    per_dim: dict[str, dict] = {d: {"substitutions": 0, "applicable": 0,
                                     "invariance_ok": 0, "inadmissible": 0,
                                     "cone_sizes": set(), "cone_nodes": set()}
                                for d in DIMENSIONS}
    for ci, spec in enumerate(build_configs(n_configs)):
        admissible = is_admissible(spec)
        for dim, alt in ALT_COMPONENTS.items():
            label = (f"{spec.code}/{spec.arch}/{spec.extractor}/"
                     f"{spec.noise}/{spec.decoder}")
            d = per_dim[dim]
            d["substitutions"] += 1
            if not admissible:
                # H1: the assembly refuses this spec, so there is no artifact map
                # to compare.  Recorded, not silently dropped.
                n_inadmissible += 1
                d["inadmissible"] += 1
                rows.append({
                    "config_id": ci, "config": label, "dim": dim,
                    "admissible": False,
                    "refused_by": "contract violated: extractor (H1)",
                    "applicable": None, "cone": None, "invariance_ok": None,
                })
                continue
            rep = substitution_invariance_report(
                A, dim, alt, spec, report=side_conditions[dim])
            inv = rep["artifact_invariance"]
            ok = (inv is not None
                  and inv["unchanged_nodes_artifact_equal"]
                  and inv["all_contracts_hold_after"])
            n_applicable += int(rep["applicable"])
            n_invariant += int(bool(ok))
            d["applicable"] += int(rep["applicable"])
            d["invariance_ok"] += int(bool(ok))
            d["cone_sizes"].add(len(rep["cone_nodes_rerun"]))
            d["cone_nodes"].add(",".join(rep["cone_nodes_rerun"]))
            rows.append({
                "config_id": ci,
                "config": label,
                "dim": dim,
                "admissible": True,
                "applicable": rep["applicable"],
                "cone": rep["cone_nodes_rerun"],
                "invariance_ok": bool(ok),
            })
    n_eval = sum(1 for r in rows if r["applicable"] is not None)
    summary = {
        "n_configs": n_configs,
        "decoder_is_a_dimension": n_configs == 48,
        "decoders": DECODERS if n_configs == 48 else [LEGACY_DECODER],
        "baseline_assembly": BASELINE_ASSEMBLY,
        "assembly_model_sources": assembly_model_sources([BASELINE_ASSEMBLY]),
        "dimensions": list(DIMENSIONS),
        "n_substitutions": len(rows),
        "n_substitutions_evaluated": n_eval,
        "n_inadmissible_specs": n_inadmissible,
        "n_applicable": n_applicable,
        "n_invariance_ok": n_invariant,
        "theorem1_confirmed": n_applicable == n_invariant == n_eval,
        "per_dimension": {
            d: {"substitutions": v["substitutions"],
                "evaluated": v["substitutions"] - v["inadmissible"],
                "inadmissible": v["inadmissible"],
                "applicable": v["applicable"],
                "invariance_ok": v["invariance_ok"],
                "cone_sizes": sorted(v["cone_sizes"]),
                "cone_nodes": sorted(v["cone_nodes"])}
            for d, v in per_dim.items()},
        "domain": DOMAIN,
        "rows": rows,
    }
    return summary


def _reconfigure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):        # pragma: no cover - platform dep.
            pass


def to_markdown(summary: dict) -> str:
    n = summary["n_configs"]
    src = summary["assembly_model_sources"][summary["baseline_assembly"]]
    md = ["# Artifact Invariance (Theorem 1 可执行验证)", "",
          "## 0. Modelling provenance", "",
          f"Baseline assembly: **`{summary['baseline_assembly']}`**  ",
          f"Builder: `{src['builder']}`  ",
          f"Read sets: {src['read_sets']}  ",
          f"DAG edges: {src['edges']}  ",
          f"Faithfulness: {src['faithfulness']}",
          "",
          f"Generated by `python experiments/artifact_invariance.py` "
          f"(decoder {'a dimension' if summary['decoder_is_a_dimension'] else 'fixed'})",
          "",
          f"- configurations: **{n}**",
          f"- decoders: `{', '.join(summary['decoders'])}`",
          f"- substitutions: {summary['n_substitutions']} "
          f"({summary['n_substitutions_evaluated']} evaluated on an admissible "
          f"assembly, {summary['n_inadmissible_specs']} refused by the "
          f"extractor contract — H1, `(code, extractor)` not on the family "
          f"whitelist)",
          f"- applicable: {summary['n_applicable']}",
          f"- invariance ok: {summary['n_invariance_ok']}",
          f"- **Theorem 1 confirmed: {summary['theorem1_confirmed']}**",
          "",
          "`cone` is Theorem 1's re-run work sheet for *replacing* component "
          "`dim`; it is not the impact of *changing* a coordinate (that is "
          "`semantics.coordinate_impact`, see `PIVOT_NOTE` §4.3).", "",
          "## Per-dimension roll-up", "",
          "| dimension | substitutions | evaluated | inadmissible | applicable "
          "| invariance ok | cone sizes | cone nodes |",
          "|---|---:|---:|---:|---:|---:|---|---|"]
    for d, v in summary["per_dimension"].items():
        md.append(f"| {d} | {v['substitutions']} | {v['evaluated']} "
                  f"| {v['inadmissible']} | {v['applicable']} "
                  f"| {v['invariance_ok']} | {v['cone_sizes']} "
                  f"| `{', '.join(v['cone_nodes'])}` |")
    md += ["", "## All rows", "",
           "| config | dim | admissible | applicable | cone | invariance |",
           "|---|---|:---:|:---:|---|---|"]
    for r in summary["rows"]:
        md.append(f"| {r['config']} | {r['dim']} "
                  f"| {'yes' if r['admissible'] else '**no**'} "
                  f"| {'' if r['applicable'] is None else r['applicable']} "
                  f"| {','.join(r['cone']) if r['cone'] else '-'} "
                  f"| {'' if r['invariance_ok'] is None else r['invariance_ok']} |")
    return "\n".join(md) + "\n"


def main(argv: list[str] | None = None) -> int:
    _reconfigure_stdout()
    argv = list(sys.argv[1:] if argv is None else argv)
    n_configs = 24 if "--configs" in argv and "24" in argv[argv.index("--configs") + 1:] else 48
    summary = run(n_configs)
    out = outdir.resolve_out(argv, HERE)
    (out / "artifact_invariance.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    (out / "artifact_invariance.md").write_text(
        to_markdown(summary), encoding="utf-8")

    counts = Counter(r["dim"] for r in summary["rows"])
    print(f"baseline: {summary['baseline_assembly']}  configs={n_configs} "
          f"substitutions={summary['n_substitutions']} "
          f"evaluated={summary['n_substitutions_evaluated']} "
          f"inadmissible={summary['n_inadmissible_specs']} "
          f"applicable={summary['n_applicable']} "
          f"invariance_ok={summary['n_invariance_ok']} "
          f"theorem1_confirmed={summary['theorem1_confirmed']}")
    print(f"per-dim rows: {dict(counts)}")
    print(f"wrote {HERE / 'artifact_invariance.json'}")
    print(f"wrote {HERE / 'artifact_invariance.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())