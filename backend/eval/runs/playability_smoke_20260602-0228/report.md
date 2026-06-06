# 可玩性体检报告 · 3判官面板（qwen3.7-max, glm-5.1, kimi-k2.6）

## 总览（逐局，分=3判官共识）
| 局 | 模式 | persona | 回合 | err | TTFT中位 | NPC | 导演 | IP | 硬检 | 进展 | 终幕 | 结局 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1-huafei-curious | script | curious | 3 | 0 | 17.5 | 3.28 | 3.28 | 4.33 | 0 | 0/3 | intro | ✗ |

## npc 维度均值（跨局·判官共识）
| 维度 | 均值 | 最低局 |
|---|---|---|
| in_character | 3.33 | S1-huafei-curious=3.33 |
| voice_distinct | 3.56 | S1-huafei-curious=3.56 |
| reactivity | 3.0 | S1-huafei-curious=3.0 |
| info_isolation | 3.45 | S1-huafei-curious=3.45 |
| no_meta | 5.0 | S1-huafei-curious=5.0 |
| agency | 3.11 | S1-huafei-curious=3.11 |

## director 维度均值（跨局·判官共识）
| 维度 | 均值 | 最低局 |
|---|---|---|
| scene_advance | 3.0 | S1-huafei-curious=3.0 |
| tension | 3.11 | S1-huafei-curious=3.11 |
| npc_activation | 3.83 | S1-huafei-curious=3.83 |
| info_gating | 3.44 | S1-huafei-curious=3.44 |
| arc_coherence | 4.11 | S1-huafei-curious=4.11 |
| agency_response | 3.11 | S1-huafei-curious=3.11 |

## ip_fidelity 维度均值（跨局·判官共识）
| 维度 | 均值 | 最低局 |
|---|---|---|
| character_fidelity | 4.67 | S1-huafei-curious=4.67 |
| etiquette_titles | 3.5 | S1-huafei-curious=3.5 |
| relationships | 5.0 | S1-huafei-curious=5.0 |
| world_canon | 5.0 | S1-huafei-curious=5.0 |
| plot_motif | 4.5 | S1-huafei-curious=4.5 |
| language_register | 4.83 | S1-huafei-curious=4.83 |

## 判官间一致性（per-judge overall，看分歧）
| 局 | 镜头 | qwen3.7-max | glm-5.1 | kimi-k2.6 |
|---|---|---|---|---|
| S1-huafei-curious | npc | 3.5 | 3.33 | 3.0 |
| S1-huafei-curious | director | 3.5 | 3.33 | 3.0 |
| S1-huafei-curious | ip_fidelity | 3.5 | 4.5 | 5.0 |

## 判官 flag + 硬检 flag 汇总
- **S1-huafei-curious**：判官 ['glm-5.1@t1:stalled', 'kimi-k2.6@t1:agency_response', 'kimi-k2.6@t2:railroad', 'qwen3.7-max@t0:wrong_title', 'qwen3.7-max@t1:canon_contradiction', 'glm-5.1@t0:wrong_title', 'kimi-k2.6@t0:wrong_title']；硬检 无