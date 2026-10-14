# 本轮中位成本（毫秒）

同进程重复样本，预热一次，原始全部样本见validation.json。

| 项目 | normal-reverse | lower-rotate | stress-shuffle | qecc-reverse |
|---|---:|---:|---:|---:|
| parse_and_lossless_fold | 15.8165 | 15.8982 | 16.1020 | 68.2437 |
| producer_artifact_and_evidence | 0.3425 | 0.3563 | 0.3796 | 1.0897 |
| independent_relation_check | 0.4336 | 0.4483 | 0.5308 | 1.4918 |
| ordinary_full_boundary_relation_and_input | 0.5286 | 0.5168 | 0.5886 | 1.8531 |
| proposed_relation_and_input | 0.5066 | 0.5184 | 0.5490 | 2.1832 |
| two_consumer_frontend_and_evidence_generation | 0.5155 | 0.3156 | 0.2843 | 1.0013 |
| two_consumer_source_and_proof_checks | 2.0131 | 1.9034 | 2.0897 | 6.1838 |
| canonical_native_full_execution | 36.9914 | 34.8315 | 31.2006 | 未执行 |

首次解析、首次证据物化、首次native执行逐配置保存在JSON；上述parse为重复解析成本。源码前端检查包含重检生产者/输入的成本；缓存比较不能替代首次stamp生成。
