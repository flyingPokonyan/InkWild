# 延迟与 TTFT 优化

> **状态（2026-06-10）**：§7 三刀（杠杆①③④）已随 `e29b56a` 部署并经 `hp-free-20260610T094340Z` 验证：TTFT p50 23.3s(-10%)、done p50 33.2s(-17%)，scene_direction 紧贴 partial_signal（差 2.3s），director/narrator 输出 -21%/-24%。**杠杆①结论：OpenCode 对关键路径 honor 关思考，"网关偷偷思考"假设排除**——切官方（杠杆②）回归纯"钱换速度"决策，前置=核网关真实计费。新尾巴：reflection 路径没带关思考配方在泄漏 CoT（纯成本，待修）；npc(flash) 的 cost_cents 疑似缓存价没配仍虚高（待核）。
>
> 缓存这条线（prefill 侧）已基本吃干；剩下的是 **decode 地板**，需要换更快推理 / 减输出 / 调架构才能再降。

---

## 1. 两个指标，别混

| 指标 | 含义 | 实测(30轮 free, OpenCode) |
|---|---|---|
| **TTFT** | 首句叙事**出字**（用户盯 loading 的真等待） | p50 ~25s |
| **done** | 整轮跑完、能再操作 | p50 ~40s / p95 ~60s |
| first SSE | 连接建立（非瓶颈） | ~0.2s |

体验 = 「~25s 出第一句 → 叙事边生成边流，用户边读边等 NPC/后续 ~15-35s」。**痛点是那 25s 首字**；后期 NPC 多时 done 拖到 60s 是次要痛点。

## 2. 延迟模型：prefill + decode

单轮延迟 = **prefill（吃输入）+ decode（顺序吐输出）**。关键路径：

```
玩家动作 → moderation(关键词,快) → director 解码出 scene_direction → narrator 起笔吐首字 → (NPC 并行,后织入) → done
```

- **director 在关键路径上、阻塞叙事**：narrator 要等 director 的 partial JSON 流出 `scene_direction` 才能起笔（早流式 `narrator_ready`）。
- **TTFT 的大头是 decode**：director 顺序解码（scene_brief → 4 个 NPC 字段 → **才到 scene_direction**）+ narrator 解码首句，两段 reasoning 级模型在 ~30-50 token/s 的网关上串行吐字 = 结构性 ~20-30s 地板。

## 3. 100 轮会不会更长？—— 不会线性涨，会 plateau

- **decode 恒定**：director 输出 ~800-2000 token、narrator ~600-1100 token，是**每轮内容量、与第几轮无关**。100 轮的 decode = 第 20 轮的 decode。
- **prefill 涨但封顶**：压缩（MIN_GAP=10 保 ~50 条）+ summary（6 段封顶）+ C-1（info_items 砍）一起卡住输入。director 输入前 30 轮 12K→32K，增速放缓，~100 轮约 45-55K 即平；且 60%+ 命中缓存，prefill 快。

**结论：100 轮单轮耗时 ≈ 第 30-40 轮（40-60s plateau），不会 2-3 倍。** 但 plateau 本身仍偏慢，是下面要攻的。

## 4. 已做：缓存/上下文优化（attack prefill）

| commit | 内容 | 效果 |
|---|---|---|
| `708b124` | recent_messages 改追加式窗口(hard_cap) + 压缩防抖计数器 + summary 有界 + reflection 限长 | 停掉每轮滑动导致的缓存失效 |
| `c92378a` | B1 续修(early-stream 时序:claim 在 state_ready 前盖戳) + 402→`provider_unavailable` 不再误报"导演无法解析" | 压缩 13→3 次/局,计数器正常 |
| `b66094d` | MIN_GAP 5→10(压缩 reset 减半) + C-1 director_state_view 砍 info_items(known_by→known_count + tail-cap) | director 状态尾部 8.8K→3K/轮 |
| `3fcbdf0` | token_usage.cost_cents 改缓存感知(对齐真实扣费,修 guardrail 虚高 3.8×) | 观测/guardrail 口径准确 |

**缓存命中实测演进**（free 模式 director）：21.8% → 31.7% → 34.7% → **50.2%（峰值 65%）**；narrator 11%→**70.7%**；npc 36%→**56.4%**。

