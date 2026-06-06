# Director 模块技术说明

> 状态截至 2026-05-08。覆盖 Phase 0（案件板 ops 重设计、prompt injection 边界规则）+ Phase 1（cache-friendly prompt、JSON mode、player_action 结构化）+ Phase 2.A.3（parse 失败 + agent retry）落地后的形态。

Director 是世界引擎的**决策中枢**。每回合 orchestrator 调用 `DirectorAgent.run(...)` 喂入 GameState + 玩家输入 + 上下文摘要，Director 调 LLM 决定本轮的"剧情走向"——具体是一个结构化的 `DirectorResult`，包含：哪些 NPC 卷入 / 各 NPC 收到什么指令 / 场景氛围指引（喂 narrator）/ 状态更新 / 快捷操作建议 / 结局判定 / 记忆摘录 / 案件板 ops / 玩家行动分类 / NPC 发言顺序。

它**不直接**做的事：
- 不直接面向玩家说话（不输出 narrative，narrative 由 Narrator 写）
- 不直接写 DB（state commit 在 game_service / 案件板 history 在 orchestrator 后置）
- 不调度 NPC（orchestrator 拿 `npc_instructions` + `npc_speech_order` 串/并行调度）
- 不做内容审核 / 限流 / 成本守卫（这些是 orchestrator 上游的横切）

紧密耦合的上下游：
- 上：[orchestrator](./orchestrator.md)（调用方）
- 下：[llm-router](./llm-router.md)（LLM 调用通道）+ [case-board](./case-board.md)（消费 case_board_ops）+ [npc](./npc.md)（消费 npc_instructions / npc_speech_order）+ [memory](./memory.md)（消费 memory_extracts / inform_npc_calls）

## 1. 能力矩阵

### A. 决策输出字段（DirectorResult）

| 能力 | 状态 | 实现 |
|---|---|---|
| `involved_npcs` 本轮卷入 NPC 列表 | ✅ | `DIRECTOR_TOOL.input_schema.involved_npcs` + `_coerce_string_list` |
| `npc_instructions` 每个 NPC 的具体指令 | ✅ | `_coerce_string_dict` |
| `scene_direction` 场景描写指引（喂 narrator） | ✅ | 默认值 `"局势暂时平静，先观察周围的变化。"` |
| `state_updates` 位置/时间/线索/库存/NPC 关系更新 | ✅ | `_coerce_nested_dict`（按字段类型校验） |
| `quick_actions` 给玩家的 3-4 个快捷操作建议 | ✅ | `_coerce_string_list` + 默认 fallback |
| `ending_triggered` AI 结局判定 | ✅ | `_coerce_optional_dict` |
| `memory_extracts` 本轮需要记住的关键事实 | ✅ | `_coerce_memory_extracts`（5 类 type） |
| `case_board_ops` 案件板增量操作（仅 script 模式扩展 schema） | ✅ | `build_director_tool` 按 game_mode + script_type 注入 |
| `inform_npc_calls` 显式植入某 NPC 私有记忆 | ✅ | `_coerce_inform_npc_calls`（importance high/medium/low） |
| `npc_speech_order` NPC 发言顺序（NPC-1） | ✅ | `_coerce_speech_order`（必须 ⊆ involved_npcs） |
| `player_action` typed 玩家行动分类（1.B.5） | ✅ | `_coerce_player_action`（9 种 enum + summary） |
| `usage` token 用量 | ✅ | 透传 LLM Router 返回 |

### B. 调用模式

| 能力 | 状态 | 实现 |
|---|---|---|
| Tool-use 模式（主路径） | ✅ | `_run_tool_use` |
| Native JSON mode（更省 token） | ✅ | `_run_json_mode`（settings.director_prefer_json_mode 默认 False） |
| JSON mode 失败 fallback 到 tool-use | ✅ | `_run_json_mode` 返回 None → 走 tool-use |
| Tool-use 内 LLM `recall_memory` 工具 | ✅ | `RECALL_MEMORY_TOOL` + recall_fn 回调 |
| 内部最多 3 次循环（处理 recall 多轮交互） | ✅ | `for _ in range(3):` |
| 内部 3 次仍无 tool_use → 抛 `DirectorParseError`（2.A.3） | ✅ | line ~375 |
| 外层 `Director.run` 1 次 agent retry on parse error（2.A.3） | ✅ | line ~245 try/except DirectorParseError |
| Code-fence 包 JSON 自动剥离（兼容 Claude/Gemini） | ✅ | `_run_json_mode` line ~409-412 |
| Authors note 注入（每轮 system prompt 末尾追加） | ✅ | `Director.run` line ~225 |

