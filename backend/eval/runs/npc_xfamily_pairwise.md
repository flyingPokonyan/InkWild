# A/B 相对评测 · rubric=npc_pairwise · seed=42

盲判对比：**no_voice** vs **voice**（随机左右、匿名）

## 判官面板（各判官胜率）
| 判官 | no_voice | voice | err | voice 胜率 |
|---|---|---|---|---|
| qwen3.7-max | 2 | 5 | 0 | 5/7 |
| glm-5.1 | 2 | 5 | 0 | 5/7 |
| kimi-k2.6 | 2 | 5 | 0 | 5/7 |

## 逐回合共识
| turn | no_voice 票 | voice 票 | 多数 |
|---|---|---|---|
| 0 | 0 | 3 | voice |
| 1 | 0 | 3 | voice |
| 2 | 0 | 3 | voice |
| 3 | 0 | 3 | voice |
| 6 | 0 | 3 | voice |
| 7 | 3 | 0 | no_voice |
| 8 | 3 | 0 | no_voice |

> A/B 随机左右匿名盲判。判官需「强 + 与被测异源」才可信（见 README）。