# 评测报告 · rubric=ip_fidelity · 判官=admin_generation

对比 condition：base_S5 vs new_goal vs boundary vs hp

| 维度 | base_S5 | new_goal | boundary | hp |
|---|---|---|---|---|
| character_fidelity | 4.87 | 4.45 | 4.8 | 3.17 |
| etiquette_titles | 4.93 | 4.9 | 4.67 | 3.22 |
| language_register | 4.93 | 4.75 | 4.87 | 3.06 |
| plot_motif | 4.67 | 4.6 | 4.47 | 2.72 |
| relationships | 4.73 | 4.6 | 4.73 | 3.28 |
| world_canon | 5.0 | 4.95 | 4.8 | 3.0 |
| **overall** | 4.87 | 4.6 | 4.73 | 2.89 |

## 故障 / flag
| condition | 局数 | 判官flag | 硬检 |
|---|---|---|---|
| base_S5 | 1 | 0 | 无 |
| new_goal | 1 | 0 | 无 |
| boundary | 1 | 2 | 无 |
| hp | 1 | 38 | meta_marker×1 |

> 注：判官绝对分有压缩/偏差，**信 Δ 不信绝对值**。Δ 为正=后者比前者好。