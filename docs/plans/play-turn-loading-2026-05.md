# Play 整轮加载生命周期重设 — 设计 spec

- 日期：2026-05-29
- 状态：✅ **已落地（2026-05-30）**。实现记录见 §11。
- 范围：play 页"首包前展示"重设 + `done` 时序真修（消 gap）
- 相关：`frontend/AGENTS.md`「三态约定」+「Play 页」（旧 visual-principles §10.1 / play-mode-spec 已并入并归档到 `docs/_archive/`）、记忆 `play-perf-optimization-2026-05`（L1/性能模型）

---

## 1. 背景与问题

### 1.1 首包前展示（pre-ttft）现状

玩家提交输入后、首包（narrator 第一个字）出来前约 **~16–20s**，当前展示链路：

- `ChatPanel.tsx`（`streamPhase==="processing"` 时）→ `StreamingStatusRail`（一个金点 + 一行 flavor 文字）。
- flavor 来源：
  1. **硬编码模板** `build_phase_hint("directing")`（`orchestrator.py:1165` → `engine/processing_hint.py`）：「幕后传来一阵低语，剧本正在被重新翻动」/「{地点}里气氛微微一变，幕后正在做出选择」。
  2. **intermission 动态短句**（`IntermissionAgent`，flash，1 句 15–25 字氛围文）。
- `ChatPanel.tsx:33` 还有写死 fallback：`"世界正在酝酿新的动静..."`。
- `ProcessingHints.tsx`（累加 4 行灰斜体）是**死代码**，未被引用。

**用户反馈的问题**（2026-05-29 走查确认）：
- 模板句生硬、"写死"感；
- 灰斜体小字像系统日志、不沉浸；
- flavor 在模板句↔intermission 间切换，读起来"逻辑没懂、好像很多行"；
- 首包到达时硬切（瞬间清空）；
- 一句之后剩十几秒"干等"，不够智能。

### 1.2 `done` gap（次生问题）

L1 重排后：narrator 在 director 的 scene_direction 落点（~16s）起笔，正文 ~32s 流完；但 `done` 事件要等 **director 的完整尾巴**（`orchestrator.py:1696` `director_result = await director_task`，注释 1603 明示等 state_updates/clues 等记账尾巴），约 **~42s** 才发。

期间（正文流完 ~32s → done ~42s，约 **~10s**）：
- `streamPhase` 仍是 `"streaming"`；
- `ActionInput.tsx` `disabled={isStreaming}`（`isStreaming = isActivePlayStreamPhase(phase)`，"streaming" 为忙）→ **输入框禁用**；
- 正文已停、无任何信号 → 玩家"以为没结束 / 卡了"。

---

## 2. 目标 / 非目标

### 目标
1. 首包前展示改成**像优秀 agent 的过程反馈**：让玩家知道"在思考、在干嘛、没卡住"。
2. 反馈**真实、每回合不同**（引用玩家真实动作 + director 真实选中的 NPC），不定式、零额外 LLM。
3. 视觉复用品牌 **Branch 思考 logo**（`LoadingPulse`），小号左对齐、小字非斜体、和正文有区分，**§10.1 合规**。
4. **消除 done gap（真修，非创可贴）**：`done` 在正文流完 + 状态/结局就绪时即触发。
5. 顺带**砍掉 intermission flash 调用**（不再展示氛围短句，省成本）。

### 非目标
- 不展示剧情内容、不编造假步骤（§10.1：禁纯文字加载 / 禁"正在加载…"）。
- 不把"谁在反应"做成第二条叙事（之前评估的 C，受时序限制 + 易踩早流式 prelude 的质量坑）。
- 不拆 director（架构大改）；不改 case_board 的**生成**（仍在 director 内、保质量），只是不让它 gate `done`。
- 不引擎赌质量、不动 ttft（ttft 已 ~20s，且受 prelude 质量墙限制，本次不碰）。

---

## 3. 整轮加载生命周期（4 态）

