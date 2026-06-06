# 可玩性体检报告 · 3判官面板（qwen3.7-max, glm-5.1, kimi-k2.6）

## 总览（逐局，分=3判官共识）
| 局 | 模式 | persona | 回合 | err | TTFT中位 | NPC | 导演 | IP | 硬检 | 进展 | 终幕 | 结局 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1-huafei-goal | script | goal_driven | — | 999 | — | — | — | — | — | — | — | no_session |
| S2-dixueyanqin-goal | script | goal_driven | — | 999 | — | — | — | — | — | — | — | no_session |
| S3-pishuang-detective | script | detective | 12 | 19 | 19.2 | 3.27 | 3.08 | 4.37 | 0 | 1/12 | middle | ✗ |
| S4-huafei-boundary | script | boundary_pusher | — | 999 | — | — | — | — | — | — | — | no_session |
| S5-free-houhou-goal | free | goal_driven | 21 | 0 | 19.0 | 3.16 | 3.04 | 3.95 | 0 | 9/21 | climax | ✗ |
| S6-free-jia-curious | free | curious | 21 | 0 | 20.0 | 3.26 | 3.42 | 4.65 | 0 | 5/21 | middle | ✗ |

## npc 维度均值（跨局·判官共识）
| 维度 | 均值 | 最低局 |
|---|---|---|
| in_character | 3.51 | S3-pishuang-detective=3.33 |
| voice_distinct | 3.18 | S3-pishuang-detective=3.13 |
| reactivity | 3.44 | S5-free-houhou-goal=3.13 |
| info_isolation | 3.54 | S3-pishuang-detective=3.47 |
| no_meta | 4.9 | S3-pishuang-detective=4.87 |
| agency | 3.26 | S6-free-jia-curious=3.14 |

## director 维度均值（跨局·判官共识）
| 维度 | 均值 | 最低局 |
|---|---|---|
| scene_advance | 3.09 | S3-pishuang-detective=2.99 |
| tension | 3.58 | S3-pishuang-detective=3.43 |
| npc_activation | 3.69 | S5-free-houhou-goal=3.46 |
| info_gating | 3.3 | S3-pishuang-detective=2.92 |
| arc_coherence | 3.69 | S5-free-houhou-goal=3.46 |
| agency_response | 3.23 | S5-free-houhou-goal=2.78 |

## ip_fidelity 维度均值（跨局·判官共识）
| 维度 | 均值 | 最低局 |
|---|---|---|
| character_fidelity | 4.41 | S5-free-houhou-goal=4.0 |
| etiquette_titles | 4.27 | S3-pishuang-detective=3.87 |
| relationships | 4.5 | S5-free-houhou-goal=3.77 |
| world_canon | 4.52 | S5-free-houhou-goal=3.96 |
| plot_motif | 4.5 | S5-free-houhou-goal=4.32 |
| language_register | 4.7 | S5-free-houhou-goal=4.51 |

## 判官间一致性（per-judge overall，看分歧）
| 局 | 镜头 | qwen3.7-max | glm-5.1 | kimi-k2.6 |
|---|---|---|---|---|
| S3-pishuang-detective | npc | 3.8 | 3.0 | 3.0 |
| S3-pishuang-detective | director | 3.67 | 3.0 | 2.57 |
| S3-pishuang-detective | ip_fidelity | 4.2 | 4.4 | 4.5 |
| S5-free-houhou-goal | npc | 3.6 | 3.2 | 2.67 |
| S5-free-houhou-goal | director | 3.5 | 3.18 | 2.45 |
| S5-free-houhou-goal | ip_fidelity | 3.88 | 4.25 | 3.71 |
| S6-free-jia-curious | npc | 3.5 | 3.33 | 2.96 |
| S6-free-jia-curious | director | 4.09 | 3.5 | 2.67 |
| S6-free-jia-curious | ip_fidelity | 4.5 | 4.88 | 4.57 |