### C. System prompt 结构（cache-friendly）

| 段 | 位置 | 来源 |
|---|---|---|
| 身份 + 5 项职责 | 稳定前缀 | 硬编码 `prompts.py` |
| 世界设定（base_setting） | 稳定前缀 | world_data |
| NPC 描述（npc_descriptions） | 稳定前缀 | world_data |
| 剧本秘密（script_setting，仅 script 模式） | 稳定前缀 | world_data |
| 结局条件（ending_conditions） | 稳定前缀 | world_data |
| 核心行为规则（含 prompt injection 边界） | 稳定前缀 | 硬编码 |
| 节奏控制（3 轮无发现加快 / 高强度后缓冲 / 10-15 轮小高潮） | 稳定前缀 | 硬编码 |
| 信任级别信息释放策略（trust 1-3/4-6/7-10） | 稳定前缀 | 硬编码 |
| NPC 行为逻辑 | 稳定前缀 | 硬编码 |
| `npc_speech_order` 用法 + 4 个示例（单人/双人张力/群戏/旁观沉默） | 稳定前缀 | 硬编码 |
| 场景氛围指导（按时段定基调） | 稳定前缀 | 硬编码 |
| 案件板规则（仅 script 模式 + script_type） | 稳定前缀 | `case_board_prompts.build_case_board_prompt_rules` |
| Author's Note（如有） | 稳定前缀（追加在 base_system 后） | 调用方传入 |
| 重要记忆（memory_context） | **可变后缀** | orchestrator 拼装：world_pulse / arc_summary / world_events / NPC schedule / world conflicts |

### D. 输出解析与校验

| 能力 | 状态 | 实现 |
|---|---|---|
| Malformed dict/list 字段宽容降级（warn + 默认值） | ✅ | `_coerce_*` 系列 + `_build_result` 顶部告警 |
| 空 scene_direction 用默认句兜底 | ✅ | line ~177 |
| `inform_npc` 拒绝指向不存在 NPC（防幻觉污染） | ✅ | orchestrator line ~502 + warn |
| `npc_speech_order` 过滤幻觉名字（不在 involved_npcs 的 drop） | ✅ | `_coerce_speech_order` line ~146-152 |
| `player_action.summary` 截断 80 字 | ✅ | `_coerce_player_action` line ~196 |
| `player_action.action_type` 不在 enum → fallback `other` | ✅ | line ~189 |
| `player_action.summary` 空 → drop（不持久化空 action） | ✅ | line ~194 |
| `case_board_ops` 仅做形状校验（dict 列表）；语义校验在 case_board.py | ✅ | `_coerce_case_board_ops` |
| `inform_npc_calls.importance` 不在 high/medium/low → 默认 high | ✅ | `_coerce_inform_npc_calls` |

### E. 错误与可观测

| 能力 | 状态 | 实现 |
|---|---|---|
| `DirectorParseError` 自定义异常 | ✅ | `director_agent.py` 顶部 |
| structlog `director.parse_failure`（attempts=3 + reason） | ✅ | line ~370 |
| structlog `director.parse_failure_retrying`（agent 层 retry） | ✅ | line ~234 |
| structlog `director.unrecoverable`（orchestrator 抓到 parse error） | ✅ | `orchestrator.py` line ~418 |
| structlog `director.json_mode_provider_failed/empty_output/parse_failed/non_object` | ✅ | `_run_json_mode` 多处 |
| structlog `director_tool_payload_malformed`（dict 字段类型不对） | ✅ | `_build_result` line ~166 |
| Prefix hash log（cache 命中分析） | ✅ | LLM Router 层（详见 [llm-router.md](./llm-router.md)） |
| Token usage 透传 | ✅ | `usage_data` 注入 DirectorResult |

### F. 跨模块协作

