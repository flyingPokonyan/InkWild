# 可玩性评测：架构层面 Bug 分析与优化交接

状态：分析完成（2026-06-02），交付给后续优化窗口
来源：甄嬛传世界 6 局可玩性评测（4 script + 2 free，OpenCode 游戏系统，3 家族跨源判官 qwen/glm/kimi + Claude 第 4 判官）
读法：每条按「现象 → 架构根因 → 合理性评价 → 涉及代码 → 修复方向」组织。优先级见末尾汇总。

---

## 0. 评测结论速览（给上下文）

| 局 | 模式/persona | NPC | 导演 | IP | 硬检 | 真实结局 |
|---|---|---|---|---|---|---|
| S1 华妃 | script/goal | 3.40 | 3.27 | 4.22 | 0 | ✅ ended（forced/timeout）|
| S2 滴血验亲 | script/goal | 3.51 | 3.76 | 4.64 | 0 | ✅ ended（forced/normal）|
| S3 砒霜 | script/detective | 3.17 | 3.34 | 3.78 | 0 | playing（回合用尽，climax 9 轮）|
| S4 华妃 | script/boundary | 3.54 | 4.06 | 4.44 | 0 | playing |
| S5 皇后 | free/goal | 3.06 | 3.10 | 4.38 | 0 | playing（free 无结局）|
| S6 甄嬛 | free/curious | 3.26 | 3.42 | 4.65 | 0 | — |
| 均值 | | 3.32 | 3.49 | 4.35 | 0 | |

三条稳定结论：**① IP 契合是硬实力（全场最高维 4.2–4.65）② 导演是短板（3.1–4.06，推进+收束）③ 护栏极稳（6 局硬检全 0，含越狱局）**。

**数据诚实备注**：每局 n=1（信方向/flag，不信绝对小数）；判官绝对分有压缩，跨局相对排序更可信；script 局被「导演截断」截短（见 P0）。

---

## 1. 【P0】导演 climax JSON 被中途掐断 —— 单点失败炸全回合

### 现象
- climax 阶段，导演的结构化 JSON **回来时不完整/malformed，卡在 ~2242 字符**（远低于预算），**连试 3 次**都失败 → 整回合 abort。
- 直接后果两个，同根：
  1. **回合软失败**：HTTP 200 但无旁白。各局 10–57% 回合这样（S3/S4 仅成功 13/30）。
  2. **`ending_triggered` 丢失**：导演「赚来的结局」信号被切掉。
- 实测：6 局结局**全部走 forced 兜底**（`ending.resolved path=forced`），**0 次 `path=ai`、0 次 `path=hard`**。玩家永远只拿到 timeout/normal 安慰奖，拿不到挣来的好结局。

### 架构根因
**导演是一坨「全有或全无」的单体大 JSON**：`scene_brief + active_npcs + per_npc_focus + scene_direction + state_updates + case_board_ops + ending_triggered + …` 全塞进**一个** JSON。
- climax 时这坨最大（NPC 多 + 高强度 + `case_board_ops` 动态拼进来体积最大，见 `prompts.py:509/573`）。
- 流被中途掐一刀 → **整个 JSON 不可解析 → 回合 + 结局判断一起死**。无论截断落在哪个字段，后面全废。
- 排除项（已逐一验证）：不是 max_tokens（`director_json_max_tokens=8192` 很宽，输出才 2242 字符）；不是 reasoning（`game_main` 在 `REALTIME_TEXT_SLOT_NAMES`，reasoning 已关）；不是客户端超时（`orchestrator.py:500` 裸 await，无 wrapper，`llm_call_timeout_seconds=120` 没撞到）；那个 `npc_climax_step_timeout=45s` 是 NPC 的（`npc_agent.py:389`）。
- 最可能物理原因：**网关对输出有低于 8192 的实际上限，或把沉重的 climax 流中途丢了**（这步只靠读码无法 100% 坐实，需配合 §2 埋点或直接探网关）。

### 合理性评价
把「叙事指引 + 结构化案件板操作 + 结局裁决」捆进一个 all-or-nothing JSON，是**脆弱性设计**：最重要、最该保命的「结局信号」被体积最大、最易截断的 `case_board_ops` 连累。三者关注点不同、失败容忍度不同，不该共命运。

### 涉及代码
- `engine/director_agent.py:989-994` —— v2 走 `stream_json(max_tokens=director_json_max_tokens)`
- `engine/director_agent.py:631` —— 3 次重试（带 prompt mutation + provider 轮换）；耗尽 → `DirectorParseError` → 回合 abort（`orchestrator.py:512`）
- `engine/prompts.py:509/573` —— `case_board_ops` 动态拼进 DIRECTOR_TOOL schema
- `engine/prompts.py:317` —— `ending_triggered` 字段位置（在大 JSON 里靠后）