## 判官 flag + 硬检 flag 汇总
- **S3-pishuang-detective**：判官 ['qwen3.7-max@t0:severe_ooc', 'qwen3.7-max@t0:premature_reveal', 'qwen3.7-max@t4:state_conflict', 'qwen3.7-max@t6:stalled', 'glm-5.1@t0:premature_reveal', 'glm-5.1@t0:state_conflict', 'glm-5.1@t4:state_conflict', 'glm-5.1@t6:stalled', 'glm-5.1@t8:state_conflict', 'glm-5.1@t10:stalled', 'glm-5.1@t10:state_conflict', 'kimi-k2.6@t0:premature_reveal', 'kimi-k2.6@t1:stalled', 'kimi-k2.6@t2:stalled', 'kimi-k2.6@t4:state_conflict', 'kimi-k2.6@t6:stalled', 'kimi-k2.6@t6:railroad', 'kimi-k2.6@t10:stalled', 'qwen3.7-max@t0:wrong_title', 'qwen3.7-max@t0:canon_contradiction', 'qwen3.7-max@t3:wrong_title', 'glm-5.1@t0:wrong_title', 'glm-5.1@t3:wrong_title', "kimi-k2.6@t0:wrong_title:小允子称甄嬛为'娘娘'，其时仅为贵人", 'kimi-k2.6@t0:canon_contradiction:纯元皇后死于难产惊悸，非砒石中毒；且初入宫即现谋害元后之证，与原著叙事节奏不符']；硬检 无
- **S5-free-houhou-goal**：判官 ['glm-5.1@t12:info_leak', 'qwen3.7-max@t2:agency_gap', 'qwen3.7-max@t4:railroad', 'qwen3.7-max@t8:railroad', 'qwen3.7-max@t10:stalled', 'qwen3.7-max@t10:tension_mismatch', 'qwen3.7-max@t12:railroad', 'qwen3.7-max@t12:state_conflict', 'qwen3.7-max@t12:stalled', 'glm-5.1@t1:state_conflict', 'glm-5.1@t2:state_conflict', 'glm-5.1@t8:state_conflict', 'glm-5.1@t10:stalled', 'glm-5.1@t14:railroad', 'glm-5.1@t16:railroad', 'glm-5.1@t16:state_conflict', 'glm-5.1@t18:stalled', 'glm-5.1@t18:state_conflict', 'kimi-k2.6@t0:railroad', 'kimi-k2.6@t1:railroad', 'kimi-k2.6@t2:railroad', 'kimi-k2.6@t2:state_conflict', 'kimi-k2.6@t4:railroad', 'kimi-k2.6@t8:railroad', 'kimi-k2.6@t8:state_conflict', 'kimi-k2.6@t10:stalled', 'kimi-k2.6@t12:railroad', 'kimi-k2.6@t12:state_conflict', 'kimi-k2.6@t14:stalled', 'kimi-k2.6@t14:railroad', 'kimi-k2.6@t16:premature_reveal', 'kimi-k2.6@t16:railroad', 'kimi-k2.6@t18:stalled', 'kimi-k2.6@t18:railroad', 'kimi-k2.6@t20:stalled', 'kimi-k2.6@t20:railroad', 'qwen3.7-max@t0:canon_contradiction', 'qwen3.7-max@t0:modern_language', 'qwen3.7-max@t1:canon_contradiction', 'qwen3.7-max@t1:wrong_title', 'qwen3.7-max@t1:modern_language', 'qwen3.7-max@t1:ooc', 'qwen3.7-max@t9:canon_contradiction', 'qwen3.7-max@t12:canon_contradiction', 'qwen3.7-max@t15:ooc', 'qwen3.7-max@t15:canon_contradiction', 'glm-5.1@t0:canon_contradiction', 'glm-5.1@t1:canon_contradiction', 'glm-5.1@t15:ooc', 'glm-5.1@t15:canon_contradiction', 'kimi-k2.6@t0:canon_contradiction: 周宁海为华妃翊坤宫太监，断无在景仁宫皇后殿内侍立之理', "kimi-k2.6@t0:modern_language: 齐妃台词中'我这一大早''定是皇上昨日又夸赞'等语偏现代口语", 'kimi-k2.6@t1:modern_language', 'kimi-k2.6@t9:canon_contradiction', 'kimi-k2.6@t12:ooc', 'kimi-k2.6@t12:canon_contradiction', 'kimi-k2.6@t15:canon_contradiction']；硬检 无
- **S6-free-jia-curious**：判官 ['qwen3.7-max@t14:severe_ooc', 'qwen3.7-max@t2:railroad', 'glm-5.1@t2:stalled', 'glm-5.1@t6:stalled', 'glm-5.1@t10:state_conflict', 'glm-5.1@t12:stalled', 'glm-5.1@t14:stalled', 'glm-5.1@t20:state_conflict', 'kimi-k2.6@t1:railroad', 'kimi-k2.6@t2:stalled', 'kimi-k2.6@t4:stalled', 'kimi-k2.6@t6:stalled', 'kimi-k2.6@t12:stalled', 'kimi-k2.6@t14:stalled', 'kimi-k2.6@t16:railroad', 'kimi-k2.6@t18:stalled', 'kimi-k2.6@t20:state_conflict', 'qwen3.7-max@t1:ooc', 'qwen3.7-max@t1:wrong_title', 'qwen3.7-max@t1:modern_language', 'qwen3.7-max@t15:wrong_title', 'qwen3.7-max@t18:wrong_title', 'glm-5.1@t1:ooc', 'kimi-k2.6@t1:wrong_title']；硬检 无