| 协作对象 | 通过什么字段 | 说明 |
|---|---|---|
| [orchestrator](./orchestrator.md) | 整个 DirectorResult（v2 还消费流式 `on_partial`） | 调用方；v2 蹭 `on_partial` 里程碑发思考态进度（v1 是 `phase=directing` 提示）+ 从 partial 抓 core 快照提前发 `done`（`case_board_ops` 在 schema 最后，故可剔除延后；见 orchestrator §2.7）+ parse error → SSE error |
| [npc](./npc.md) | `npc_instructions` / `npc_speech_order` | NPC 顺序对话核心；speech_order ≤ 3 兜底 trim |
| [narrator](./narrator.md) | `scene_direction` | Narrator weave 阶段织合 + 早流式 prelude 也用 |
| [case-board](./case-board.md) | `case_board_ops` | 严格 clue_id 锚点；无效 op 静默拒绝不致命 |
| [memory](./memory.md) | `memory_extracts` / `inform_npc_calls` | game_service 后置写入 memory_entries |
| [intent-system](./intent-system.md) | （间接）从 memory_context 读 NPC intent 摘要 | 不直接写 npc_intents，那是 world_simulator 的职责 |
| [cost-rate-moderation](./cost-rate-moderation.md) | （input） `<player_input>` 包裹 + system prompt 边界规则 | 输入注入防护 |

## 2. 关键能力实现要点

### 2.1 双调用模式 + 多层 fallback

**问题**：Tool-use 调用比 JSON mode 贵（消耗工具 schema token） + LLM 偶发不调工具，会让一回合卡住。但 JSON mode 也会偶发产 malformed JSON / 多包一层 code fence。

**解决**：双层尝试 + 三层 fallback：

```
Director.run
  ├─ if prefer_json_mode and recall_fn is None:
  │     └─ _run_json_mode → DirectorResult | None
  │         (None 时 fall through 到 tool-use)
  └─ _run_tool_use（含 3 次内部循环 for recall_memory 多轮）
      └─ 仍无 tool_use → DirectorParseError
          └─ Director.run 捕获后再 retry 1 次
              └─ 仍失败 → DirectorParseError 上抛
                  └─ orchestrator 转 SSE error{code:llm_parse}
```

**实现**：
- JSON mode 当 `recall_fn is None` 时才启用（recall_memory 工具需要多轮交互，JSON mode 一次性输出不支持）
- JSON mode 内手动剥 ` ```json ... ``` ` 包装（line ~409-412）
- Tool-use 内 `for _ in range(3)` 处理 recall：第 1 次 LLM 可能调 recall_memory，回灌结果，再询问；最多 3 轮
- Agent 层 retry：`Director.run` 包了一层 try/except `DirectorParseError`（2.A.3）；retry 不变 messages（同样 prompt 让 LLM 重试，不是改 prompt）

**取舍**：
- 不在 LLM Router 做 retry（router 只负责 transient error retry，parse 失败不是 transient）
- Agent 层只 retry 一次（再多就翻倍 cost；DirectorParseError 通常是模型行为问题不是网络问题）
- 不做 prompt 退化（即"换简单 prompt 再试一次"）—— 增加复杂度，效果不明显

### 2.2 Cache-friendly system prompt（Phase 1.A.3）

**问题**：每回合 director system prompt 几千 tokens，每次都全量传 LLM 浪费钱（DeepSeek 等支持 auto prefix-cache 的 provider 完全可以复用前缀）。

**解决**：把 system prompt 切成两段：
- **稳定前缀**：身份 + 世界设定 + NPC 描述 + 剧本设定 + 结局条件 + 行为规则 + 节奏 + 信任策略 + speech_order 用法 + 案件板规则。同一 (world, mode, script_type) 跨所有回合**字节完全一致**
- **可变后缀**：`memory_context`（本轮的 world_pulse + arc_summary + world_events + NPC schedule + world conflicts），每轮都不同

**实现**：
- 拼装顺序在 `prompts.build_director_system` line ~270-381，最后一行才追加 memory_context
- LLM Router 入口对 system 前 1024 字节做 sha256 → emit `prompt.prefix_hash` 日志（line ~57-71 `llm/router.py`）便于命中率分析
- 每轮的 `Author's Note`（如有）追加在 base_system 之后、memory_context 之前——它**也是稳定的**（一个 session 内不变）

**取舍**：
- Anthropic 显式 `cache_control` 标记没做（roadmap 1.A.4，已延后到切 Claude 主力时再做）
- DeepSeek auto prefix-cache 不需要任何标注，对最大头的 prompt 自动生效
- 把 Author's Note 放稳定前缀里（不是后缀）—— 牺牲一点灵活性换 cache 命中

