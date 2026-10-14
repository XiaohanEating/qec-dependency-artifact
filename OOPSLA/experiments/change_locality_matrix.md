# Change Locality Matrix (预对比)

## 0. 每列的数字来自哪里

| 列 | 建模来源 |
|---|---|
| `quits.cl` | pre-registered static attribution from gate_audit/audit_results.json (not measured) |
| `hand_written.cl` | assumption: the monolith is touched in full |
| `ours.cl` | abstraction.measure_cl over the pre-registered 6-component inventory (DSL track; design-time count, independent of any source-derived read set) |
| `semantic.cl` | size of cone(x) divided by the node count on the `source_faithful` assembly; read sets auto-extracted from the pinned QUITS tree by experiments/extract_read_sets.py (READ_SETS_FROM_SOURCE) |
| `semantic_coordinate_impact.cl` | same assembly, but the impact of *changing* a coordinate (PIVOT_NOTE section 4.3) — this, not the cone, is what a QUITS user asks |

发布基线 assembly：**`source_faithful`**
（读集合：auto-extracted from the pinned QUITS tree by experiments/extract_read_sets.py (READ_SETS_FROM_SOURCE)；边：auto-derived: ARTIFACT_READS_FROM_SOURCE minus self-loops (ASSEMBLY_EDGES_FROM_SOURCE): extractor <- code, arch <- code, decoder <- (code, extractor)）

两个 ours 的区别是**建模不同**而不是数字冲突：`ours.cl` 是设计期计数（DSL 轨道的 6 组件清单），`semantic.cl` 是 checker 从源码自动提取的读集合算出来的重跑工作表。本表是**预对比**；不主张「我们比 QUITS 更局部」（`gate_audit` 已证伪，见 `PIVOT_NOTE` §8.6 第 5 条）。

| 变更场景 | QUITS CL | hand-written CL | ours CL (设计期) | semantic CL (cone) | semantic CL (改坐标) |
|---|---|---|---|---|---|
| code | 0.333 | 1.0 | 0.167 | 0.667 | 0.833 |
| extraction | 0.333 | 1.0 | 0.167 | 0.333 | 0.500 |
| architecture | 0.167 | 1.0 | 0.167 | 0.167 | 0.333 |
| noise | 0.167 | 1.0 | 0.167 | 0.167 | 0.667 |
| decoder | 0.333 | 1.0 | 0.167 | 0.167 | 0.333 |

`semantic CL (cone)` = 替换该组件需要重跑的比例（Theorem 1）；`semantic CL (改坐标)` = 改该坐标的影响面。两者在 `noise` 上不同：改 noise 会连带改 extractor 的产物，而 `cone(noise)` 里没有 extractor（`PIVOT_NOTE` §4.3）。

