# Narrator 模块技术说明

> 状态截至 2026-05-08。覆盖 Phase 1.A.1（早流式 prelude） + Phase 1.A.3（cache-friendly system prompt） 落地后的形态。

Narrator 是世界引擎的**叙事织合器**——把 Director 的 `scene_direction`（场景指引）和各 NPC 实际说出的 `npc_dialogues`（对白）合成为一段流畅、沉浸的第三人称叙事文本，流式 yield 给玩家。

它**不直接**做的事：
- 不做决策（不决定谁说话、不更新 game_state）
- 不调度 NPC（NarratorAgent 拿到的 `npc_dialogues` 已经是 NPC agent 跑完的最终结果）
- 不感知 GameState 全貌（只透传 `recent_messages`，不读 case_board / NPC intents / 等）
- 不做内容审核（输出审核在 orchestrator 后置，不阻塞流式）

这是设计选择——Narrator 的职责严格收窄到"织合 + 风格化叙事"，让它对世界状态尽可能无知，避免 LLM 幻觉穿越（比如给玩家泄露 case_board / ending 信息）。

紧密耦合的上下游：
- 上：[orchestrator](./orchestrator.md)（早流式 prelude 跟 NPC 并行启动；weave 阶段在 NPC 完结后调用）
- 下：[llm-router](./llm-router.md)

## 1. 能力矩阵

### A. 两阶段调用模式

| 能力 | 状态 | 实现 |
|---|---|---|
| 早流式 prelude（仅写环境氛围，跟 NPC 并行） | ✅ | `stream_prelude` |
| Weave（织合 scene_direction + npc_dialogues） | ✅ | `stream` |
| Prelude 输出 cap `_PRELUDE_MAX_TOKENS = 256` | ✅ | `narrator_agent.py:10` |
| Weave 不限 max_tokens（用 router 默认 2048） | ✅ | `stream` 没传 max_tokens |
| Prelude 失败时由 orchestrator 兜底 fallback weave 单次开场 | ✅ | orchestrator try/except |
| Prelude_text 透传 weave，让续写不重复开场 | ✅ | `build_narrator_system(prelude_text=...)` |
| Authors Note 双阶段都注入（最高优先级风格参考） | ✅ | 两个 build_* 函数都接受 |
| 早流式开关 `settings.narrator_early_stream_enabled` | ✅ | orchestrator 主开关，默认 True |
| 早流式仅当有 NPC 时才跑（无 NPC 直接走 stream） | ✅ | orchestrator line ~746 |

### B. System prompt 结构（cache-friendly）

| 段 | 位置 | 来源 |
|---|---|---|
| 身份（你是 Narrator） | 稳定前缀 | 硬编码 prompts.py |
| 叙述视角与风格（第三人称有限 / NPC 对白引号 / 不替玩家做决定） | 稳定前缀 | 硬编码 |
| 场景类型风格切换（紧张/日常/对话/过渡） | 稳定前缀 | 硬编码 |
| 节奏感（环境后对话 / 重要时刻慢 / 日常快） | 稳定前缀 | 硬编码 |
| 禁止事项（现代网络用语 / 第四墙 / 时代错位词汇 / 华丽修辞） | 稳定前缀 | 硬编码 |
| Author's Note（如有） | 末尾追加（session 级稳定） | 调用方传入 |
| 上文 prelude_text（仅 weave 阶段且早流式时） | 末尾追加（每回合变化） | stream_prelude 输出 |
| 续写要求（仅有 prelude_text 时） | 末尾追加 | 硬编码 |

### C. Prelude 严格约束（防 LLM 抢戏）

| 能力 | 状态 | 实现 |
|---|---|---|
| Prelude 100-150 字范围（prompt 软约束 + 256 token 硬 cap 双保险） | ✅ | `build_narrator_prelude_system` line ~654-655 + `_PRELUDE_MAX_TOKENS` |
| 严禁写 NPC 台词 / 回应 / 具体行动 | ✅ | "**绝对不要**写任何 NPC 的台词、回应或具体行动" |
| 允许用环境暗示（脚步声、影子、目光）暗示 NPC 即将出现 | ✅ | line ~659 |
| 写到自然留白处停笔（让续写衔接自然） | ✅ | line ~660-661 |
| 禁止"接下来""然后"这类显式转折提示 | ✅ | line ~661 |