> 注：真实扣积分（`credit_service` → `usage_to_cost_fen`）一直缓存感知、没问题；`3fcbdf0` 修的是观测列 `token_usage.cost_cents`（之前缓存盲虚高 3.8×，影响 dashboard + 单局 guardrail）。真实成本 ~7.4 分/轮（非 cost_cents 的 28 分），趋势早 4.5→后 9.4 分（context 累积）。

## 5. 待办：压 decode 地板的杠杆（按性价比排）

| # | 杠杆 | 攻 | 收益 | 风险/成本 |
|---|---|---|---|---|
| ① | **验证 reasoning 在 OpenCode 上真关没关** | TTFT | 可能白捡 5-10s | 零(只抓一笔原始响应看有无 reasoning_content) |
| ② | **切 DeepSeek 官方网关**（已计划） | TTFT+稳定性 | 官方实测 16.7s vs OpenCode 25s、无 p95 尖峰 | 钱(按量付费 vs OpenCode 便宜/免费) |
| ③ | **director schema 把 scene_direction 提前** | TTFT | narrator 早起 ~5-10s | 中(CoT 顺序取舍,A/B 验方向质量) |
| ④ | **director/narrator 输出瘦身**(砍字段/更紧) | TTFT+done | 每砍 200 token ≈ 省 4-6s | 中(权衡叙事丰富度) |
| ⑤ | **NPC 串行对话降 speakers/并行** | done | 后期 NPC 多时砍一截 | 中(丢"互相看见"质量,`npc_max_speakers_per_turn`/`npc_dialogue_sequential_enabled`) |
| ⑥ | director 换 flash | TTFT | decode 快 2-3× | 高(director 是大脑,质量风险大,不建议轻动) |

### 关键背景：reasoning 与 provider
- 历史坑：官方 DeepSeek 上 v4-pro reasoning 静默没关 → director 隐藏 CoT → 25-62s，修配方后 → 20.6s（见 memory `ttft-reasoning-recipe-rootcause`）。
- 现在 OpenCode：关思考 recipe 已发(host 命中 `_REASONING_OFF_BY_HOST` 的 `opencode.ai`)，但**未验证 OpenCode 真 honor**。官方 16.7 vs OpenCode 25 的差距里，可能就有"OpenCode 偷偷还在 think"——**杠杆①要先排除这个变量**。切官方(②)同时也绕开了这个不确定性。

## 6. 诚实的天花板

这套「director→narrator 串行 + 两段长文学输出」的架构，TTFT 想稳定压到 15s 以下，**不换更快推理(模型/网关)或显著减输出做不到**。AI Dungeon/c.ai 快是因为单小模型、一次调用、结构少——InkWild 的多 Agent 丰富度就是用延迟换的。缓存优化已吃干，再 attack prefill 收益递减。

**建议尝试顺序**：① 验 reasoning（零风险） → ② 切官方（已计划，主杠杆） → ③ schema 重排 → ④ 输出瘦身 → ⑤ 降 NPC speakers。

## 7. 本轮修复（2026-06-09）

### A. `scene_direction` 提前（TTFT 杠杆③）

已把 `DIRECTOR_TOOL_V2` 输出顺序调整为：

```
scene_brief → active_npcs → per_npc_focus → scene_role → dramatic_intensity → narrative_pressure → scene_direction → ...
```

原因：当前 v2 narrator 真正起笔前仍要等 NPC action，因此前 5 个 NPC 早绑字段必须保留最前；`narrative_pressure` 是很短的 narrator 节奏枚举，放在 `scene_direction` 前面避免早流式默认成 `advance`；`scene_direction` 随后避开 `offstage_active / structural_* / state_updates / quick_actions / player_action / case_board_ops` 等 bookkeeping tail。下一轮评测重点看日志：

- `stage.timing stage=director_v2 partial_signal_ms`：NPC 早绑触发时间应保持不退化。
- `stage.timing stage=director_v2 scene_direction_ms`：应从旧顺序的 ~director 40%+ 降到紧贴 `partial_signal_ms`。
- TTFT：理论收益取决于 OpenCode 是否按 JSON schema 顺序稳定输出；若模型不完全遵守，收益会打折。

### B. reasoning 是否真关的观测（TTFT 杠杆①）

OpenAI-compatible / DeepSeek provider 现在会统计上游流式 delta 中的 `reasoning_content`，只记录块数和字符数，不记录具体内容；router 发现后打印：