```
① 思考态  (0~16s, streamPhase=processing)
   Branch logo(小·左对齐, 持续动画) + 演进式过程反馈(蹭 director 流式真实里程碑)
   小字 · 非斜体 · 和正文有区分。沿用 GenerationLoadingScreen 的 Branch+phase 范式。

② 正文流式 (~16~32s, streamPhase=streaming)
   思考态平滑淡出(~300ms) → 正文逐字流 + 光标接管"还在写"。

③ done   (正文流完 + state_updates/ending_triggered 就绪即触发, 不等 case_board/quick_actions)
   输入解锁、turn 真正结束。gap 消失。

④ follow-up (done 之后, 非阻塞)
   case_board_ops 等 director 尾巴完成后, 作为补发事件更新案件板。
   面板比正文晚一拍刷新(可接受)。
```

### 思考态的演进阶段（真实里程碑驱动）

| 阶段 | 触发时机（真实信号） | 文案示例 | 数据来源 |
|---|---|---|---|
| 接收行动 | 提交后立即 | 接收你的行动 | 立即 |
| 推演走向 | director 开始（~0–11s，最长） | 推演『{玩家这次输入摘要}』… | 玩家原始输入（截断） |
| 角色进场 | director 流式吐出 `active_npcs`（~11s） | {真实 NPC 名} 进入这一幕… | director on_partial |
| 落笔 | `scene_direction` 就绪（~16s，narrator 起笔） | 落笔成文… | director on_partial |

- 头 ~10s（prefill + 在憋 scene_brief）是唯一"一句"的阶段——不暴露 scene_brief 内容（剧情/剧透），靠 **Branch 动画 + 引用玩家动作**撑住"在动、针对你这次"。
- ~11s 起逐里程碑演进；每回合动作/NPC 不同 → 不定式、全真话、零 LLM。

---

## 4. 前端改动

### 4.1 `StreamingStatusRail.tsx`（重写）
- 三态单元：
  - **呼吸态**（无真实文案前）：Branch logo 动画，无文字。
  - **演进态**：Branch + 当前阶段文案（小字、非斜体、`--lv-ink-3`/比 narrative 小一档、左对齐）。文案变化用轻过渡（淡入），**不累加多行**——单行替换。
  - **淡出**：`streamPhase` 转 `streaming` 时整体淡出/上移（~300ms），让位正文。
- logo：复用 `LoadingPulse`。需要一个**小号内联左对齐**用法（现 `block` 是 64px 居中，`inline` 是 8px 纯点）；评估新增一个小号 Branch 尺寸或参数，落实现阶段定。
- §10.1 合规：Branch 为主视觉 + 文案为辅，非纯文字、非"正在加载…"，与 `GenerationLoadingScreen` 同范式。
- `prefers-reduced-motion`：Branch 自带降级。

### 4.2 `ChatPanel.tsx`
- 去掉写死 fallback `"世界正在酝酿新的动静..."`；无真实阶段文案时进"呼吸态"（只有 logo）。
- 消费新的 processing 事件序列（见 §6）。

### 4.3 清死代码
- 删除未引用的 `components/play/ProcessingHints.tsx`。

---

## 5. 后端改动

### 5.1 过程反馈进度事件
- 删除 `orchestrator.py:1165` 的 `build_phase_hint("directing")`（v2 路径）。`processing_hint.py` 暂留给 v1 路径。
- 砍掉 v2 路径的 intermission task（`IntermissionAgent`）——不再生成氛围短句。（`IntermissionAgent` 是否整体删除待定：确认无其他引用后删。）
- director 的 `on_partial` 里程碑 → 发 `processing` 进度事件：
  - 提交立即：`接收你的行动`
  - director 起跑：`推演『{player_input 截断}』…`
  - `active_npcs` 在 partial 中就绪：`{names} 进入这一幕…`
  - `scene_direction` 就绪：`落笔成文…`
- `on_partial` 在 director task 内运行，向主生成器传递进度需走类似 `narrator_ready_waiter` 的信号通道（队列/事件），主循环 drain 后 `yield`。

