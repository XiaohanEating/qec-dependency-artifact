# VERSIONS — 三轨道共享的版本锁定文档

三条线（ISCAS / OOPSLA / ESOP）的所有实验必须在下列锁定版本上进行，
任何升级需先在此文档留痕并重新跑 baseline replay。

## Python 环境

- 环境名：`qldpc`（conda，Anaconda `envs/qldpc`）
- Python：3.11.17

## 关键包（来自 `pip list` 2026-10-08 快照）

| 包 | 版本 | 备注 |
|---|---|---|
| qldpc | 0.4.1 | code 构造、Stim circuit utilities |
| quits | 1.2.0 | site-packages 安装；与 `third_party/quits-0f36b8c...` 同为 1.2.0，以 third_party 源码为对照基准 |
| stim | 1.16.0 | circuit / DEM / tableau 模拟 |
| ldpc | 2.4.1 | BP-OSD / BP-LSD 解码器（`bposd_decoder`、`bplsd_decoder`） |
| sinter | 1.16.0 | 并行化采样/解码实验 |
| qecc_routing | commit 4ef18121c39492414b85ff36b3a61c83f9ebf95f | 源码快照在 `third_party/`，非 pip 包；脚本位于 `src_py/`，按需加入 `sys.path` |
| numpy / scipy | 2.4.6 / 1.17.1 | |
| galois | 0.4.11 | qecc_routing 依赖 |

## third_party 快照

| 快照 | commit | 用途 |
|---|---|---|
| quits-0f36b8c5... | 0f36b8c5a9b81d6b7be0cef2c81c61b5850c0452 | baseline B1 对照、OOPSLA gate audit 对照组 |
| qecc_routing-4ef18121... | 4ef18121c39492414b85ff36b3a61c83f9ebf95f | baseline B2（BB 2D-local greedy routing） |

## 验证状态（2026-10-08）

- [x] `smoke_codes.py` — BB-144 / HGP / Stim sampler OK
- [x] `smoke_quits.py` — QUITS zxcoloration circuit on BB(12,12)，720 detectors / 576 qubits
- [x] `smoke_decode3.py` — quits sliding-window BP-OSD end-to-end decode OK
- [x] `c0_corpus.py` — 5 个 C0 实例生成，写入 `shared/C0/corpus.json`

## 已知缺口

- qecc_routing 的 Stim/C++ 编译产物未在 Windows 环境构建；B2 baseline replay 前需先在该快照上验证 `src_py` 脚本可跑（依赖 `src_cpp` 时退而求其次：记录为"论文引用实现，未本地复现"）。
- `bposdv`/PyMatching 等备选解码器未在 C0 主线使用；如接入，更新本表。
