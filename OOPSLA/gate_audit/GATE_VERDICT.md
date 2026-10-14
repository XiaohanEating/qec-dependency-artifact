# GATE VERDICT — QUITS Boundary Audit (executed change tasks)

Date: 2026-10-08 (5/5 维度实测完成于 2026-10-09).
Pinned tree: `third_party/quits-0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452`
(baseline commit `586ebf81f3d4153ee685a2cb4768f25fb2959a90`).

## Executed change tasks (real git measurements)

| 维度 | change_task | 新增文件 | 触碰包 (actual) | LOC changed (git diff --stat) |
|---|---|---|---|---|
| Noise | add SI1000-style parameterized noise model (`SI1000ErrorModel`, subclass of `ErrorModel`) | `src/quits/noise/si1000.py` (+43) | `noise` (1 包) | 45 insertions, 1 deletion → `est_loc = 46` |
| Decoder | add standalone replaceable BP-LSD decoder (`StandaloneBpLsdDecoder` over `ldpc.bplsd_decoder`) | `src/quits/decoder/bplsd_standalone.py` (+51) | `decoder` (1 包) | 53 insertions → `est_loc = 53` |
| Code | add a new code family (`ToyFamilyCode`: Z checks full-rank, X checks = leading rows of the GF(2) nullspace basis of the Z checks, so `hz@hxᵀ ≡ 0 mod 2` by construction, `k ≥ 1`) | `src/quits/qldpc_code/toy_family.py` (+43) | `qldpc_code` (1 包) | 45 insertions, 1 deletion → `est_loc = 46` |
| Extraction | add a new syndrome-extraction strategy (`ToyStrategyBuilder`, `name='toy'`, a pass-through delegating to the zx-coloration builder, registered in `_BUILDERS`) | `src/quits/qldpc_code/circuit_construction/toy_strategy.py` (+34) | `qldpc_code` (1 包) | 37 insertions → `est_loc = 37` |
| Architecture | add a new qubit topology/layout constraint (`ToyGridLayout`: rectangular integer-grid `Layout` whose `mapping()` covers every data/zcheck/xcheck index) | `src/quits/layout/toy_grid.py` (+55) | `layout` (1 包) | 57 insertions → `est_loc = 57` |

**五个维度的标准变更任务全部实际执行并测量**（2026-10-09 补齐 Code /
Extraction / Architecture；测量口径 `git add -N <new files>; git diff --stat`，
按文件集归属到维度）。三个后补任务在同一个工作树上实现，因此它们的数字是对
同一个 diff 的划分：46 + 37 + 57 = 140 = 139 insertions + 1 deletion。

每个任务都验证了**可用性**而不只是可编译：

| 维度 | 执行期验证 |
|---|---|
| Code | `ToyFamilyCode().build_circuit(strategy='zxcoloration')` 成功产出 stim circuit；`verify_css_logicals()` 为 True |
| Extraction | `get_builder('toy', code)` 解析到 `ToyStrategyBuilder`；`code.build_circuit(strategy='toy')` 经 registry 分派成功 |
| Architecture | `issubclass(ToyGridLayout, Layout)` 为 True；`mapping()` 返回覆盖全部 qubit 索引的 `LayoutMapping` |

五个任务均未触碰 `simulation/`、`api.py`、`circuit.py` 等装配层；任务被限制在
单个源码包内部，LOC 量级 < 60。

## Gate 判定 (protocol.md rubric)

rubric：若 ≥70% 维度的任务其预估修改面与"直接在 QUITS 里改"无实质差别
（即 QUITS 已预留同等扩展点）→ kill。5 个维度，≥70% 即 ≥4 个。

- **5/5 维度全部实测**（2026-10-09 补齐 Code / Extraction / Architecture 后）：
  每个标准变更任务都只新增 1 个模块 + 1–3 行注册/导出，且**新增即可用**
  （不改装配层、不改任何既有组件），即修改面 == 直接在 QUITS 内改。
- 逐维度实测修改面：Noise 1 包 / 46 LOC，Decoder 1 包 / 53 LOC，
  Code 1 包 / 46 LOC，Extraction 1 包 / 37 LOC，Architecture 1 包 / 57 LOC。
  静态预估（`touched_packages_est`）对 code / extraction / decoder 三维
  **高估**了触碰面（列入了 `circuit` / `simulation` 包）；实测全部是 1 包。
- 结论：5/5 维度 QUITS 已预留等价扩展点（阈值 ≥4/5 满足，实测比例 100%）
  → **kill criterion triggered：不需要在 QUITS 之上另建一层同构抽象层**。
  任何新抽象都应只包装 QUITS 的 ErrorModel / decoder / layout / code family
  注册点，而非重新定义它们。

## 复原状态

`git reset --hard 586ebf8` 已完成；`git status` 干净，工作树回到 baseline
（两批 change task 的新增模块 —— `si1000.py` / `bplsd_standalone.py` 与
`toy_family.py` / `toy_strategy.py` / `toy_grid.py` —— 已全部移除，
五个 `__init__.py` 已还原）。
`python -c "import quits"` 冒烟通过。

## 附注

- `audit_results.json` 已回填 `change_task`、`est_loc`（真实值）、
  `touched_packages_actual`、`loc_detail`，并新增 `executed_change_tasks`
  一节汇总 5/5 实测。
- 五个维度的标准变更任务全部实际执行（2026-10-09 补齐后三个维度）；
  本文档中不再有静态预估替代实测的维度。