### 2.3 案件板 ops 模式

**问题**：早期 Director 直接输出整份 case_board snapshot，每轮都重写——LLM 偶尔丢字段、覆盖玩家已发现的线索、生造新 clue_id 都会污染数据。

**解决**：Director 改输出**增量 ops 序列**（typed enum：`set_field` / `upsert_list_item` / `remove_list_item`），由纯函数 `apply_case_board_ops` 应用，每条 op 引用的 `clue_id` 必须在 `discovered_clues` 内（含同回合 new_clues）。

**实现**：
- `build_director_tool(script_type, game_mode)` 仅在 `game_mode == "script" and script_type` 时给 schema 注入 `case_board_ops` 字段（line ~213-251）
- 自由模式 LLM 完全不知道有这个字段（schema 里没有）
- prompt 里加显式约束："只能通过 case_board_ops 更新案件面板，不要输出整份 case_board 快照；每个证据或推理里的 clue_id 必须引用已经发现的线索 ID。"（line ~371-374）
- 详见 [case-board.md](./case-board.md) 的 ops 应用语义

**取舍**：
- DirectorAgent 这边只做形状校验（必须是 dict 列表）；语义校验（路径合法性 / clue_id 锚点）在 `case_board.py::apply_case_board_ops` 纯函数里
- 拒绝了"Director 输出 partial diff" 的方案——typed ops 比 diff 更明确，错误更容易定位

### 2.4 NPC 发言顺序的"沉默是合法选择"

**问题**：早期所有 involved NPC 全部发言，多人场景每人都接一句"礼貌话"，毫无群戏张力。

**解决**：把"卷入剧情"和"开口说话"解耦：
- `involved_npcs`：本轮在场或被卷入的 NPC（决定他们能拿到本轮 memory + 计 tick）
- `npc_speech_order`：本轮真正开口的人（必须 ⊆ involved_npcs）

System prompt 里给了 4 个用法示例（单人对话 / 双人张力 / 群戏议事 / 旁观沉默），明确"默认偏好 1-2 个发言者；只在真正群戏才让 ≥3 个开口"。

**实现**：
- `_coerce_speech_order` 严格过滤幻觉名字（不在 involved_npcs 的 silently drop）
- orchestrator 拿到 speech_order 后还会被 `npc_max_speakers_per_turn`（默认 3）兜底 trim
- 配合 NPC system prompt 里"沉默是合法选择"段（详见 [npc.md §3.10](./npc.md)），让 NPC 真敢不开口

**取舍**：
- 拒绝了"由 NPC 自己决定要不要说话"——LLM 会倾向都说一句以"显得有礼貌"，效果不如 Director 集中调度
- speech_order 跟 involved_npcs 双字段冗余，但语义不一样（前者是 acting cast，后者是 scene cast）；统一成一个会失去表达力

### 2.5 player_action 结构化追踪（Phase 1.B.5）

**问题**：NPC 跨轮认知很弱——它能看到自己的记忆，但看不到玩家在做什么"模式"（连问三轮、来回奔波各处、给过谁东西）。

**解决**：Director 每轮把玩家输入归类成 typed action（9 种 enum：`visit_location` / `ask_about` / `tell_npc` / `give_item` / `take_item` / `examine` / `confront` / `wait` / `other`），输出在 DirectorResult.player_action。orchestrator 把它 append 到 `game_state.player_actions`（cap 20 条），透传给每个 NPC 的 system prompt 渲染"玩家最近做过的事"段。

**实现**：
- Schema 在 `prompts.DIRECTOR_TOOL.input_schema.player_action`（line ~125-167）
- `_coerce_player_action`（line ~187-217）做归一化：未知 type → `other`；空 summary → drop（不持久化空 entry）
- summary 截断 80 字防 prompt 膨胀
- 详见 [npc.md §3.x recent_player_actions 渲染](./npc.md) 和 [state-and-persistence.md](./state-and-persistence.md) 的 cap 逻辑

**取舍**：
- 9 种 enum 不可扩展是有意的——粒度多了 LLM 分类不稳定
- summary 是 LLM 生成的"客观描述"——不是直接复用玩家原话（玩家原话可能含 prompt injection / 太长）
- 当前 NPC 看到的 player_actions **包括本轮新增**的那条（不是只有历史）——给 NPC 显式标签理解 Director 在让它响应什么

