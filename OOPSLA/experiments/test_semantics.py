"""Tests for src/semantics.py (OOPSLA pivot 第一版形式化核心)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_OOPSLA = _HERE.parent
sys.path.insert(0, str(_OOPSLA / "src"))
sys.path.insert(0, str(_OOPSLA))
sys.path.insert(0, str(_HERE))

import semantics  # noqa: E402
from semantics import (  # noqa: E402
    BASELINE_ASSEMBLY, COORDINATES, DOMAIN, DOMAIN_EXHAUSTIVE, FAMILY_STRATEGIES,
    QUITS_CALL_SITES, Assembly, Component, Spec, context_independence,
    detect_hidden_dependency, make_assembly, make_source_faithful_assembly,
    pointwise_equal_on_reads, signature_ok, substitute, theorem1_report,
)
from cone_table import (  # noqa: E402
    build_24_configs, build_assemblies, build_configs_all, config_to_spec,
    full_substitute, make_alt, run_all, summarize,
)


def test_spec_is_finite_product():
    s = Spec()
    for c in COORDINATES:
        assert hasattr(s, c)
    assert s.coords(("code", "noise")) == {"code": "BB", "noise": "SD6"}


def test_assembly_evaluate_and_contracts():
    A = make_assembly()
    art = A.evaluate(Spec())
    assert set(art) == set(A.nodes) | {"experiment"}
    assert all(A.nodes[n].contract(art[n]) for n in A.nodes)


def test_context_independence_pure_components():
    A = make_assembly()
    for n in ("code", "arch", "noise", "decoder", "extractor"):
        assert context_independence(A.nodes[n], DOMAIN), n


def test_hidden_dependency_detected_quits_style():
    A = make_assembly(with_quits_style=True)
    hid = detect_hidden_dependency(A.nodes["extractor"], DOMAIN)
    assert hid["verdict"] == "impure (hidden reads)"
    # Theorem 3: observed reads ⊄ declared ⇒ 非纯可被原则性探测
    assert "extractor" in hid["observed_extensions"]
    assert not hid["observed_reads_subset_declared"]


def test_theorem1_substitution_applicable():
    A = make_assembly()
    code_alt = Component("code", ("code",),
                         lambda s: {"kind": "code", "family": s.code},
                         contract=lambda a: a["kind"] == "code")
    v = substitute(A, "code", code_alt)
    assert v["checks"]["signature_ok"]
    assert v["applicable"]
    # cone(code) ⊂ nodes；其余节点 artifact 相同（Theorem 1 结论）
    assert v["cone_nodes_rerun"] == ["experiment"]
    assert set(v["provably_unchanged_nodes"]) >= {"arch", "noise", "decoder", "extractor"}
    assert A.cone("code") == {"experiment"}
    assert A.cone("experiment") == set()


def test_side_condition_pointwise_equality():
    A = make_assembly()
    code_node = A.nodes["code"]
    alt_same = Component("code", ("code",),
                         lambda s: {"kind": "code", "family": s.code})
    alt_diff = Component("code", ("code",),
                         lambda s: {"kind": "code", "family": s.code + "!"})
    assert pointwise_equal_on_reads(code_node, alt_same, DOMAIN)
    assert not pointwise_equal_on_reads(code_node, alt_diff, DOMAIN)
    assert signature_ok(code_node, alt_same)
    assert signature_ok(code_node, alt_diff)  # 参数契约一致，pointwise 分出其不等


# ---------------------------------------------------------------------------
# 2026-10-12 soundness fixes：第二轮独立审稿（research/novelty-audit-2026-10-10
# §3）的三个反例转为回归测试。
# ---------------------------------------------------------------------------

def _audit_counterexample_assembly() -> Assembly:
    """审稿反例（audit §3.2）：code -> decoder -> sink。

    decoder 声明 reads=("decoder",)，通过前驱 artifact 间接读 code：
    旧实现在所有 spec 下返回前驱产物；新实现在 BB 下相同、HGP 下返回
    CHANGED。两个实现都满足"直接读集与前驱产物固定时输出相等"，因此
    旧 checkter 在只枚举 R(x) + 默认值补全的探测下会漏查 code 经由
    前驱 artifact 对 decoder 的影响，报告 applicable=True 并把 decoder
    列入 provably_unchanged——而 Spec(code="HGP") 下 decoder 真的变。
    """
    code = Component("code", ("code",), lambda s, inp: s.code)
    old = Component("decoder", ("decoder",), lambda s, inp: inp["code"])
    new = Component("decoder", ("decoder",),
                    lambda s, inp: inp["code"] if inp["code"] == "BB" else "CHANGED")
    sink = Component("sink", (), lambda s, inp: inp["decoder"])
    return Assembly({"code": code, "decoder": old, "sink": sink},
                    {"code": (), "decoder": ("code",), "sink": ("decoder",)})


_AUDIT_DOMAIN = {"code": ["BB", "HGP"], "extractor": ["cardinal"],
                 "arch": ["free"], "noise": ["SD6"], "decoder": ["BP-OSD"]}


def test_c4_audits_every_full_spec_with_real_predecessor_inputs():
    """反例 1 回归（audit §3.2）：C4 必须遍历完整有限 Spec 域，并在每一点
    用**实际前驱 artifact**（不是默认值补全的 Spec）比较 x 与 x'。

    旧实现的 pointwise_equal_on_reads 只枚举 R(x)、其余坐标取 Spec 默认值、
    前驱输入从补全后的 spec 计算——code 产物因此从未参与 C4，checker 对
    实际求值中会变的 decoder 报告 provably_unchanged（soundness 反例）。
    """
    A = _audit_counterexample_assembly()
    new = Component("decoder", ("decoder",),
                    lambda s, inp: inp["code"] if inp["code"] == "BB" else "CHANGED")
    report = theorem1_report(A, "decoder", new, _AUDIT_DOMAIN)
    # (C4) 必须在完整域 + 实际前驱输入上失败……
    assert report["checks"]["pointwise_equal_on_reads"] is False
    assert report["applicable"] is False
    # ……并且 checker 不得把会变的节点报告为不变
    assert "decoder" not in report["provably_unchanged_nodes"]
    # 见证：替换在 Spec(code="HGP") 下确实改变 decoder（与 sink）
    A2 = Assembly({**A.nodes, "decoder": new}, A.edges)
    spec = Spec(code="HGP")
    assert A.evaluate(spec)["decoder"] != A2.evaluate(spec)["decoder"]


def test_substituted_node_x_never_in_provably_unchanged():
    """反例 2 回归（audit §3.1）：cone(x) 不含 x 自身（无环时），C4 未通过
    时被替换节点 x 的 artifact 可能变。checker 工作表的正确不变域是
    N ∖ ({x} ∪ cone(x))，无论 applicable 与否都不能把 x 报成不变。
    """
    A = make_assembly()
    alt_diff = Component("code", ("code",),
                         lambda s, inp: {"kind": "code", "family": s.code + "!"})
    refused = substitute(A, "code", alt_diff)
    assert refused["checks"]["pointwise_equal_on_reads"] is False
    assert refused["applicable"] is False
    # (C4) 失败：x 自己的 artifact 会变，绝不能出现在不变工作表里
    assert "code" not in refused["provably_unchanged_nodes"]

    alt_same = Component("code", ("code",),
                         lambda s, inp: {"kind": "code", "family": s.code})
    accepted = substitute(A, "code", alt_same)
    assert accepted["applicable"]
    # 工作表保守地排除 x（x 的不变由 (C4) 单独给出，见 PIVOT_NOTE §6.1 Step 1）；
    # {x} ∪ cone(x) ∪ provably_unchanged 恰好划分 N
    assert "code" not in accepted["provably_unchanged_nodes"]
    assert ({"code"} | set(accepted["cone_nodes_rerun"])
            | set(accepted["provably_unchanged_nodes"])) == set(A.nodes)


def test_lemma2_converse_is_invalid_local_underdeclaration_is_not_global():
    """反例 3 回归（audit §3.3）：¬P ⇒ ¬Q 不是 Lemma 2（P ⇒ Q）的逆否；
    真正的逆否是 ¬Q ⇒ ¬P。

    反例：组件 a 声明空读集却读 code（非纯，Theorem 3 可检出）；组件 b
    正确声明读 code。全部声明读集的并集已覆盖两个组件实际读取的坐标，
    因此**任意**在全部声明坐标上一致的 spec 仍给出相同 artifact 映射——
    一个组件的局部漏读推不出"声明式 spec 整体不足以决定产物"。
    """
    a = Component("a", (), lambda s, inp: f"a:{s.code}")     # 漏声明 code
    b = Component("b", ("code",), lambda s, inp: f"b:{s.code}")
    A = Assembly({"a": a, "b": b}, {"a": (), "b": ()})
    # 局部事实成立：a 非纯且探测器报出漏读的正是 code（Theorem 3）
    hid = detect_hidden_dependency(a, _AUDIT_DOMAIN)
    assert hid["verdict"] == "impure (hidden reads)"
    assert hid["observed_extensions"] == ["code"]
    assert context_independence(b, _AUDIT_DOMAIN)
    # 但整体性质 Q 也成立：不存在"在全部声明坐标上一致而 artifact 映射不同"
    # 的 spec 对——旧稿的"逆否"（¬P ⇒ ¬Q）在此不成立
    import itertools
    keys = sorted(_AUDIT_DOMAIN)
    envs = [Spec(**dict(zip(keys, combo)))
            for combo in itertools.product(*(_AUDIT_DOMAIN[k] for k in keys))]
    declared_union = set(a.reads) | set(b.reads)
    for s in envs:
        art_s = A.evaluate(s)
        for t in envs:
            agrees = all(getattr(s, k) == getattr(t, k) for k in declared_union)
            if agrees:
                assert A.evaluate(t) == art_s, (s, t)



    A2 = make_assembly(with_quits_style=True)
    clean = Component("extractor", ("code", "extractor"),
                      lambda s: f"{s.extractor}@{s.code}")
    v = substitute(A2, "extractor", clean)
    # impure 节点替换：不主张 cone 外不变（trigger-2 probe 的可执行形式）
    assert v["checks"]["signature_ok"] is False or v["applicable"] is False


def test_p04_greedy_extension_finds_minimal_hidden_reads():
    """P0-4：读了两个未声明坐标的组件也能被贪心最小扩展捕获。"""
    two_hidden = Component("two_hidden", ("code",),
                           lambda s, inp: f"{s.code}/{s.extractor}/{s.noise}")
    hid = detect_hidden_dependency(two_hidden, DOMAIN)
    assert hid["verdict"] == "impure (hidden reads)"
    assert set(hid["observed_extensions"]) == {"extractor", "noise"}


def test_p02_artifact_invariance_executed():
    """P0-2：替换实际执行后，cone 外 artifact 逐点相同、contract 保持。"""
    from semantics import substitution_invariance_report
    A = make_assembly()
    alt = Component("code", ("code",),
                    lambda s, inp: {"family": s.code, "kind": "code"},
                    contract=lambda a: a["kind"] == "code")
    rep = substitution_invariance_report(A, "code", alt, Spec())
    assert rep["applicable"]
    inv = rep["artifact_invariance"]
    assert inv["unchanged_nodes_artifact_equal"]
    assert inv["all_contracts_hold_after"]
    # cone 内节点（experiment）重跑后 artifact 仍满足 contract
    assert "experiment" in inv["cone_nodes_before_after"]


def test_quits_call_sites_table():
    assert len(QUITS_CALL_SITES) == 5
    for row in QUITS_CALL_SITES:
        assert row["model_checkable"] is True
        assert row["semantic_check"]
        assert row["site"]


# ---------------------------------------------------------------------------
# cone_table 关键断言（PIVOT_NOTE §5 下一步 (1)(4)）
# ---------------------------------------------------------------------------

def test_cone_table_24_configs_instantiable():
    """24 configs from C0 corpus all instantiate as valid Specs (3x2x2x2)."""
    configs = build_24_configs()
    assert len(configs) == 24
    corpus_families = {"BB", "HGP", "QLP"}  # C0 corpus families
    for c in configs:
        spec = config_to_spec(c)
        assert spec.code in corpus_families
        assert spec.extractor in DOMAIN["extractor"]
        assert spec.arch in DOMAIN["arch"]
        assert spec.noise in DOMAIN["noise"]
        assert spec.decoder == "BP-OSD"


def test_cone_table_cross_product_shape():
    """24 = 3 codes x 2 archs x 2 extractors x 2 noises; each value appears equally."""
    configs = build_24_configs()
    from collections import Counter
    for field, n_expected in (("code", 3), ("arch", 2), ("extractor", 2), ("noise", 2)):
        vals = Counter(config_to_spec(c).__dict__[field] for c in configs)
        assert len(vals) == n_expected, field
        assert all(v == 24 // n_expected for v in vals.values()), field


def test_cone_table_pure_substitutions_applicable():
    """Clean assembly: all 24x5 substitutions applicable, bounded cones."""
    configs = build_24_configs()
    A = make_assembly()
    for c in configs:
        for dim in COORDINATES:
            alt = make_alt(dim, A.nodes[dim])
            r = full_substitute(A, dim, alt)
            assert r["applicable"], (c, dim, r["checks"])
            assert len(r["cone_nodes_rerun"]) == 1          # cone = {experiment}
            # 不变工作表 = N ∖ ({x} ∪ cone(x))：7 节点 − 1 cone − x 自身
            assert len(r["provably_unchanged_nodes"]) == 5  # all other nodes unchanged
            assert dim not in r["provably_unchanged_nodes"]


def test_cone_table_quits_faithful_extractor_unbounded():
    """QUITS-faithful assembly: extractor substitutions unbounded (H1)."""
    configs = build_24_configs()
    A = make_assembly(with_quits_style=True)
    for c in configs:
        alt = make_alt("extractor", A.nodes["extractor"])
        r = full_substitute(A, "extractor", alt)
        assert not r["applicable"]
        assert not r["checks"]["x_context_independent"]


def test_cone_table_quits_dataflow_noise_cone():
    """Dataflow-faithful assembly: noise cone = 3 (extractor+decoder+experiment)."""
    configs = build_24_configs()
    assemblies = build_assemblies()
    A = assemblies["quits_dataflow"]
    # H3: noise baked into circuit → extractor & decoder both in cone(noise)
    assert A.cone("noise") == {"extractor", "decoder", "experiment"}
    # 决策 3（2026-10-09）：`arch <- code` 边已补上。此前 `cone(code)` 漏掉
    # `arch`，被 dynamic_impact 实测（换 code 会改 layout_positions）判为缺口。
    assert A.cone("code") == {"extractor", "arch", "decoder", "experiment"}
    assert A.cone("arch") == {"decoder", "experiment"}
    # All substitutions still applicable (components are pure)
    for c in configs:
        for dim in COORDINATES:
            alt = make_alt(dim, A.nodes[dim])
            r = full_substitute(A, dim, alt)
            assert r["applicable"], (dim, r["checks"])


def test_cone_table_source_faithful_is_the_baseline():
    """决策 2：发布基线是 ``source_faithful``，它的 cone 由源码推导。"""
    from cone_table import ASSEMBLY_NAMES
    assemblies = build_assemblies()
    assert BASELINE_ASSEMBLY == "source_faithful"
    assert "source_faithful" in ASSEMBLY_NAMES
    A = assemblies["source_faithful"]
    assert A.cone("code") == {"extractor", "arch", "decoder", "experiment"}
    assert A.cone("extractor") == {"decoder", "experiment"}
    assert A.cone("arch") == {"experiment"}
    # H3 在这份基线上的形式是 coordinate impact，不是 cone（§4.3）
    assert semantics.coordinate_impact(A, "noise") == {
        "noise", "extractor", "decoder", "experiment"}
    assert "extractor" not in A.cone("noise")
    for dim in COORDINATES:
        alt = make_alt(dim, A.nodes[dim])
        r = full_substitute(A, dim, alt)
        assert r["applicable"], (dim, r["checks"])
        assert r["cone_covers_every_node"] is False


def test_cone_table_48_configs_cover_the_decoder_dimension():
    """决策 4 的语料：48 配置（decoder 成一维），与 artifact_invariance 对齐。"""
    assert len(build_configs_all()) == 48
    specs = [config_to_spec(c) for c in build_configs_all()]
    assert {s.decoder for s in specs} == {"BP-OSD", "BP-LSD"}
    assert len(set(s.decoder for s in specs)) == 2


def test_cone_table_scripts_run_and_stamp_the_baseline(tmp_path):
    """脚本端到端可跑，并把 baseline / 建模来源写进 JSON 与 Markdown。

    ``--out tmp_path``：测试绝不能覆写已发布产物（§3.4-D）——quick/24 配置
    跑出来的对象与发布的全量对象不是同一个。
    """
    import json
    import cone_table
    assert cone_table.main(["--out", str(tmp_path)]) == 0
    blob = json.loads((tmp_path / "cone_table.json")
                      .read_text(encoding="utf-8"))
    m = blob["metadata"]
    assert m["baseline_assembly"] == "source_faithful"
    assert set(m["assembly_model_sources"]) >= {
        "clean", "quits_faithful", "quits_dataflow", "source_faithful",
        "_baseline"}
    assert m["assembly_model_sources"]["source_faithful"]["baseline"] is True
    assert m["decoder_is_a_dimension"] is True
    assert blob["summary"]["trigger2_risk"]["baseline_assembly"] == \
        "source_faithful"
    md = (tmp_path / "cone_table.md").read_text(encoding="utf-8")
    assert "Modelling provenance" in md
    assert "source_faithful" in md


def test_cone_table_script_can_reproduce_the_24_config_corpus(tmp_path):
    import json
    import cone_table
    # the legacy corpus is reproducible, but it is NOT the published artifact:
    # it must never land in the checked-in output directory
    assert cone_table.main(["--configs", "24", "--out", str(tmp_path)]) == 0
    blob = json.loads((tmp_path / "cone_table.json")
                      .read_text(encoding="utf-8"))
    assert blob["metadata"]["n_configs"] == 24
    assert blob["metadata"]["decoder_is_a_dimension"] is False
    assert blob["summary"]["trigger2_risk"]["verdict"] in {
        "bounded", "localized", "unbounded"}
    assert not (cone_table.HERE / "cone_table_24.json").exists()
    # the published 48-config artifact is untouched by this test
    assert (cone_table.HERE / "cone_table.json").exists()


def test_cone_table_summary_trigger2():
    """决策 4：trigger-2 在 ``source_faithful`` 基线上重算。

    - 基线上 **0 unbounded** ⇒ verdict ``bounded``，PLAN §9 trigger 2 未命中；
    - 对照列：``clean`` / ``quits_dataflow`` 同样 0；
    - ``quits_faithful``（手工构造的 H1 不纯反例）在 extractor 维度上
      全部 unbounded——这解释了上一轮为什么会得到 "localized"。
    """
    configs = build_configs_all()
    assemblies = build_assemblies()
    rows = run_all(assemblies, configs)
    summary = summarize(rows, BASELINE_ASSEMBLY)
    for asm in ("clean", "quits_dataflow", "source_faithful"):
        assert summary[asm]["unbounded"] == 0, asm
        assert summary[asm]["applicable"] == summary[asm]["total"], asm
    assert summary["quits_faithful"]["unbounded"] == len(configs)
    for dim in COORDINATES:
        ub = summary["quits_faithful"]["by_dimension"][dim]["unbounded"]
        assert ub == (len(configs) if dim == "extractor" else 0), dim
    t2 = summary["trigger2_risk"]
    assert t2["baseline_assembly"] == "source_faithful"
    assert t2["unbounded_in_baseline"] == 0
    assert t2["verdict"] == "bounded"
    # 基线上的 unbounded 分布逐维度为 0
    for dim in COORDINATES:
        assert summary[BASELINE_ASSEMBLY]["by_dimension"][dim]["unbounded"] == 0


def test_cone_table_summary_verdict_encodes_trigger2():
    """verdict 的三档口径必须与 PLAN §9 trigger 2 对齐。

    ``bounded``  = 没有 unbounded；``localized`` = 部分 unbounded（局部化）；
    ``unbounded`` = 全部 unbounded ⇒ 定理退化为"所有组件都要重验证" ⇒ 止损。
    """
    assemblies = build_assemblies()
    configs = build_24_configs()
    rows = run_all(assemblies, configs)
    base = "source_faithful"
    others = [r for r in rows if r["assembly"] != base]

    # (1) partial failure -> localized: every dimension except `decoder` fails
    partial = ([dict(r, applicable=False) for r in rows
                if r["assembly"] == base and r["dimension"] != "decoder"]
               + [r for r in rows
                  if r["assembly"] == base and r["dimension"] == "decoder"])
    assert summarize(partial + others)["trigger2_risk"]["verdict"] == "localized"
    # (2) total failure -> unbounded: Theorem 1 degenerates to "re-verify all"
    total = [dict(r, applicable=False) for r in rows if r["assembly"] == base]
    assert summarize(total + others)["trigger2_risk"]["verdict"] == "unbounded"
    # (3) the real table -> bounded
    assert summarize(rows)["trigger2_risk"]["verdict"] == "bounded"


# ---------------------------------------------------------------------------
# P1-4: cone 在含环 DAG 上的语义（定义 + 终止性 + 与 Theorem 1 的关系）
# ---------------------------------------------------------------------------

def _trivial_nodes(names) -> dict:
    return {n: Component(n, ("code",), lambda s, inp: s.code) for n in names}


def _cyclic_assembly() -> Assembly:
    """含环 assembly：`c` 依赖 `b`，`b` 依赖 `c`；`d` 依赖 `c`。

    edges[u] = u **依赖**谁，因此依赖方向是 b → c → b（2-环）。
    c3 这一支再串一个 3-环，用来检查 BFS 在环下不会指数膨胀。
    """
    nodes = _trivial_nodes(("a", "b", "c", "d", "c2", "c3"))
    edges = {
        "a": (),
        "b": ("a", "c"),      # b 依赖 a 与 c；c 依赖 b ⇒ 2-环 {b, c}
        "c": ("b",),
        "d": ("c",),
        "c2": ("c",),
        "c3": ("c2",),
    }
    return Assembly(nodes=nodes, edges=edges)


def test_cyclic_assembly_is_detected_not_dag():
    """含环 assembly：is_dag()=False，环上节点恰为 {b, c}。"""
    A = _cyclic_assembly()
    assert A.cycles() == {"b", "c"}
    assert not A.is_dag()
    # 无环对照
    assert make_assembly().is_dag()
    assert make_assembly().cycles() == set()


def test_cone_on_cyclic_assembly_terminates_and_is_correct():
    """含环 DAG 上 cone 必然终止且给出正确的最小传递闭包。

    edges[u] = u **依赖**谁：
        a 无依赖；b 依赖 a 与 c；c 依赖 b（⇒ 2-环 {b, c}）；d / c2 依赖 c；
        c3 依赖 c2。
    """
    A = _cyclic_assembly()
    # a 在环外：cone(a) = 所有传递依赖 a 的节点，不含自身
    assert A.cone("a") == {"b", "c", "d", "c2", "c3"}
    assert "a" not in A.cone("a")
    # b、c 在环上：环上闭合 ⇒ 自身也进入 cone
    assert A.cone("b") == {"b", "c", "d", "c2", "c3"}
    assert A.cone("c") == {"b", "c", "d", "c2", "c3"}
    # c2 在环外但依赖 c：cone(c2) 不含自身
    assert A.cone("c2") == {"c3"}
    # d 是叶子：cone(d) 为空
    assert A.cone("d") == set()
    # 关键性质：x ∈ cone(x) 当且仅当 x 在环上
    for x in A.nodes:
        assert (x in A.cone(x)) == (x in A.cycles()), x


def test_cone_on_cycle_terminates_everywhere():
    """所有起点上 cone 都必须终止（不指数膨胀、不死循环）。"""
    A = _cyclic_assembly()
    for target in A.nodes:
        cone = A.cone(target)              # 必须终止
        assert isinstance(cone, set)
        assert cone <= set(A.nodes)
    # 幂等/闭包性质：cone(cone(x)) ⊆ cone(x) ∪ {x}
    for x in A.nodes:
        cone = A.cone(x)
        union = set().union(*(A.cone(y) for y in cone)) if cone else set()
        assert union <= cone | {x}, x


def test_evaluate_refuses_cyclic_assembly():
    """⟦A⟧ 按拓扑序定义；环下 evaluate 明确拒绝而不是给出任意结果。"""
    A = _cyclic_assembly()
    with pytest.raises(ValueError, match="cycle"):
        A.evaluate(Spec())


def test_theorem1_refuses_cyclic_assembly_but_still_reports_cone():
    """环下 checker 保守拒绝（assembly_is_dag=False），但仍报出 cone。"""
    A = _cyclic_assembly()
    alt = Component("a", ("code",), lambda s, inp: s.code)
    v = substitute(A, "a", alt)
    assert v["checks"]["assembly_is_dag"] is False
    assert v["applicable"] is False
    assert v["cone_nodes_rerun"] == ["b", "c", "c2", "c3", "d"]  # sorted(cone)
    assert sorted(v["cycles"]) == ["b", "c"]


def test_acyclic_assembly_passes_dag_side_condition():
    """无环 assembly 上 assembly_is_dag=True，既有结论不变。"""
    A = make_assembly()
    alt = Component("code", ("code",), lambda s, inp: {"kind": "code", "family": s.code})
    v = substitute(A, "code", alt)
    assert v["checks"]["assembly_is_dag"] is True
    assert v["applicable"]


# ---------------------------------------------------------------------------
# P2-3: Domain 的 extractor 维度覆盖 QUITS 源码支持的全部策略
# ---------------------------------------------------------------------------

def test_extractor_domain_covers_source_union():
    """DOMAIN['extractor'] ⊇ 各 family supported_strategies 的并集（源码自动解析）。"""
    from quant_evidence import extractor_domain_from_source
    src = set(extractor_domain_from_source())
    assert src, "failed to parse whitelists from the pinned tree"
    assert src <= set(DOMAIN["extractor"]), sorted(src - set(DOMAIN["extractor"]))
    # 关键：不能少于 QUITS 白名单并集的大小
    assert len(DOMAIN["extractor"]) >= 5


def test_context_independence_verdicts_stable_on_widened_domain():
    """P2-3：extractor 维度从 2 扩到 5 后，纯/不纯判定不变。"""
    narrow = dict(DOMAIN, extractor=["cardinal", "zxcoloration"])
    A, Aq = make_assembly(), make_assembly(with_quits_style=True)
    for name in ("code", "arch", "noise", "decoder", "extractor"):
        assert context_independence(A.nodes[name], DOMAIN) is True
        assert context_independence(A.nodes[name], narrow) is True
    # QUITS 风格 extractor 在两个域上都必须被判为不纯（Theorem 3）
    for dom in (DOMAIN, narrow):
        hid = detect_hidden_dependency(Aq.nodes["extractor"], dom)
        assert hid["verdict"] == "impure (hidden reads)"
        assert "extractor" in hid["observed_extensions"]


def test_domain_exhaustiveness_flags_declared():
    """每个坐标都必须显式标注穷举性（PIVOT_NOTE §6.3 枚举完备性）。"""
    assert set(DOMAIN_EXHAUSTIVE) == set(DOMAIN)
    assert DOMAIN_EXHAUSTIVE["code"] and DOMAIN_EXHAUSTIVE["extractor"]
    assert not DOMAIN_EXHAUSTIVE["arch"]        # 刻意欠近似，已标注
    assert not DOMAIN_EXHAUSTIVE["noise"]
    assert not DOMAIN_EXHAUSTIVE["decoder"]


# ---------------------------------------------------------------------------
# P2-4: 24 → 48 配置（decoder 成为一维）
# ---------------------------------------------------------------------------

def test_artifact_invariance_48_configs_with_decoder_dimension():
    """48 = 3×2×2×2×2；decoder 参与 cross-product。

    决策 2 之后基线是 ``source_faithful``，所以两件事变了：
    (a) 240 次替换里有 40 次的 spec **不可装配**（``BB + cardinal`` 不在
    ``BbCode.supported_strategies`` 上，H1），它们被单独计入 ``inadmissible``
    而不是混进 applicable；(b) cone 不再是单点。见 PIVOT_NOTE §11。
    """
    from artifact_invariance import DECODERS, run
    s = run(48)
    assert s["n_configs"] == 48
    assert s["decoder_is_a_dimension"]
    assert s["decoders"] == DECODERS
    assert s["baseline_assembly"] == BASELINE_ASSEMBLY == "source_faithful"
    assert s["n_substitutions"] == 48 * len(COORDINATES)
    # BB + cardinal is on 8 of the 48 configs x 5 dimensions = 40 refusals
    assert s["n_inadmissible_specs"] == 40
    assert s["n_substitutions_evaluated"] == s["n_substitutions"] - 40
    assert s["n_applicable"] == s["n_substitutions_evaluated"]
    assert s["n_invariance_ok"] == s["n_substitutions_evaluated"]
    assert s["theorem1_confirmed"]
    for dim, v in s["per_dimension"].items():
        assert v["substitutions"] == 48, dim
        assert v["inadmissible"] == 8, dim
        assert v["invariance_ok"] == 40, dim


def test_artifact_invariance_cone_is_no_longer_a_single_point():
    """源码 faithful 基线上 cone 由源码推导，不再恒为 ``{experiment}``。

    这条是决策 2 的**实质变化**：在旧的理想化基线上每个 cone 都是 1 个节点，
    artifact 不变性因此是平凡成立的。
    """
    from artifact_invariance import run
    s = run(48)
    per = s["per_dimension"]
    assert per["code"]["cone_nodes"] == ["arch,decoder,experiment,extractor"]
    assert per["extractor"]["cone_nodes"] == ["decoder,experiment"]
    for dim in ("arch", "noise", "decoder"):
        assert per[dim]["cone_nodes"] == ["experiment"], dim
    # 每个维度都至少有一个 cone 外的节点（否则 Theorem 1 退化成"全部重验"）
    A = make_source_faithful_assembly()
    for dim in COORDINATES:
        assert A.cone(dim), dim
        assert A.cone(dim) < set(A.nodes), dim


def test_faithful_baseline_and_alternatives_agree():
    """``artifact_invariance`` 的 alt 必须与 faithful baseline 逐点相等 (C4)。

    alt 用一张**独立抄写**的白名单/参数表；如果这两张表漂移，Theorem 1 的
    side condition (C4) 会失败——而这正是 (C4) 在可执行 checker 里的作用。
    """
    import artifact_invariance as ai
    A = make_source_faithful_assembly()
    for dim in COORDINATES:
        orig = A.nodes[dim]
        alt = ai.ALT_COMPONENTS[dim]
        assert orig.reads == alt.reads, dim
        for spec in (Spec(code="HGP", extractor="cardinal", arch="grid2d"),
                     Spec(code="mitten", extractor="hook_error_free",
                          arch="free", noise="SI1000", decoder="BP-LSD")):
            inputs = {d: A.evaluate(spec, check_contracts=False)[d]
                      for d in A.dependencies(dim)}
            from semantics import _call_produce
            assert (_call_produce(orig, spec, inputs)
                    == _call_produce(alt, spec, inputs)), (dim, spec)
    assert ai._CODE_SIZES == semantics.CODE_FAMILY_DATA_QUBITS
    assert {k: tuple(v) for k, v in ai._ALT_WHITELISTS.items()} == FAMILY_STRATEGIES


def test_artifact_invariance_legacy_24_configs_still_reproducible():
    """旧的 24 配置口径（decoder 固定 BP-OSD）仍可复现。"""
    from artifact_invariance import LEGACY_DECODER, run
    s = run(24)
    assert s["n_configs"] == 24
    assert not s["decoder_is_a_dimension"]
    assert s["decoders"] == [LEGACY_DECODER]
    assert s["n_substitutions"] == 24 * len(COORDINATES)
    assert s["theorem1_confirmed"]
    assert {r["config"].rsplit("/", 1)[1] for r in s["rows"]} == {LEGACY_DECODER}
    # 24 = 3x2x2x2：BB+cardinal 出现在 4 个配置上 x 5 维 = 20 次拒绝
    assert s["n_inadmissible_specs"] == 20
    assert s["n_invariance_ok"] == s["n_substitutions"] - 20


# ---------------------------------------------------------------------------
# P1-2 / P2-2: 定量证据脚本
# ---------------------------------------------------------------------------

def test_quant_evidence_h1_h2_h3_verdicts():
    from quant_evidence import h1_evidence, h2_evidence, h3_evidence
    h1, h2, h3 = h1_evidence(), h2_evidence(), h3_evidence()
    # H1：白名单彼此不一致
    assert h1["n_concrete_families"] >= 6
    assert h1["n_distinct_whitelists"] >= 2
    assert h1["n_inconsistent_family_pairs"] > 0
    assert h1["verdict_supported"]
    assert h1["global_registry_keys"]            # _BUILDERS 已解析
    # 至少有 1 个策略被某族白名单接受却不在全局 registry 中
    assert h1["n_strategies_whitelisted_without_registry_entry"] >= 1
    # H2：decoder/ 零抽象接口，layout/ 有
    assert h2["decoder_package"]["n_abstract_classes"] == 0
    assert h2["decoder_package"]["n_protocol_classes"] == 0
    assert h2["layout_package"]["n_abstract_classes"] >= 1
    assert h2["implicit_decoder_interface"]["required_attributes"] == ["decode"]
    assert h2["verdict_supported"]
    # H3：每个定义 build_circuit 的文件都依赖 noise
    assert h3["n_distinct_files_defining_build_circuit"] >= 5
    assert h3["n_files_depending_on_noise_any_channel"] == \
        h3["n_distinct_files_defining_build_circuit"]
    assert h3["verdict_supported"]


def test_quant_evidence_call_sites_verified():
    """P2-2：五条 QUITS_CALL_SITES 至少三条自动验证（此处要求全部静态可验）。"""
    from quant_evidence import verify_call_sites
    sites = verify_call_sites()
    assert len(sites) == len(QUITS_CALL_SITES) == 5
    assert sum(1 for s in sites if s["verified"]) >= 3
    for s in sites:
        assert s["static_check"]["ok"] is True, s["dimension"]
    dims = {s["dimension"] for s in sites}
    assert dims == {row["dimension"] for row in QUITS_CALL_SITES}
    # 每条都有可陈述的 runtime 探测（即使环境里跑不了也必须记录原因）
    for s in sites:
        assert s["runtime_check"]["status"] in {"ok", "unavailable", "mismatch"}


def test_quant_evidence_script_runs_and_emits_artifacts(tmp_path):
    """脚本端到端可跑，并落盘 quant_evidence.json / .md。

    ``--out tmp_path`` keeps the published artifact byte-identical: this
    script's output depends on which ``quits`` is imported, and a test run must
    never be able to republish it (``SUBMISSION_READINESS.md`` §3.4-D).
    """
    import json
    import quant_evidence
    data = quant_evidence.collect()
    assert data["summary"]["H1_verdict"]
    assert data["summary"]["H2_verdict"]
    assert data["summary"]["H3_verdict"]
    assert data["summary"]["domain_covers_source_union"]
    assert data["summary"]["all_call_sites_verified"]
    out = quant_evidence.main(["--out", str(tmp_path)])
    assert out == 0
    for name in ("quant_evidence.json", "quant_evidence.md"):
        p = tmp_path / name
        assert p.is_file() and p.stat().st_size > 0, name
    blob = json.loads((tmp_path / "quant_evidence.json")
                      .read_text(encoding="utf-8"))
    assert blob["metadata"]["quits_commit"] == quant_evidence.QUITS_COMMIT


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
