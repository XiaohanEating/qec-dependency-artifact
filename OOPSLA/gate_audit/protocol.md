# QUITS Boundary Audit — Measurement Protocol (pre-registered)

按 OOPSLA PLAN §2/§5：本协议在测量开始前冻结，测量由脚本自动完成，不允许人工认定。
基线 QUITS 锁定于 commit `0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452`（third_party/）。

## 变更任务定义（每维度一个标准任务）

| 维度 | 标准变更任务 |
|---|---|
| Code | 新增一个 code family（如新 BB 多项式族或新 lift-product 结构），使其可被 build_circuit 使用 |
| Extraction | 新增一种 syndrome-extraction circuit strategy |
| Architecture | 新增一种 qubit 拓扑/布局约束（如 2D grid 邻接限制） |
| Noise | 新增一种 noise model（如 SI1000 变体） |
| Decoder | 新增一种 decoder 接入（如 BP-LSD 作为独立可替换项） |

## 组件粒度（预注册，不可再调）

QUITS 侧组件边界 = 源码模块包：`qldpc_code/*`（Code、Extraction）、`layout`（Architecture）、
`noise`（Noise）、`decoder`（Decoder）、`simulation/api`（装配层）。
"我们的抽象"侧组件边界 = PLAN §4 的五个 spec 组件 + Experiment 装配层（六组件）。

## 指标定义

- **修改组件数**：被任务触碰的模块包数（git-diff 按包边界归类；本审查阶段用静态归属表）。
- **LOC changed**：任务完成后 `git diff --stat` 的净变更行数（新增文件计全部行数）。
- **reuse ratio**：零 diff 模块包数 / 模块包总数。
- **CL(x)** = 修改组件数 / 总组件数。

## QUITS 侧静态审查（gate 数据，先于任何开发）

对每个维度：给出"在 QUITS 中完成任务所需触碰的模块包清单"及预估 LOC 量级
（通过阅读源码：抽象基类要求实现的成员数、注册点数量、类型耦合点数量）。
**Gate 判定**：若五维度中 ≥70% 的任务其预估修改面与"直接在 QUITS 里改"无实质差别
（即 QUITS 已预留同等的扩展点），则触发 OOPSLA kill criterion。

## 输出

`audit_results.json`：每维度 {touched_packages, est_loc, abstract_members_required,
registry_points} + gate verdict。