### D. Weave 阶段织合

| 能力 | 状态 | 实现 |
|---|---|---|
| 接收 scene_direction（Director 输出） | ✅ | `stream(scene_direction=...)` |
| 接收 npc_dialogues（dict[npc_name, dialogue]，跳过空 dialogue） | ✅ | orchestrator 收集时 `if result.dialogue` |
| 用 `- {name}：{dialogue}` 列表喂给 LLM | ✅ | `stream` line ~62 |
| 无 NPC dialogue 时显示"（无）"占位 | ✅ | line ~62 |
| 早流式模式下指示"承接上文，织入 NPC 对白和后续动作，不要重复开场" | ✅ | line ~71-72 |
| 单次 weave 模式下指示"将上述内容整合成自然流畅的叙事文本" | ✅ | line ~73-74 |

### E. 风格控制

| 能力 | 状态 | 实现 |
|---|---|---|
| 第三人称有限视角（始终跟随玩家） | ✅ | system prompt |
| 时代背景适配（民国世界用民国文学语言） | ✅ | system prompt |
| 4 类场景风格切换（紧张/日常/对话/过渡） | ✅ | system prompt |
| Author's Note 全 session 优先级最高 | ✅ | system prompt + 调用方在 game_service 一路透传 |
| 禁止现代网络用语（如「绝绝子」「yyds」「破防」） | ✅ | system prompt |
| 禁止打破第四墙（提及游戏/系统/AI） | ✅ | system prompt |

### F. 信息隔离（Narrator 不该看到的）

| 类别 | 当前怎么排除 |
|---|---|
| 案件板 case_board | 不在调用参数里 |
| 结局条件 ending_conditions / script_setting | 不在调用参数里 |
| NPC secret / intent / reflection / memory | NPC 已经"翻译"成 dialogue 文本，secret 等内部状态被 NPC agent 过滤 |
| GameState 全貌（位置/线索/库存等结构化数据） | 不在调用参数里（只透传 recent_messages，那是已经发给玩家的过往叙事） |
| 玩家正在思考但未输出的私心 | recent_messages 只含 LLM 已生成的内容 |

Narrator 看到的只是：scene_direction（director 已经决定的"应该写什么场景"）+ npc_dialogues（NPC 已经"说出口"的话）+ recent_messages（过往叙事）+ 风格约束。它本质上是个**风格滤镜**，没有自主决策权。

### G. 调用接口与协作

| 协作对象 | 输入 | 说明 |
|---|---|---|
| [orchestrator](./orchestrator.md) | 调度方 | 早流式时用 asyncio.create_task 起 NPC，主线 await prelude tokens；NPC 完结后再调 stream |
| [director](./director.md) | scene_direction | Narrator 严格按 director 的指示去写场景，不发挥 |
| [npc](./npc.md) | npc_dialogues | NPC 实际说出的话；空 dialogue（沉默）不会进 weave |
| [llm-router](./llm-router.md) | LLM 调用通道 | 默认走 game_main slot；prefix_hash 日志会记录 |

## 2. 关键能力实现要点

### 2.1 早流式 prelude（Phase 1.A.1）

**问题**：玩家发送 action 后要等 Director（最慢，2-5s）→ 所有 NPC 调用（每个 1-3s）→ Narrator 才开始流式输出第一个字。TTFB 5-10s 是常态。

**解决**：把 Narrator 拆成两阶段：
1. **prelude**：Director 决定 `scene_direction` 后立刻启动 NPC tasks（背景 task），同时 Narrator 直接开写"开场段（环境氛围）"——只用 scene_direction 和 recent_messages，不依赖 NPC dialogue
2. **weave**：NPC 完结后，Narrator 拿到 `npc_dialogues`，承接 prelude_text 续写，织合 NPC 对白和后续动作