### 修复方向
1. **拆 `ending_triggered` 成独立小判断**（专治结局发不出，不被 case_board 截断连累）—— 最干净。
2. **climax 砍/缓发导演 payload**：`case_board_ops` 挪出主 JSON 走已有的 deferred「case_board tail」机制（日志见 `director_v2_tail`），climax 限 `active_npcs`。一箭双雕治软失败 + 结局丢失。
3. **末次失败抢救部分 JSON**：已有 `try_partial_parse`（流式增量用），终态 malformed 时也抢救可解析前缀，至少救回 `scene_brief`/`ending_triggered`。

---

## 2. 【P0】隐藏 bug：`finish_reason` 没接通 —— 引擎对自己的截断全瞎

### 现象
导演解析失败时一律记成 `failure=malformed finish_reason=None`，从不出现 `truncated`。

### 架构根因
- `engine/director_agent.py:1019` 从 usage 事件读 `finish_reason = event.get("finish_reason")`。
- 但 `llm/openai_compatible.py:155-159` 的 usage 事件**只发 `type/input_tokens/output_tokens`，根本没有 `finish_reason` 字段**（grok provider 同样没有）。
- → 导演里 `finish_reason` **永远是 None** → `director_agent.py:1031` 的 `if finish_reason == "length": reason="truncated"`（以及配套「raise max_tokens」自愈逻辑）**是死代码，从未触发**。

### 合理性评价
**有一套正确的截断恢复逻辑，但它依赖的信号从未被填充 —— 比没有恢复机制更糟**（给人「已处理截断」的假安全感）。这也是 §1 的问题长期没被定位的直接原因：可观测性断了。

### 涉及代码
- `llm/openai_compatible.py:155-159`（usage 事件缺 `finish_reason`）
- `llm/grok.py`（同缺）
- `engine/director_agent.py:1019,1031`（消费方）

### 修复方向
**给 openai_compatible / grok 的 usage 事件补 `finish_reason`**（OpenAI 流最后一个 chunk 的 `choices[].finish_reason`）。几行改动，立刻让 §1 的截断**可见 + 自愈逻辑生效**。建议优先于 §1 其它修法。

---

## 3. 【P1】结局三层路径退化成「只剩兜底」

### 现象
`_resolve_ending`（`orchestrator.py:180-223`）设计了三层：authored hard → 导演 AI `ending_triggered` → 架构兜底地板。实测**只有兜底地板在工作**。

### 架构根因
- **hard 层从不匹配**：工坊生成的结局只带 `soft_conditions`，`check_hard_endings` 匹配 `hard_conditions`（`ending_system.py:92-109`），永远空。
- **AI 层从不触发**：被 §1 截断切没了。
- **forced 地板总兜底**：`check_forced_ending`（`ending_system.py:135-166`）在 `rounds_in_climax >= 12`（`FORCED_CLIMAX_LINGER_ROUNDS`）或 8 轮无新线索时，发 `_pick_stall_ending` —— **偏好 timeout/normal/bad「没挣到」的结局**（`ending_system.py:132,169-181`）。
- 净效果：玩家**只可能拿到安慰奖**，「挣来的好结局」结构上不可达。

### 合理性评价
分层兜底的设计本身是对的（地板确实防住了「卡 climax 永不结束」，S1/S2 满 12 轮被正确收尾）。问题是**三层里两层在实践中是死的**，导致体验从「多结局分支」退化成「单一安慰奖」。修好 §1+§2 后 AI 层能复活；hard 层需要工坊侧也产出 `hard_conditions`（或让 soft→AI 裁决补位）。

### 涉及代码
- `engine/orchestrator.py:180-223`（`_resolve_ending`），调用点 `928` / `2091`
- `engine/ending_system.py:92-181`
- `engine/narrative_arc.py:38-62`（阈值 + `resolution_tier`）

---

## 4. 【P1】导演「素」：防 railroad 护栏过校正成惰性

### 现象
弱/低能动输入时，导演滑水出美景但 0 推进（线索/事件全空）；甚至**纯观察输入也不回报线索**（玩家"仔细观察"→0 线索）。自由模式漫游局开局 7 回合 0 推进。

### 架构根因
- 弱输入 clamp（`prompts.py:842-853`）：为防 NPC 替玩家行动（railroad），强令「环境为主、active_npcs≤1、别暗示 NPC 主动」。它**只会「做更少」，没有「推世界但不抢玩家」的中间档**。
- 判定 `assess_input_strength`（`player_input_guard.py:101-129`）：`char_count<12` 或纯观察→weak。
- 节奏只有「连续 3 轮无发现才 advance」（`prompts.py:788-792`），**没有「每回合至少留一点新东西」的地板**（对比：收束有 12 轮地板，推进没有对应物）。

