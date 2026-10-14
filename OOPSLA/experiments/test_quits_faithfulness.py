"""Tests for the two AST/execution-driven QUITS-faithfulness checks.

* ``extract_read_sets``  -- PAPER_GAP_ANALYSIS **P0-3** (Gap 1.7 / 1.8):
  the component read sets ``R(c)`` must be *derived* from the pinned QUITS
  source, and the hand-declared model must be diffed against the derivation.
* ``dynamic_impact``     -- PAPER_GAP_ANALYSIS **P2-2** dynamic half (Gap 2.4):
  the five call-site claims must survive an actual substitution measured on
  the running QUITS object.

Everything here is *self-checking against the source*: if the pinned QUITS
tree changes in a way that invalidates ``semantics.READ_SETS_FROM_SOURCE``,
``semantics.ARTIFACT_READS_FROM_SOURCE`` or ``semantics.FAMILY_STRATEGIES``,
these tests fail.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_OOPSLA = _HERE.parent
for _p in (str(_OOPSLA / "src"), str(_OOPSLA), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import semantics  # noqa: E402
from semantics import (  # noqa: E402
    ARTIFACT_READS_FROM_SOURCE, ASSEMBLY_EDGES_FROM_SOURCE, COORDINATES,
    DOMAIN, FAMILY_STRATEGIES, READ_SETS_FROM_SOURCE, Spec,
    admissible_spec, context_independence_with_inputs,
    coordinate_impact, detect_hidden_dependency, inadmissible_pairs,
    make_source_faithful_assembly, predecessor_inputs,
)

extract_read_sets = pytest.importorskip(
    "extract_read_sets",
    reason="AST read-set extractor (needs the pinned QUITS tree)")


# ---------------------------------------------------------------------------
# extractor: the expected read sets of the known QUITS components
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def extraction() -> dict:
    return extract_read_sets.extract_read_sets()


@pytest.fixture(scope="module")
def diff_report(extraction) -> dict:
    return extract_read_sets.build_diff(extraction)


def test_extractor_finds_every_dimension(extraction):
    """每个维度都必须有锚点被定位到（否则 R(c) 是空的而没人发现）。"""
    for d in COORDINATES:
        assert extraction["read_sets"][d]["anchors"], d
        assert extraction["read_sets"][d]["reads"], d


def test_extracted_read_sets_match_semantics_tables(extraction):
    """`semantics.READ_SETS_FROM_SOURCE` 必须逐条等于自动提取的结果。"""
    for d in COORDINATES:
        assert set(extraction["read_sets"][d]["reads"]) == set(
            READ_SETS_FROM_SOURCE[d]), (d, extraction["read_sets"][d]["reads"])


def test_extracted_artifact_reads_match_semantics_tables(extraction):
    """`ARTIFACT_READS_FROM_SOURCE` 也必须由源码提取，而不是手工断言。"""
    for d in COORDINATES:
        assert set(extraction["read_sets"][d]["artifact_reads"]) == set(
            ARTIFACT_READS_FROM_SOURCE[d]), (
            d, extraction["read_sets"][d]["artifact_reads"])


def test_code_reads_only_its_own_coordinate(extraction):
    """BB/HGP/QLP ... 的 ``__init__`` 只读自己的坐标（family 的构造参数）。"""
    assert set(extraction["read_sets"]["code"]["reads"]) == {"code"}


def test_extractor_reads_noise_coordinate(extraction):
    """H3 的核心：``build_circuit`` 的 ``error_model`` 参数就是 noise 坐标。"""
    rs = extraction["read_sets"]["extractor"]
    assert set(rs["reads"]) == {"code", "extractor", "noise"}
    noise_evidence = rs["evidence"]["noise"]
    assert noise_evidence, "no evidence recorded for the noise read"
    assert any("error_model" in s for s in noise_evidence), noise_evidence
    assert all(s.startswith("qldpc_code/") for s in noise_evidence)


def test_extractor_reads_code_coordinate_via_supported_strategies(extraction):
    """H1 的机制：extractor 读 code 族的 ``supported_strategies`` 类属性。"""
    sites = extraction["read_sets"]["extractor"]["evidence"]["code"]
    assert any(".supported_strategies" in s for s in sites), sites


def test_arch_and_decoder_depend_on_code_as_artifacts_not_coordinates(
        extraction):
    """``Layout(code)`` / ``get_codecap_pL(code, ...)`` 是 **artifact 边**。

    把它们折进 R(c) 就是 P0-1 之前的 arity-1 特例；两者必须分开。
    """
    arch = extraction["read_sets"]["arch"]
    decoder = extraction["read_sets"]["decoder"]
    assert set(arch["reads"]) == {"arch"}
    assert "code" in arch["artifact_reads"]
    assert set(decoder["reads"]) == {"decoder"}
    assert {"code", "extractor"} <= set(decoder["artifact_reads"])


def test_noise_reads_only_its_own_coordinate(extraction):
    assert set(extraction["read_sets"]["noise"]["reads"]) == {"noise"}


def test_extractor_records_evidence_for_every_read(extraction):
    """每一次坐标读都必须带 file:line 证据（否则报告不可审计）。"""
    for d in COORDINATES:
        rs = extraction["read_sets"][d]
        for coord in rs["reads"]:
            assert rs["evidence"].get(coord), (d, coord)
            for site in rs["evidence"][coord]:
                assert ":" in site and site.startswith(("qldpc_code/", "layout/",
                                                       "noise/", "decoder/",
                                                       "simulation.py")), site


def test_ambiguous_names_are_dropped_not_guessed(extraction):
    """歧义名必须被丢弃并记录，而不是随便归到一个维度。"""
    amb = extraction["ambiguous_names_dropped"]
    assert isinstance(amb, dict) and amb
    vocabs = extraction["vocabularies"]
    for name, owners in amb.items():
        assert len(owners) >= extract_read_sets.AMBIGUITY_THRESHOLD
        for owner in owners:
            assert name not in vocabs[owner]["names"]
            assert name not in vocabs[owner]["state"]


def test_hand_vs_auto_diff_reports_exactly_one_missing_coordinate(diff_report):
    """自动提取与手工建模的差异必须是**已知的**那一条，且被记录下来。

    唯一的手工漏项是 ``extractor`` 少了 ``noise``；``arch`` / ``decoder`` 在
    R(c) 上一致（它们的依赖是 artifact 边）。
    """
    rows = diff_report["rows"]
    assert diff_report["n_hand_disagreements"] == 1
    r = rows["extractor"]["vs_hand_declared"]
    assert r["verdict"] == "manual_under_approximates"
    assert r["in_auto_not_manual"] == ["noise"]
    for d in ("code", "arch", "noise", "decoder"):
        assert rows[d]["vs_hand_declared"]["agrees"], d


def test_diff_records_the_notes_for_each_disagreement(diff_report):
    """差异的成因必须写在 ``semantics.READ_SETS_FROM_SOURCE_NOTES`` 里。"""
    for d in COORDINATES:
        assert d in semantics.READ_SETS_FROM_SOURCE_NOTES, d


# ---------------------------------------------------------------------------
# extractor: the corrected model in semantics.py
# ---------------------------------------------------------------------------

def test_family_strategies_match_the_source_whitelists():
    """``FAMILY_STRATEGIES`` 必须等于 QUITS 的 ``supported_strategies``。"""
    from quant_evidence import supported_strategies_by_class
    by_class = {w["class"]: sorted(w["strategies"])
                for w in supported_strategies_by_class()}
    assert FAMILY_STRATEGIES["BB"] == tuple(by_class["BbCode"])
    assert FAMILY_STRATEGIES["HGP"] == tuple(by_class["HgpCode"])
    assert FAMILY_STRATEGIES["QLP"] == tuple(by_class["QlpCode"])
    assert FAMILY_STRATEGIES["mitten"] == tuple(by_class["MittenCode"])
    assert FAMILY_STRATEGIES["BPC"] == tuple(by_class["BpcCode"])
    assert FAMILY_STRATEGIES["LCS"] == tuple(by_class["LcsCode"])


def test_faithful_assembly_edges_are_derived_from_artifact_reads():
    """DAG 边 = artifact 读集合去掉自环。"""
    for d in COORDINATES:
        expected = tuple(sorted(set(ARTIFACT_READS_FROM_SOURCE[d]) - {d}))
        assert tuple(sorted(ASSEMBLY_EDGES_FROM_SOURCE[d])) == expected, d
    assert ASSEMBLY_EDGES_FROM_SOURCE["extractor"] == ("code",)
    assert ASSEMBLY_EDGES_FROM_SOURCE["arch"] == ("code",)
    assert ASSEMBLY_EDGES_FROM_SOURCE["decoder"] == ("code", "extractor")


def test_faithful_components_are_pure_under_the_general_model():
    """一般模型的 Definition：R(c) 一致 + 前驱 artifact 一致 ⇒ 输出相同。

    这里 ``arch`` / ``decoder`` 的 produce 读的是 ``inp[...]``（artifact），
    arity-1 探测会把它们误报成 impure；传 ``inputs_for`` 才正确。
    """
    A = make_source_faithful_assembly()
    assert A.is_dag()
    for name, c in A.nodes.items():
        if name == "experiment":
            continue
        inputs = predecessor_inputs(A, name)
        assert context_independence_with_inputs(c, DOMAIN, inputs), name
        assert detect_hidden_dependency(c, DOMAIN, inputs)["verdict"] == "pure", name


def test_faithful_cone_and_coordinate_impact():
    """cone（替换组件）与 coordinate_impact（改坐标）是两个不同的集合。"""
    A = make_source_faithful_assembly()
    # replacing the *code component*: everything downstream of the code artifact
    assert A.cone("code") == {"arch", "extractor", "decoder", "experiment"}
    assert A.cone("extractor") == {"decoder", "experiment"}
    assert A.cone("arch") == {"experiment"}
    assert A.cone("noise") == {"experiment"}
    # changing the *noise coordinate* additionally reaches every reader of the
    # coordinate (the extractor) and then the extractor's cone.
    assert coordinate_impact(A, "noise") == {"noise", "extractor", "decoder",
                                              "experiment"}
    assert coordinate_impact(A, "code") == {"code", "arch", "extractor",
                                            "decoder", "experiment"}
    assert coordinate_impact(A, "extractor") == {"extractor", "decoder",
                                                  "experiment"}


def test_coordinate_impact_is_a_fixpoint_under_cone_closure():
    A = make_source_faithful_assembly()
    for c in COORDINATES:
        impact = coordinate_impact(A, c)
        assert c in impact
        for v in impact:
            assert A.cone(v) <= impact, (c, v)


def test_faithful_extractor_contract_refuses_inadmissible_pairs():
    """H1：不可装配的 (code, extractor) 由 contract 拒绝，而不是运行期异常。"""
    A = make_source_faithful_assembly()
    bad = inadmissible_pairs()
    assert ("BB", "cardinal") in bad
    assert ("BB", "zxcoloration") not in bad
    for code, strategy in bad[:5]:
        with pytest.raises(ValueError, match="contract violated: extractor"):
            A.evaluate(Spec(code=code, extractor=strategy))
    # an admissible pair assembles
    A.evaluate(Spec(code="BB", extractor="custom"))
    A.evaluate(admissible_spec())


def test_idealised_assembly_is_documented_as_such():
    """`_mk_components` 是理想化对照基线，不是 QUITS-faithful 模型。

    决策 2（2026-10-09）之后它不再是 ``cone_table`` / ``artifact_invariance``
    的基线——那两张表的数字挂在 ``source_faithful`` 上。
    """
    clean = semantics.make_assembly()
    assert all(clean.dependencies(n) == ()
               for n in clean.nodes if n != "experiment")
    faithful = make_source_faithful_assembly()
    assert faithful.dependencies("arch") == ("code",)


def test_assembly_model_sources_are_recorded_and_unique():
    """每个 assembly 的读集合 / 边的来源都必须写死，且只有一个是基线。

    决策 2/3 的可执行护栏：如果有人换了某个 assembly 的构造方式却没更新
    provenance，实验产出的数字就可能被读成来自另一个建模。
    """
    src = semantics.assembly_model_sources()
    assert set(src) == {"clean", "quits_faithful", "quits_dataflow",
                        "source_faithful", "_baseline"}
    assert src["_baseline"] == semantics.BASELINE_ASSEMBLY == "source_faithful"
    baselines = [k for k, v in src.items()
                 if k != "_baseline" and v["baseline"]]
    assert baselines == ["source_faithful"]
    for name, info in src.items():
        if name == "_baseline":
            continue
        assert info["builder"], name
        assert info["read_sets"], name
        assert info["edges"], name
        assert info["faithfulness"], name
    # the recorded source of each assembly must actually be its constructor
    assert "make_assembly()" in src["clean"]["builder"]
    assert "with_quits_style" in src["quits_faithful"]["builder"]
    assert "make_quits_dataflow_assembly" in src["quits_dataflow"]["builder"]
    assert "make_source_faithful_assembly" in src["source_faithful"]["builder"]
    assert "extract_read_sets" in src["source_faithful"]["read_sets"]
    assert "ASSEMBLY_EDGES_FROM_SOURCE" in src["source_faithful"]["edges"]


def test_assembly_model_sources_are_stamped_into_every_experiment(tmp_path):
    """决策 2 的第二条要求：每个实验产物都要能自证数字的建模来源。

    ``--out tmp_path`` keeps the published artifacts byte-identical: this
    test must never overwrite the checked-in JSON/MD (§3.4-D).
    """
    import json
    import cone_table
    import artifact_invariance
    import quant_evidence

    assert cone_table.main(["--out", str(tmp_path)]) == 0
    cone = json.loads((tmp_path / "cone_table.json")
                      .read_text(encoding="utf-8"))
    assert cone["metadata"]["baseline_assembly"] == "source_faithful"
    assert "source_faithful" in cone["metadata"]["assembly_model_sources"]

    inv = artifact_invariance.run(48)
    assert inv["baseline_assembly"] == "source_faithful"
    assert inv["assembly_model_sources"]["_baseline"] == "source_faithful"
    md = artifact_invariance.to_markdown(inv)
    assert "Modelling provenance" in md
    assert "source_faithful" in md

    assert quant_evidence.main(["--out", str(tmp_path)]) == 0
    quant = json.loads((tmp_path / "quant_evidence.json")
                       .read_text(encoding="utf-8"))
    prov = quant["metadata"]["fed_into_assembly"]
    assert prov["published_baseline_assembly"] == "source_faithful"
    for key in ("H1", "H2", "H3"):
        assert prov[key], key
    qmd = (tmp_path / "quant_evidence.md").read_text(encoding="utf-8")
    assert "source_faithful" in qmd


def test_dynamic_impact_declares_itself_the_ground_truth():
    """决策 1：本实验是 ground truth，静态提取器是交叉验证。

    叙事定位写在产物里，而不是只写在论文里。
    """
    impact = pytest.importorskip("dynamic_impact",
                                 reason="needs the quits runtime")
    prov = impact._assembly_provenance()
    assert set(prov["compared_models"]) == {
        "source_faithful_cone", "source_faithful_coord", "dataflow_cone"}
    for info in prov["compared_models"].values():
        assert info["read_sets_from"], info
        assert info["edges_from"], info
        assert info["question"], info
    assert "ground truth" in prov["note"]
    assert "cross-validation" in prov["note"]
    data = impact.run(quick=True)
    md = impact.to_markdown(data)
    assert "ground truth" in md
    assert "cross-validation" in md
    assert "source_faithful" in md


# ---------------------------------------------------------------------------
# dynamic impact: five real substitutions on the running QUITS object
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def impact() -> dict:
    dyn = pytest.importorskip(
        "dynamic_impact",
        reason="dynamic substitution experiment (needs the quits runtime)")
    return dyn.run(quick=True)


def test_dynamic_impact_covers_all_five_dimensions(impact):
    dims = {r["dimension"] for r in impact["substitutions"]
            if not r.get("refused")}
    assert dims == set(COORDINATES), dims


def test_dynamic_impact_measures_modules_and_artifacts(impact):
    """每个替换都必须给出 (a) 触达的 quits 模块和 (b) artifact 指纹。"""
    base = impact["baseline_artifacts"]
    assert set(base) == set(semantics_constants := {
        "code_matrices", "layout_positions", "noise_model", "stim_circuit",
        "detector_error_model", "logical_observables", "decoder_output"})
    for a in base.values():
        assert a["fingerprint"]
    assert len(impact["baseline_stages"]) >= 5
    modules = {m for st in impact["baseline_stages"].values()
               for m in st["modules"]}
    assert any(m.startswith("quits.qldpc_code") for m in modules), modules
    assert any(m.startswith("quits.decoder") for m in modules), modules
    for r in impact["substitutions"]:
        if r.get("refused"):
            continue
        assert r["n_quits_modules_after"] >= 1
        assert r["quits_modules_executed_after"]


def test_h3_noise_substitution_is_not_circuit_preserving(impact):
    """H3：只改 noise 坐标，stim circuit 与 DEM 必须变（extractor 的产物）。"""
    row = next(r for r in impact["substitutions"]
               if r["dimension"] == "noise" and not r.get("refused"))
    assert "stim_circuit" in row["changed_artifacts"]
    assert "detector_error_model" in row["changed_artifacts"]
    assert row["collateral_nodes"] == sorted(["decoder", "extractor"])
    assert row["changed_nodes"] == sorted(["decoder", "extractor", "noise"])


def test_h1_inadmissible_substitution_is_refused(impact):
    """H1：全局 registry 有、但不在族白名单里的策略无法装配。"""
    probe = impact["inadmissible_probe"]
    assert probe["outcome"] == "refused"
    assert probe["exception"] == "NotImplementedError"
    assert "cardinal" not in probe["family_whitelist"]
    assert "cardinal" in probe["global_whitelist"]
    assert probe["semantic_layer_refuses_same_pair"] is True
    refused = [r for r in impact["substitutions"] if r.get("refused")]
    assert refused and refused[0]["exception"] == "NotImplementedError"


def test_architecture_substitution_is_circuit_preserving(impact):
    """arch 替换只改 layout 产物：extractor 自己建 TransversalLayout。"""
    row = next(r for r in impact["substitutions"]
               if r["name"] == "arch" and not r.get("refused"))
    assert row["changed_artifacts"] == ["layout_positions"]
    assert row["collateral_nodes"] == []


def test_decoder_substitution_is_local(impact):
    """decoder 替换只改 decoder 产物（SD6 名义点上两个解码器一致）。"""
    row = next(r for r in impact["substitutions"]
               if r["name"] == "decoder" and not r.get("refused"))
    assert row["changed_nodes"] == []
    assert row["collateral_nodes"] == []
    stress = next(r for r in impact["substitutions"]
                  if r["name"] == "decoder_stress" and not r.get("refused"))
    assert stress["changed_artifacts"] == ["decoder_output"]
    assert stress["collateral_nodes"] == []


def test_code_substitution_changes_every_downstream_artifact(impact):
    row = next(r for r in impact["substitutions"]
               if r["dimension"] == "code" and not r.get("refused"))
    assert set(row["changed_artifacts"]) == {
        "code_matrices", "layout_positions", "stim_circuit",
        "detector_error_model", "logical_observables", "decoder_output"}
    assert row["collateral_nodes"] == ["arch", "decoder", "extractor"]


def test_coordinate_impact_covers_every_measurement(impact):
    """`coordinate_impact` 必须覆盖每一组实测影响面（这是 soundness）。"""
    assert impact["summary"]["coordinate_impact_covers_measurement_all"] is True
    for r in impact["substitutions"]:
        if r.get("refused"):
            continue
        assert r["prediction_covers_measurement"]["source_faithful_coord"], r["name"]


def test_component_substitution_cone_is_a_different_question(impact):
    """Theorem 1 的 cone 回答的是"替换组件"，不能用来预测"改坐标"。

    这是本实验明确记录的一个**建模区分**，而不是 bug：改 noise 坐标会改变
    extractor 的产物，但 cone(noise) 里没有 extractor。
    """
    assert impact["summary"]["theorem1_cone_covers_measurement_all"] is False
    cones = impact["cones"]
    assert "noise" in cones["source_faithful_cone"]
    assert "extractor" not in cones["source_faithful_cone"]["noise"]
    assert "extractor" in cones["source_faithful_coord"]["noise"]


def test_dataflow_assembly_no_longer_under_approximates(impact):
    """决策 3：`arch <- code` 边补上后，dataflow cone 覆盖全部实测影响面。

    在补这条边之前，``code`` 那一行的 cone 漏掉 ``arch``（实测换 code 会改
    ``layout_positions``），``dataflow_cone_covers_measurement_all`` 是 False。
    """
    assert impact["summary"]["dataflow_cone_covers_measurement_all"] is True
    row = next(r for r in impact["substitutions"]
               if r["dimension"] == "code" and not r.get("refused"))
    assert "arch" in row["predicted_nodes_to_rerun"]["dataflow_cone"]
    assert row["prediction_covers_measurement"]["dataflow_cone"] is True


def test_decoder_stress_probe_is_not_flaky(impact):
    """`decoder_stress` 用更多 shots，使两个解码器在每个 hash seed 下都分歧。

    16 shots 时某些 circuit（circuit 文本本身依赖 ``PYTHONHASHSEED``）会让两个
    解码器在所有采样上一致，使这条断言变成 flaky。128 shots 下我们测过的每个
    hash seed 都分歧。
    """
    stress = next(r for r in impact["substitutions"]
                  if r["name"] == "decoder_stress" and not r.get("refused"))
    assert stress["changed_artifacts"] == ["decoder_output"]
    assert stress["collateral_nodes"] == []
    assert stress["shots"] >= 128


def test_call_site_alignment_is_reported_for_every_dimension(impact):
    aligned = {a["dimension"] for a in impact["call_site_alignment"]}
    assert aligned == set(COORDINATES)
    for a in impact["call_site_alignment"]:
        assert a["site"]
        assert a["static_modelling"]
        assert isinstance(a["aligned"], bool)
        assert a["notes"]


def test_stim_circuit_is_not_stable_under_hash_randomisation(impact):
    """可复现性发现：``edge_coloration`` 依赖 set 迭代顺序。

    这条不影响本实验的结论（同一进程内的 before/after 比较仍然有效），但它
    意味着 stim circuit **不是**一个稳定的 artifact，必须记在 artifact 文档里。
    """
    probe = impact["hash_seed_probe"]
    assert probe["n_distinct"] >= 2
    assert probe["deterministic"] is False


def test_installed_wheel_and_pinned_snapshot_measure_the_same_thing():
    """`--source both`：site-packages 的 quits 1.2.0 与 pinned 快照测出同一结果。

    `shared/VERSIONS.md` 说两者同版本；这条测试把这个说法变成可执行的证据。
    （较慢：会在子进程里把整个实验重跑一遍。）
    """
    dyn = pytest.importorskip("dynamic_impact",
                              reason="needs the quits runtime + pinned tree")
    # Both sides must run in a child interpreter with the same
    # PYTHONHASHSEED (see dynamic_impact.probe_hash_seed_sensitivity).
    installed = dyn._run_in_child(pinned=False, quick=True)
    pinned = dyn._run_in_child(pinned=True, quick=True)
    if installed is None or pinned is None:         # pragma: no cover
        pytest.skip("the quits runtime or the pinned tree is unavailable here")
    report = dyn._cross_source_report(installed, pinned)
    assert report["pinned_available"] is True
    assert report["pinned_quits_version"] == dyn.INSTALLED_VERSION
    assert report["all_baseline_fingerprints_agree"], report
    assert report["all_same_changed_artifacts"], report
    assert all(report["summaries_agree"].values()), report
    assert not (dyn.HERE / "_dynamic_impact_pinned.json").exists()
    assert not (dyn.HERE / "_dynamic_impact_installed.json").exists()


def test_dynamic_impact_script_runs_and_emits_artifacts(tmp_path):
    """脚本端到端可跑，并落盘 dynamic_impact.json / .md。

    ``--out tmp_path`` keeps the published artifact byte-identical (§3.4-D).
    """
    import json
    import dynamic_impact
    assert dynamic_impact.main(["--quick", "--out", str(tmp_path)]) == 0
    for name in ("dynamic_impact.json", "dynamic_impact.md"):
        p = tmp_path / name
        assert p.is_file() and p.stat().st_size > 0, name
    assert not (dynamic_impact.HERE / "_dynamic_impact_pinned.json").exists()
    blob = json.loads((tmp_path / "dynamic_impact.json")
                      .read_text(encoding="utf-8"))
    assert blob["metadata"]["pinned_commit"] == dynamic_impact.QUITS_COMMIT
    assert blob["summary"]["h3_noise_not_circuit_preserving"] is True
    assert blob["summary"]["h1_extractor_inadmissible_detected"] is True
    assert blob["metadata"]["role"].startswith("ground truth")


def test_read_sets_script_runs_and_emits_artifacts(tmp_path):
    import json
    out = extract_read_sets.main(["--out", str(tmp_path)])
    assert out == 0
    for name in ("read_sets.json", "read_sets.md"):
        p = tmp_path / name
        assert p.is_file() and p.stat().st_size > 0, name
    blob = json.loads((tmp_path / "read_sets.json")
                      .read_text(encoding="utf-8"))
    assert blob["metadata"]["quits_commit"] == extract_read_sets.QUITS_COMMIT
    assert blob["summary"]["n_hand_disagreements"] == 1
    assert blob["summary"]["auto_read_sets"]["extractor"] == [
        "code", "extractor", "noise"]
    # 决策 1：提取器自称交叉验证，ground truth 是动态实验
    assert blob["role"]["status"] == "cross-validation"
    assert "dynamic_impact" in blob["role"]["ground_truth"]
    assert blob["role"]["published_baseline_assembly"] == "source_faithful"
    md = (tmp_path / "read_sets.md").read_text(encoding="utf-8")
    assert "cross-validation, not ground truth" in md
    assert "source_faithful" in md


def test_read_sets_report_labels_the_published_baseline(diff_report):
    """差异报告必须标出哪一列是发布基线（决策 1/2）。"""
    for d in COORDINATES:
        assert diff_report["rows"][d]["is_published_baseline"] is True, d


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))