Prelude tokens 直接 yield 给玩家，TTFB 从 5-10s 压到 1-2s。

**实现**：
- `stream_prelude` 单独一个 system prompt（`build_narrator_prelude_system`）严格约束"只写环境/氛围，不写 NPC 台词、不接近终结点"
- `_PRELUDE_MAX_TOKENS = 256` 硬 cap 防 LLM 跑太长把 weave 的预算吃了
- prelude_text（join 完所有 prelude tokens）传给 weave 的 system prompt，加段"承接上文不要重复开场"
- orchestrator 用 `asyncio.create_task(_run_all_npcs())` 让 NPC 真并行
- prelude 失败 → fallback 走单次 weave（不重复内容，因为 prelude_text 留空 weave 自己开场）

**取舍**：
- 拒绝了"流式 weave + LLM 自己织"——LLM 不知道哪些 NPC 还没说，无法可靠织合
- 拒绝了"分两次调用 NPC"（先快档预热再主档生成）——成本翻倍，效果不确定
- prelude 有 256 token cap 是有意压制——LLM 偶尔会想写一长段，但那会让 weave 阶段没空间承接

### 2.2 Cache-friendly system prompt

**问题**：Narrator 每回合的 system prompt 几千 tokens，每次都全量传 LLM 浪费。但跟 Director 不同，Narrator 的 prompt 没有 world_setting / NPC 描述（信息隔离要求），变量更少。

**解决**：稳定前缀（身份 + 视角 + 风格 + 禁止事项）跨整个项目统一。Author's Note（session 级稳定）和 prelude_text（每回合变化）追加在末尾，不破坏前缀 cache。

**实现**：
- `build_narrator_system(authors_note, prelude_text)` 拼装顺序：硬编码部分 → authors_note → prelude_text + 续写要求
- 同一 session 内 authors_note 不变，所以 prelude_text 之前的整段是 cache-eligible
- `build_narrator_prelude_system` 是独立 system prompt（更短），不跟 weave 共享

**取舍**：
- 拒绝了把 world_setting 注入 narrator system prompt（虽然 cache 命中率会更高）——信息隔离更重要，避免 narrator 替 director 决策
- prelude_text 在 system 末尾而不是 user message——prompt 实测上 LLM 更服从 system 中的 "承接上文" 指令

### 2.3 Prelude 严格约束（防 LLM 抢 NPC 戏）

**问题**：早期 prelude prompt 不够严格时，LLM 会"猜测" NPC 会说什么然后写出来——结果 weave 阶段拿到真 dialogue 后跟 prelude 矛盾，玩家看到割裂。

**解决**：prelude system prompt 用强语气约束：
- "只写环境与氛围铺垫，**绝对不要**写任何 NPC 的台词、回应或具体行动"
- "如果场景方向暗示某个 NPC 即将出现，可以用环境暗示（脚步声、影子、目光），但不要让 NPC 开口"
- "写到一个自然的留白处停笔...后续会有人接着写对话与动作"

**实现**：line ~657-661 的 prelude system prompt"严格约束"段。配合 256 token cap，LLM 想抢戏也没空间。

**取舍**：
- 不靠"prelude 失败就 fallback"——预防比补救更重要
- 加示例（"脚步声、影子、目光"）减少 LLM 主观发挥空间
- 让 prelude 写到"自然留白"——刻意留个钩子让 weave 接得自然

### 2.4 Weave 续写衔接

**问题**：早流式后 weave 不能"重新开场"——玩家已经看过 prelude 那段环境描写。但 LLM 拿到 scene_direction + npc_dialogues 容易"从头写起"。

**解决**：weave 的 system prompt 在 prelude_text 段后明确写：
- "直接承接上文的语气和场景"
- "把 NPC 对白和后续动作自然织入，不要重写环境/氛围"
- "不要写「接续」或「上文之后」等转折提示，让衔接自然"