### 合理性评价
护栏方向对（防 railroad 是真需求，记忆里 railroad 是已知低频 bug），但**把「别抢玩家」和「别推世界」混为一谈**，过校正成 inertia。应拆开：弱输入下仍可推进世界（冒一条环境线索 / 后台事件），只是不替玩家完成其声明动作。纯观察至少回报一条感官线索（看了就该有所得）。

### 涉及代码
- `engine/prompts.py:788-792`（节奏）、`842-853`（弱输入 clamp）
- `engine/player_input_guard.py:101-129`
- `engine/orchestrator.py:1847+`（弱输入 clamp safety net，可挂"推进地板"兜底）

---

## 5. 【P2】次要发现

| # | 现象 | 架构根因/合理性 | 涉及 |
|---|---|---|---|
| 5.1 | **POV/能动越界**（free）：玩家是皇后，却命令了华妃的宫女颂芝 | 自由模式长程缺「玩家只能驱动自己 POV 角色」的边界约束；引擎照单全收跨角色指令 | 导演 intent 解析 / free 模式 prompt |
| 5.2 | **线索虚高**：把玩家自己下的命令记成 discovered_clue | 线索语义混淆「世界新事实」与「玩家意图日志」→ 进展度量灌水 | state_updates.new_clues 的写入门槛 |
| 5.3 | **延迟偏慢**：开场 TTFT ~20s，回合中位 18–24s，导演 climax 飙 45s | climax 导演 payload 重（同 §1）；与可玩性直接相关 | 同 §1 砍 payload 会顺带改善 |
| 5.4 | **引擎 warning 频发**：`npc_reflection.empty_output`（频繁）、`case_board_invalid_ops`（案件板 op schema 校验失败被丢）、`ending_summary_json_parse_failed` | 多处结构化输出解析脆弱；reflection 是后台非致命但说明 NPC 反思步常空转 | `engine/case_board.py` / `npc_agent` / `ending_system.py:77` |
| 5.5 | boundary 局旁白被挑衅带偏到**近恐怖氛围**（对宫斗略 OOC） | narrator 对敌意输入过度渲染阴森 | narrator 风格约束 |

---

## 6. 评测基建自身的坑（避免后续重踩）

- **🔴 评测期间绝不能改 backend 下的 `.py`**：栈跑在 `uvicorn --reload`（bind-mount→WatchFiles→reload），改 `.py` 会**热重启后端、掐断所有在飞 SSE** → driver 侧 `RemoteProtocolError`。本次「并发 4 死 3/4」的伪结论就是这么来的，**与网关/模型并发能力无关**。优化时若要边改边测，关掉 reload 或用独立实例。
- **真并发瓶颈 = 进程级全局信号量** `llm_global_concurrency=8`（`llm/router.py:42-54`），**非用户级**，所有用户/session 共用；单局峰值 6–8 个 LLM 调用就压满。上线伸缩要抬它（抬完天花板才暴露=网关账号真实额度+成本），详见记忆 `concurrency-bottleneck-2026-06-02`。
- **评测 harness 自身 bug**：`eval/examples/playability_judge.py` 的 `_progression` 用 `ending_triggered` 字段判结局，应改用 `game_sessions.status=='ended'`（forced 结局不写 `ending_triggered`）——正是它害我误报「故事收不了尾」。`capture_session` 需附带 status。
- **判官解析容错**已修：`eval/judge.py:loads_lenient`（修 kimi `>{` 前缀）+ 8 单测；跨家族绝对分判官必须走容错解析。
- **判官网关**（devops `sto.cn`）有 burst 限流，judge glue 已加退避（`XFAM_JUDGE_CONCURRENCY=3`+5 次退避）；并发拉太高会被拖慢甚至卡。

---

## 7. 优先级汇总

| 优先级 | 项 | 一句话 | 性价比 |
|---|---|---|---|
| **P0** | §2 补 `finish_reason` | 几行，让截断可见 + 自愈逻辑生效 | 极高，先做 |
| **P0** | §1 拆 ending / 砍 climax payload | 同时治软失败 + 结局丢失 + 延迟 | 高 |
| **P1** | §3 复活 AI/hard 结局层 | 让玩家拿到挣来的结局（依赖 §1+§2）| 高 |
| **P1** | §4 导演推进地板 | 治「素」，弱输入也推世界不抢玩家 | 中 |
| **P2** | §5.1 POV 边界 / §5.2 线索语义 / §5.4 解析脆弱 | 体验细节 + 健壮性 | 中 |
| —— | §6 harness `_progression` 修字段 | 评测准确性 | 顺手 |

**建议起手**：§2 → §1（先让问题可见，再砍 payload + 拆 ending），一轮就能把「软失败 + 只有安慰奖结局」两个 P0 同时压下去。