### 5.2 `done` 时序（真修）
- `done` 触发条件改为：`max(正文流完, core 就绪)`，其中 **core = state_updates + ending_triggered**（+ quick_actions 若此时已就绪）。
- 从 director **partial** 提取 core（嵌套对象需完整闭合后才用）；不再无条件 `await` 完整 director_task 才发 done。
- `case_board_ops`：等 director 完整结果出来后，作为 **follow-up SSE 事件**补发（新事件类型或复用既有 case_board 更新通道），`game_service` + 前端应用 → 案件板刷新。
- director task 仍在后台跑完（case_board 仍在 director 内生成，质量不变）。

---

## 6. 数据流 / SSE 事件

```
processing(stage=接收/推演/进场/落笔) × N
  → narrative 流式 …
  → done { new_state(含 state_updates), ending_triggered, quick_actions? }   ← 解锁
  → case_board_update (follow-up, 非阻塞)   ← 刷新案件板
```

- 所有 SSE payload 带 `version: 1`；内部 `state_ready` 不发前端（既有约定）。
- `processing` 事件 payload 建议：`{ type:"processing", kind:"progress", stage, label, npcs? , version:1 }`；前端按 `stage` 渲染 logo + 文案。前后端 schema 同步（`frontend/lib/sse.ts` + `lib/types.ts`）。

---

## 7. 待验证假设 / 风险（实现阶段确认）

1. **director 吐字顺序**：`state_updates` / `ending_triggered` 确实在 `case_board_ops` **之前**生成（`case_board_ops` 由 `build_director_tool_v2` 最后追加进 schema，大概率最后吐）——需用真实回合**量一下** partial 里各 key 的到达顺序/时机；若 `ending_triggered` 偏后，需把它在 schema 里前移（结局判定必须先于解锁，否则会"该结局却放人继续"）。
2. **partial 提取可靠性**：从流式 partial 稳定取出**完整**的 `state_updates`/`ending_triggered` 嵌套对象（现 `on_partial`/`try_partial_parse` 处理顶层 key，嵌套需谨慎）。
3. **commit-from-partial 安全性**：用 partial 的 core 提交状态后，若 director 后续失败/重试 → 状态一致性。需保证只在 core 确定完整时提交，并妥善处理 director 完成/失败两路。
4. **clamp 逻辑**：weak-input clamp（`orchestrator.py:1742+`）会改 `director_result`（intensity/active_npcs）。done 时机需要的字段（clamp 后的 active_npcs 等用于 done 的部分）要齐。
5. **case_board follow-up 时序**：玩家若在 done 后**秒速**提交下一轮，case_board 可能还没补完 → 下回合 director 读到略旧的 case_board。概率低、影响小（面板/推理晚一拍）；如需可在下一轮开始前确保 follow-up 已落库。

---

## 8. 错误处理

- 进度事件生成/传递失败：静默，Branch logo 继续动（不阻塞）。
- done core 提取失败：**回退到现行为**——`await` 完整 director_task 再发 done（gap 退化回现状，但不出错）。
- case_board follow-up 失败：静默，下回合沿用旧 case_board（可接受）。
- `prefers-reduced-motion`：Branch + Grow 自带降级（§10.1）。

---

## 9. 测试

- **后端（轻量 pytest）**：
  - done 在 core 就绪 + 正文流完时触发（不等 case_board）；
  - case_board follow-up 事件补发；
  - 进度事件序列（接收/推演/进场/落笔）按真实里程碑发出；
  - core 提取失败回退到完整 await。
- **前端（vitest 若可行 + 手测）**：
  - `StreamingStatusRail` 三态渲染 + 淡出过渡；
  - `ChatPanel` 无 fallback 模板、消费新事件；
  - `prefers-reduced-motion` 降级。
- **真实回合验证**（`_measure_play.py` + 手玩）：done gap 消失（正文流完即解锁）、过程反馈逐回合不同、案件板 follow-up 正常、无卡顿。

---

## 10. 实现顺序建议（交给 writing-plans 细化）