User message 里也再强调一次"请承接上文（system 中给出的开场段），织入 NPC 对白和后续动作，不要重复开场。"

**实现**：
- `build_narrator_system(prelude_text=...)` line ~710-722
- `narrator_agent.stream` user message line ~71-72

**取舍**：
- 双重提示（system + user）有点重复但有效
- 不用 special token 标记 prelude（`<prelude>...</prelude>`）—— LLM 处理标签的能力不稳定，不如直接列出来 + 文字描述

## 3. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/engine/narrator_agent.py` | NarratorAgent 主类（stream / stream_prelude） |
| `backend/engine/prompts.py` | build_narrator_system / build_narrator_prelude_system |
| `backend/engine/orchestrator.py` | 早流式调度 + prelude_text 透传到 weave + usage 合并（line ~751-790、~865-893） |
| `backend/llm/router.py` | LLM 调用通道（详见 [llm-router.md](./llm-router.md)） |

## 4. 配置项

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `NARRATOR_EARLY_STREAM_ENABLED` | `true` | 早流式总开关；False 强制走单次 weave |

| Slot | 模型档位 | 用途 |
|---|---|---|
| `game_main` | 主档 | Narrator 默认走这个 slot；prelude 和 weave 共用 |

Narrator 没有独立廉价 slot——它是叙事质量直接关联的环节，跟 Director 共用主档比较稳。如果未来证据表明 prelude 用廉价档够用，可以加 `narrator_prelude` slot 单独绑定。

## 5. 测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_orchestrator_early_stream.py` | 早流式 prelude tokens 先于 NPC 完结 yield / prelude_text 传到 weave / 早流式关闭走单次 weave / prelude usage + weave usage 合并到 done |
| `tests/test_orchestrator.py::test_orchestrator_full_pipeline` | 完整 pipeline 含 narrator stream（基线回归） |
| `tests/test_prompts.py::test_narrator_system_includes_author_note_when_provided` | Author's Note 注入 |
| `tests/test_prompts.py::test_narrator_system_omits_author_note_when_not_provided` | Author's Note 省略 |

## 6. 已知短板与未来扩展

### P2

- **Prelude 失败后 weave 体验**：当前 prelude 抛错只 warn，weave 自己重新开场——玩家会看到一段被打断+重启的感觉。改进点是 prelude 失败时给一个 placeholder narrative（"夜风吹过..."）让 weave 续上去；但工作量小不大，等真有玩家投诉再做。
- **Prelude 没有独立廉价 slot**：现在跟 weave 共用 game_main 主档。prelude 的目标只是"快速产出几句环境描写"，理论上廉价档够用。可以加 `narrator_prelude` slot，但需要数据证明值得做（主档 prelude TTFB 已经 1-2s，再压收益不明显）。
- **Author's Note 影响 cache**：当前 Author's Note 在 system 末尾、prelude_text 之前；不同 session 的 authors_note 不同，破坏跨 session cache 复用。如果 admin 模板化常见 authors_note，可以考虑预 hash + 走 cache_control（Anthropic 切换时再做）。

### P3

- **Narrator streaming partial scene_direction**：当前 Narrator 必须等 Director 完整返回 scene_direction 才能启动 prelude。如果 Director 能流式输出 scene_direction（其它字段后到），Narrator 可以更早开始。但 LLM API 这个能力不普及。
- **多视角 narrator**：当前固定第三人称有限视角（跟随玩家）。如果支持第一人称、第二人称、上帝视角切换，可以让某些剧本（恐怖/悬疑）有更强表现力。但 schema + prompt + 测试工作量大，等 Phase 3。
- **NPC 内心独白注入 narrator**：当前 NPC dialogue 是台词 only。某些剧情需要让 narrator 写"王福握紧了拳头，他想起了那晚雨夜"这种内心独白。需要 NPC agent 暴露独白字段、Director 决定何时启用、narrator system prompt 加规则。
