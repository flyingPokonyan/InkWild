# 评测报告 · rubric=npc · 判官=admin_generation

对比 condition：baseline vs new

| 维度 | baseline | new | Δ |
|---|---|---|---|
| agency | 4.1 | 4.16 | +0.06 |
| in_character | 4.25 | 4.25 | +0.0 |
| info_isolation | 4.48 | 4.3 | -0.18 |
| no_meta | 5.0 | 4.98 | -0.02 |
| reactivity | 4.16 | 4.39 | +0.23 |
| voice_distinct | 4.06 | 4.24 | +0.18 |
| **overall** | 4.23 | 4.25 | +0.02 |

## 故障 / flag
| condition | 局数 | 判官flag | 硬检 |
|---|---|---|---|
| baseline | 3 | 0 | 无 |
| new | 3 | 1 | 无 |

> 注：判官绝对分有压缩/偏差，**信 Δ 不信绝对值**。Δ 为正=后者比前者好。