1. 后端进度事件（删模板/砍 intermission + on_partial 里程碑 → processing 事件）。
2. 前端 `StreamingStatusRail` 重写 + `ChatPanel` 接新事件 + 删死代码。
3. 后端 done 时序真修（先量 director 吐字顺序 → core 提取 → done 提前 → case_board follow-up）。
4. 前端 follow-up 事件消费（案件板刷新）。
5. 真实回合验证 + 调样式/文案。

---

## 11. 实现记录（2026-05-30）

全量落地（A 进度反馈 + B done gap），两个对 spec 的偏离已确认：

**A — 思考态进度反馈**
- 后端 `_process_action_v2`：删 `build_phase_hint("directing")` + 整个 IntermissionAgent 块（`engine/intermission_agent.py` 已删除；`intermission` model slot 现为 vestigial，未解析）。
- `on_partial` 真实里程碑 → `processing` 事件 `{kind:"progress", stage, input_summary?, npcs?}`：`received`（提交即发）/`reasoning`（director 起跑，带玩家输入摘要）/`npcs_entering`（active_npcs partial 就绪，带真实 NPC 名，走 `asyncio.Queue` → 主循环 drain）/`writing`（scene_direction 就绪）。
- 前端 `StreamingStatusRail` 重写：小号左对齐 Branch logo（`LoadingPulse` 新增 `variant="branch"`，持续动画）+ 按 `stage` 走 **next-intl 拼装**文案（`play.processing.*` zh/en）。**⚠️ 偏离 spec §6**：文案不在后端拼 `label`，改后端只发结构化信号、前端 i18n 渲染（符合项目 i18n 约定 + 支持 en）。
- `ChatPanel` 删写死 fallback、用 `AnimatePresence` 做 300ms 淡出消"首包硬切"。死代码 `components/play/ProcessingHints.tsx` 删除。

**B — done gap 真修**
- `on_partial` 在 **`player_action`** key 出现时抓 core 快照（剔 `case_board_ops`）→ `core_ready`。player_action 是 schema 里 case_board_ops 之前最后一个 *required* 字段，它就绪即保证 state_updates / ending_triggered 已闭合。
- Phase 3 用 core 快照经 `DirectorAgent._build_result_v2` 建 core result → 跑完 bookkeeping → 正文流完即发 `done`。Phase 4：`await` 完整 director_task → apply case_board → 发 `case_board_update` follow-up（带完整 mem_extract bundle）。
- `game_service._commit_case_board_followup`：只更 `game_state.case_board` 字段、不动 `rounds_played`、不覆盖并发后台写。前端 `stores/game.ts` 4 条流接 `onCaseBoardUpdate`（仅合并 game_state，不动 streamPhase）。
- **fallback（§8）**：无 partial 信号（如 provider 不流式）→ `await` 完整 director，case_board inline、无 follow-up、退回旧时序但保正确。free 模式无 case_board → 无 follow-up，mem_extract 仍在 done。

**SSE 契约**：`api/game.py:to_sse_event` 白名单加 `stage`/`input_summary`/`npcs`（processing）+ 新增 `case_board_update` 分支。

**测试**：`tests/test_orchestrator_v2_loading.py`（5 个，覆盖里程碑顺序 / done 早于 case_board / core 排除 case_board / 无信号 fallback / free 模式）+ 前端 `play-stream-state.test.ts` 新增 stage 透传 & "streaming 后晚到 writing 不回退"。

**验证**：5 个新测试通过；活栈实跑一轮（临时把 game_main/npc_agent 重绑 Grok 后已恢复）—— **done-gap 0.04s（旧 ~10s）**、4 个里程碑真实数据、`case_board_update` 在 done 后。

**§7.1 状态**：schema 顺序已确认（`case_board_ops` 由 `build_director_tool_v2` 追加在**最后**，仅 script 模式；state_updates/ending_triggered/player_action 都在它之前）。`ending_triggered` 未偏后、无需前移。生产 deepseek 时延下的真实吐字顺序仍建议 `_measure_play.py` 复测一次（fallback 已保正确性）。