```
llm.reasoning_content_observed
```

下一轮评测判断：

- 若完全没有这条日志：OpenCode 至少没有显式返回 reasoning delta，继续看官方网关差异。
- 若出现 `reasoning_requested=false` 但 `chunks>0`：说明网关没有 honor 关 thinking 配方，这是 TTFT 异常的强信号，优先切官方或换 recipe。

### C. Director 早期字段瘦身（TTFT 杠杆④的小刀）

把关键路径前段的软上限收紧，并加 parser 兜底：

- `scene_brief`：≤300 字 → ≤180 字；超长时 `_build_result_v2` 截到 180。
- `per_npc_focus`：≤120 字 → ≤80 字；超长时 `validate_per_npc_focus` 截到 80。

这两个字段只喂 NPC/进度，不是玩家正文；过长会直接拖慢 `scene_direction` 到达，并让 NPC prompt 继续变胖。下一轮评测看 `director_v2.scene_brief.truncated` / `director_v2.per_npc_focus.truncated` 是否频繁出现：如果很频繁，说明 prompt 还没完全压住；如果很少出现，收益主要来自模型自觉少 decode。

同时看常规长度观测：

```
director_v2.early_field_lengths
```

它只记录 `scene_brief_chars` / `per_npc_focus_max_chars` / `per_npc_focus_avg_chars` / `active_npc_count`，不记录剧情内容。若 truncation 很少但长度仍贴近上限，说明模型基本遵守但 early decode 仍偏胖；若长度已经明显下降而 TTFT 不动，瓶颈更可能转到 narrator 首字或 NPC block wait。

## 附：评测 run 台账（VPS `backend/research/`）

| run | 节点 | provider | 关键结论 |
|---|---|---|---|
| `hp_parallel_20260608_085129` | 修复前基线 | OpenCode | director 缓存锁死 ~6K(21.8%)、压缩 30 次/49 轮 |
| `hp_free_opt_20260608_144329` | `708b124` | 官方(主)+OpenCode(续) | A 生效(缓存增长)、B1 仍坏、发现 402→llm_parse 假象 |
| `hp_free_40rerun_20260609_014848` | `c92378a` | OpenCode | B1 修好:压缩 3 次、缓存峰值 50%、0 llm_parse |
| `hp-free-20260609T062333Z` | `b66094d` | OpenCode | MIN_GAP+C-1:director 50.2%/峰 65%、压缩 2 次、质量无退化 |
| `hp-free-20260610T094340Z` | `e29b56a` | OpenCode | 三刀验证:TTFT p50 23.3s(-10%)/done p50 33.2s(-17%);scene_direction 距 partial_signal 仅 2.3s;director/narrator 输出 -21%/-24%;**①结论=关键路径 reasoning 干净,reflection 路径泄漏待修**;缓存持平 |
| `hp-free-continue-*-20260611` | `e29b56a` 同 session 续到 R100 | OpenCode | **§3 plateau 预测成立**:TTFT p50 三段 23.3/23.6/22.1s 全平,director 输入 19.8K→34.8K(max 39K,优于预测45-55K),narrator 缓存 76%;**新发现长局唯一真问题=DeepSeek json_object 空白输出退化**(24 次失败全是"数百空白字符+finish_reason=stop",R61-100 段 17 次/40 轮,重试轮即慢轮 Top8,R73/R78 三连败直接报错玩家);修法=空白流早期熔断+retry 换 tool 模式 |
| `hp-free-continue-20260612T021032Z` | `17c007a` 同 session 续 R101-120 | OpenCode | 验三修(日志下钻):**①熔断✅完全生效**(6 次空白退化全 64 字符即斩,尾延迟 p95 51→35s/max 66→40s 主因);**②升级 forced_tool🟡部分**(救回 4/6=67%,但 110+轮极长上下文下 forced_tool 同样退化产空 tool_use,2 次走到 final,R106 穿透给玩家;第二次 final 被上层兜底未暴露)→换 output 模式治标,DeepSeek 超长上下文 json/tool 通吃退化;**③narrator 反套路❌基本无效**(「不是X是Y」94→89%、开篇 55→68% 不降反升、破折号 6.4→6.2)但**续跑同 session 上文 anchoring 严重污染**,须全新 session 复核 |