## 3. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/engine/director_agent.py` | DirectorAgent 主类 / DirectorResult / DirectorParseError / 所有 _coerce_* |
| `backend/engine/prompts.py` | DIRECTOR_TOOL schema / build_director_system / build_director_tool / build_director_json_instruction / RECALL_MEMORY_TOOL |
| `backend/engine/case_board_prompts.py` | build_case_board_prompt_rules（按 script_type 注入案件板规则） |
| `backend/engine/context_builder.py` | build_messages（玩家输入包 `<player_input>` + recent_messages 拼装） |
| `backend/engine/input_sanitizer.py` | wrap_player_input（XML 包裹 + `<` 转义） |
| `backend/engine/orchestrator.py` | Director 调用点 + parse error 兜底 + player_action append 逻辑 |
| `backend/llm/router.py` | first-token timeout / retry / prefix_hash 日志（详见 [llm-router.md](./llm-router.md)） |

## 4. 配置项

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `DIRECTOR_PREFER_JSON_MODE` | `false` | 启用 JSON mode（无 recall_fn 时生效） |
| `LLM_CALL_TIMEOUT_SECONDS` | `60.0` | LLM 首 token 超时（详见 llm-router） |
| `LLM_CALL_MAX_RETRIES` | `1` | router 层 transient retry 次数 |

| Slot | 模型档位 | 用途 |
|---|---|---|
| `game_main` | 主档 | Director / Narrator 主调用 |
| `conversation_compression` | 廉价档 | 上下文压缩（不是 director 直接用，但同 router 共享 cache） |
| `ending_summary` | 主档（可选） | 结局总结独立 LLM 调用（详见 ending_system） |

## 5. 测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_director_agent.py` | tool_use 解析 / parse_error 抛出 + agent retry / recall_memory 多轮 / 各 _coerce_* 字段 / player_action（typed/空/未知 enum 三种 case） |
| `tests/test_orchestrator.py::test_orchestrator_emits_llm_parse_error_when_director_fails` | DirectorParseError → orchestrator → SSE error{code:llm_parse} |
| `tests/test_orchestrator.py::test_orchestrator_appends_player_action_*` | player_action append + cap + NPC 注入 |
| `tests/test_director_inform_npc.py` | inform_npc_calls 写 director_told memory + 拒绝未知 NPC |
| `tests/test_npc_sequential_dialogue.py` | speech_order coerce + trim |
| `tests/test_prompts.py` | DIRECTOR_TOOL schema / case_board_ops 仅 script 模式 / player_action enum |
| `tests/test_prompts_stable_prefix.py` | 稳定前缀字节一致性（同 world 跨回合） |

## 6. 已知短板与未来扩展

### P2

- **JSON mode 没法用 recall_memory**：当前 `prefer_json_mode and recall_fn is None` 才启用 JSON mode；recall_fn 注入时强制走 tool-use。如果 LLM 长上下文需要主动调 recall，就吃不到 JSON mode 的省 token 收益。改进点是给 JSON mode 也支持双轮交互（先输出"我需要 recall X" → 注入结果 → 再要最终决策），但工作量不小。
- **Agent retry 不变 prompt**：当前 retry 用同样 messages 重发。如果 LLM 卡在某个奇怪状态，再发一次仍会失败。可以考虑 retry 时给 messages 追加一句 hint（"上次输出未调 director_decision 工具，请严格调用"），但要保证幂等性。
- **`director.parse_failure` 没区分 reason**：现在只记录 attempts=3，但不知道是 LLM 没调任何工具、还是调了 recall 但耗尽 3 次还没决策。加细分 reason 字段便于排查。

### P3

- **Anthropic cache_control 标记**（roadmap 1.A.4）：切 Claude 主力时给稳定前缀打 ephemeral cache 标记，省 50%+ input cost。当前 DeepSeek 主力 + auto prefix-cache 已经够，未触发。
- **Director streaming partial decision**：当前 LLM 必须一次性输出完整 tool_use；早流式（1.A.1）只能从 narrator prelude 启动，Director 仍要等齐。如果 Director 能流式输出 scene_direction（其它字段后到），TTFB 还能压一截。但 LLM API 这个能力不普及，等更多 provider 支持再说。
- **Prompt template A/B 测试框架**（roadmap 3.2，已砍）：现在 prompt 调整是"改 prompts.py 推全量"。一人开发不需要 A/B 框架。
