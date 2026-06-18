# InkWild 产品说明书

> 最后更新：2026-05-19  
> 面向读者：玩家、创作者/管理员、AI 协作代理、新加入项目的人  
> 文档定位：这是当前产品说明书，不是早期商业计划或远期 roadmap。若本文与代码冲突，以当前代码和最新架构文档为准。

## 30 秒读懂

InkWild 是一个 **AI 驱动的互动叙事引擎**。玩家先选择一个世界，再选择玩法模式和扮演角色，然后用自然语言行动。系统会根据世界规则、NPC 记忆、角色关系、事件进度和玩家行为，实时生成下一段故事。

它的核心不是“选项分支小说”，也不是“随便聊天的 AI”。它要把两种体验放进同一个世界引擎里：

- **剧本模式**：有预设谜题、真相、关键事件和结局。玩家路径自由，但体验目标清晰，适合推理、调查、通关。
- **自由模式**：没有预设主线和硬性终点。玩家只借用同一个世界和角色，在其中探索、扮演、卷入关系和冲突，适合开放式冒险。

有创作权限的用户还可以进入 **创作工坊**，用一段描述生成世界或剧本，经过草稿编辑和发布后进入世界库。

## 产品定位

**一句话定位**：让玩家走进一个由 AI 实时推演的故事世界，在“有目标的剧本体验”和“开放式角色扮演”之间自由选择。

InkWild 解决的是两个极端之间的空白：

| 常见形态 | 优点 | 问题 |
|---|---|---|
| 传统剧本杀 / 固定分支互动小说 | 目标强、结构清楚、结局明确 | 路径固定，重玩价值有限 |
| 纯开放 AI 故事聊天 | 自由度高 | 容易跑散，世界一致性弱，NPC 记忆差 |
| InkWild 剧本模式 | 有真相、有线索、有结局，同时允许自然语言调查 | 需要好的剧本与节奏控制 |
| InkWild 自由模式 | 共享世界规则和 NPC 逻辑，允许开放探索 | 目标由玩家自己定义 |

InkWild 不是：

- 不是多人同局跑团；当前是单玩家单会话体验。
- 不是固定选项树；快捷行动只是建议，玩家可以直接输入任何合理行动。
- 不是通用聊天机器人；AI 必须服从世界观、角色记忆、时间和事件约束。
- 不是当前已经上线的付费/订阅/创作者市场；商业化仍属于后续方向。
- 不是自定义任意主角的沙盒；当前入口以世界内预设可扮演角色为主。

## 谁会用它

### 玩家

玩家想要的是“我真的进入了这个世界”。他们可以选择：

- 玩剧本模式，追查真相、收集线索、影响结局。
- 玩自由模式，扮演一个角色，在世界里生活、探索、结盟、对抗或旁观。
- 暂停和恢复会话，从历史记录回到未完成的故事。

### 创作者 / 管理员

创作者想要的是“快速搭出可玩的世界”。他们可以：

- 用提示词生成世界：世界观、地点、NPC、可扮演角色、封面和头像。
- 给已有世界生成剧本：故事线、事件、结局、剧本封面和结局图。
- 在草稿中编辑结果，再发布到世界库。

### AI 协作代理

AI 需要快速知道产品边界：

- 世界、剧本、角色、会话是核心实体。
- 剧本模式和自由模式共享世界引擎，但事件、案件板和结局规则不同。
- Player-facing 文案不能暴露剧本秘密、系统机制、prompt 或内部状态。
- 修改产品/文档时，应以 `CLAUDE.md`、`docs/ARCHITECTURE.md` 和当前代码为准。

## 核心概念

| 概念 | 含义 | 玩家能否看见 |
|---|---|---|
| 世界（World） | 一个舞台，包含时代、地点、规则、NPC、可扮演角色、封面图 | 能 |
| 剧本（Script） | 绑定某个世界的一条故事线，包含隐藏真相、事件、结局 | 能看到名称/简介，不能看到秘密 |
| 模式（Mode） | `script` 剧本模式或 `free` 自由模式 | 能 |
| 可扮演角色（WorldCharacter） | 玩家进入世界时选择的身份，有起点、物品和能力 | 能 |
| NPC | 世界里的非玩家角色，有性格、秘密、日程、知识和记忆 | 只能看见表现 |
| 会话（GameSession） | 一次游玩记录，保存状态、消息、回合数、结局 | 能 |
| 回合（Turn） | 玩家提交一次行动，AI 推演并返回下一段故事 | 能 |
| 游戏状态（GameState） | 当前位置、时间、线索、物品、NPC 关系、世界状态等 | 部分通过 UI 展示 |
| 快捷行动 | AI 根据当前场景建议的 3-4 个行动 | 能 |
| Author's Note | 开局前给 AI 的风格偏好，如“节奏慢一点” | 能输入 |
| 案件板 | 剧本模式的结构化推理面板，记录目标、问题、嫌疑人与证据 | 剧本模式能 |
| 统一侧栏 | 自由模式的状态侧栏，承载身份、地点、物品、关系等信息 | 自由模式能 |
| 结局 | 剧本或自然收束后的总结、路径回顾和证据回顾 | 能 |
| 草稿 | 创作工坊生成后、发布前的可编辑内容 | 创作者能 |

## 玩家流程

### 1. 浏览世界库

入口：`/discover`

玩家看到已发布世界列表，可以按题材筛选。每个世界展示名称、题材、时代、难度、封面和是否支持剧本。

### 2. 查看世界详情

入口：`/worlds/:id`

世界详情页展示：

- 世界名称、题材、时代、难度、预计时长。
- 世界简介和视觉封面。
- 可玩的剧本列表（如果该世界支持剧本模式）。
- 可扮演角色列表。
- 当前世界支持“剧本 + 自由”还是“仅自由模式”。

### 3. 开始前选择

入口：`/worlds/:id/start`

选择流程：

1. 选模式：剧本模式或自由模式。
2. 选剧本：只有剧本模式需要；无剧本的世界不能选择剧本模式。
3. 选角色：从世界提供的可扮演角色中选择。
4. 可选 Author's Note：告诉 AI 本局偏好的叙事节奏或风格。

### 4. 正式游玩

入口：`/play/:session_id`

游玩页的核心是“叙事文本 + 行动输入”：

- 玩家读到 AI 流式生成的叙事。
- 玩家可以点快捷行动，也可以自己输入自然语言行动。
- 剧本模式打开案件板，查看当前目标、关键问题、嫌疑人与证据。
- 自由模式打开统一侧栏，查看角色与世界状态。
- 玩家可以暂停、恢复、重试上一轮。
- 如果触发结局，会进入结局动画和总结页。

示例行动：

```text
询问茶摊老板昨夜有没有看到陌生人。
推开书房门，先检查书桌和抽屉。
我不急着追问，倒一杯茶观察王福的反应。
去后山看看有没有新鲜脚印。
```

### 5. 回到历史

入口：`/history`

玩家可以查看自己的历史会话，看到世界、角色、状态、当前时间和地点，并回到未结束的故事。

## 两种玩法模式

### 对比表

| 维度 | 剧本模式 | 自由模式 |
|---|---|---|
| 目标 | 追查真相、完成故事线、抵达结局 | 自己定义目标，开放探索 |
| 内容来源 | 世界 + 绑定剧本 | 世界 + 自由设定 |
| 隐藏真相 | 有 | 默认无 |
| 事件推进 | 有关键事件、线索保底和结局条件 | 由 NPC 意图、世界张力和玩家行为涌现 |
| UI 侧栏 | 案件板 | 统一状态侧栏 |
| 结局 | 有软/硬结局，如完美、普通、失败、超时 | 无硬性终点，可自然收束 |
| 适合 | 推理、调查、通关、复盘 | 扮演、生活、冒险、关系探索 |

### 剧本模式怎么玩

剧本模式的底层目标是“让玩家用自己的路径接近预设真相”。

玩家不会被强制按固定路线走，可以询问 NPC、观察环境、移动地点、使用物品、撒谎、拖延、施压或旁观。但系统会持续维护：

- 隐藏真相：凶手、动机、关键关系、危险倒计时等。
- 线索链：玩家发现的证据必须来自合理行动。
- 节奏推进：长时间无进展时，世界会通过 NPC、环境或事件给出推动。
- 案件板：用结构化方式记录目标、问题、嫌疑人和证据。
- 结局判断：玩家是否找到足够证据、是否指认正确、是否拖太久。

剧本模式的关键体验不是“猜中答案”，而是“我通过自己的行动把真相逼出来”。

### 自由模式怎么玩

自由模式的底层目标是“让玩家在世界里活出自己的故事”。

它不预设必须破解的谜题，也不把玩家拉回主线。系统会根据世界设定初始化 NPC 的意图、信息和冲突，然后随着玩家行动推进：

- NPC 会按自己的日程和目标行动。
- 世界张力会随玩家介入而变化。
- 玩家可以结交、得罪、帮助、背叛或忽视 NPC。
- 如果玩家长期无目标，世界会自然给出风声、冲突或机会，但不会伪装成剧本主线。
- 当故事自然到达阶段性收束，AI 可以生成总结或结局式回望。

自由模式的关键体验不是“通关”，而是“这个世界真的回应了我”。

## 默认世界示例：雾隐镇

当前种子世界是 **雾隐镇**：

- 题材：悬疑
- 时代：民国
- 难度：3
- 预计时长：30-60 分钟
- 简介：一个不断有人失踪的民国小镇，迷雾笼罩下暗藏杀机。

可扮演角色示例：

| 角色 | 起点 | 体验差异 |
|---|---|---|
| 外来调查员 | 镇口 | 身份公开，擅长审问和观察 |
| 镇上医生 | 诊所 | 人脉更广，适合从关系和医学线索入手 |
| 戏班班主 | 戏台 | 消息灵通，适合伪装和旁敲侧击 |

对外说明不要暴露剧本真相。需要查看内部谜底、事件和结局时，读 `backend/seeds/wuyinzhen/` 下的种子 JSON。

## AI 如何驱动一回合

玩家输入一次行动后，系统大致按这个顺序工作：

1. **输入安全检查**：过滤越权、违规或空输入；行动文本最长 2000 字。
2. **世界 tick**：推进时间、NPC 位置、世界事件、NPC 意图和信息传播。
3. **Director 决策**：分析玩家意图，决定场景方向、状态更新、参与 NPC、快捷行动、案件板操作和是否进入结局。
4. **NPC 演绎**：相关 NPC 按性格、秘密、信任度、情绪、记忆、日程和导演指令回应；NPC 可以沉默。
5. **Narrator 叙述**：把导演场景方向和 NPC 对白织成第三人称有限视角叙事。
6. **状态更新**：返回新的游戏状态、快捷行动、触发事件和可能的结局。
7. **记忆沉淀**：把关键事实写入结构化记忆，必要时触发 NPC 反思和长对话压缩。

这套分工让 InkWild 同时保留结构感和自由度：

- Director 管节奏和规则。
- NPC 管角色一致性和信息边界。
- Narrator 管玩家看到的文学化体验。
- WorldSimulator 管不依赖 LLM 的确定性世界推进。
- MemoryManager 管长线连续性。

## AI 行为边界

### Director 必须记住

- 不直接给玩家写叙事，只做决策。
- 不能把剧本秘密直接泄露给玩家。
- 要根据玩家行动更新位置、时间、线索、物品、NPC 信任和情绪。
- 玩家长时间没进展时，可以让世界主动给出推动。
- 剧本模式下，通过 `case_board_ops` 更新案件板，不输出整份案件板快照。
- 自由模式下不要偷塞主线，只让世界根据张力自然发展。

### NPC 必须记住

- 只知道自己应该知道的信息。
- 秘密不能主动倒给玩家，只能在高信任、被逼问或剧情合理时暗示。
- 信任度和情绪会改变说话方式。
- NPC 可以沉默、观察或做小动作，不需要每轮都说话。
- 多 NPC 顺序对话时，后说的人能听见前面的人，可以接话、反驳或装没听见。

### Narrator 必须记住

- 使用第三人称有限视角，始终跟随玩家。
- 不替玩家做决定，不写玩家内心独白。
- 不提“系统”“AI”“工具”“回合”等第四面墙内容。
- 风格必须符合世界时代和题材。
- 对话要保持 NPC 原始语气，不额外编造 NPC 没说过的话。

## 创作工坊

入口：`/workshop`

创作工坊面向有创作权限的用户。它的产品目标是：让创作者用一句或一段描述，生成可编辑、可发布、可游玩的世界和剧本。

### 生成世界

入口：`/workshop/generate/world`

输入一个世界想法后，系统会通过长任务生成：

- 世界基本设定：时代、地点、规则、题材、简介。
- 地点列表。
- NPC 列表：性格、秘密、知识、日程、初始关系。
- 可扮演角色。
- 封面图、英雄图、角色头像。
- 质量检查和可能的自动修复。

生成完成后先进入世界草稿。创作者可以编辑草稿，再发布为玩家可见的世界。

### 生成剧本

入口：`/workshop/generate/script`

剧本必须绑定一个已有世界。输入故事线或大纲后，系统会生成：

- 剧本设定和隐藏真相。
- 事件触发条件与效果。
- 多个结局。
- 推荐可扮演角色。
- 剧本封面和结局图。
- 质量检查和可能的自动修复。

生成完成后先进入剧本草稿。创作者可以编辑草稿，再发布到对应世界。

### 草稿与发布

创作工坊采用“草稿 → 发布”生命周期：

- 生成结果不会直接出现在世界库。
- 草稿可编辑、删除、继续加工。
- 发布是原子操作：发布失败时草稿仍保留，不会出现半发布状态。
- 发布后的世界和剧本才会进入玩家可见流程。

## 当前已实现能力

| 领域 | 当前状态 |
|---|---|
| 世界库 / 世界详情 | 已实现 |
| 剧本模式 | 已实现 |
| 自由模式 | 已实现 |
| 预设角色开局 | 已实现 |
| 自然语言行动 + 快捷行动 | 已实现 |
| SSE 流式叙事 | 已实现 |
| 案件板 | 剧本模式已实现 |
| 自由模式侧栏 | 已实现 |
| 暂停 / 恢复 / 重试 | 已实现 |
| 历史会话 | 已实现 |
| 多 Agent 编排 | 已实现 |
| NPC 记忆、反思、关系和日程 | 已实现/部分持续增强 |
| 创作工坊生成世界 | 已实现 |
| 创作工坊生成剧本 | 已实现 |
| 联网检索辅助生成 | 已实现 |
| AI 配图 | 已实现 |
| 草稿发布流程 | 已实现 |
| 多 LLM Provider / Slot 管理 | 已实现 |

## 当前不要承诺的能力

这些不是当前玩家说明里应该承诺的功能：

- 多人同局。
- 分支存档点或回到任意历史分支。
- 任意自定义玩家角色。
- 付费订阅、单世界付费、创作者分成。
- 小程序或原生 App。
- 第三方 OAuth 登录。
- 自动创作者市场和社区审核。
- NPC 在玩家不在场时完整后台模拟每个细节。

## 路由与 API 速查

这部分给 AI 和开发协作者快速对齐，不是玩家说明文案。

| 场景 | 前端路由 | 后端接口 |
|---|---|---|
| 浏览世界 | `/discover` | `GET /api/worlds` |
| 世界详情 | `/worlds/:id` | `GET /api/worlds/:world_id` |
| 开局选择 | `/worlds/:id/start` | `POST /api/game/start` |
| 游玩会话 | `/play/:session_id` | `POST /api/game/:session_id/action` |
| 重试上一轮 | `/play/:session_id` | `POST /api/game/:session_id/retry` |
| 暂停 | `/play/:session_id` | `POST /api/game/:session_id/pause` |
| 恢复 | `/play/:session_id` | `POST /api/game/:session_id/resume` |
| 会话详情 | `/play/:session_id` | `GET /api/game/:session_id/detail` |
| 案件板 | `/play/:session_id` | `GET /api/game/:session_id/case-board` |
| 历史记录 | `/history` | `GET /api/game/history` |
| 创作工坊 | `/workshop` | `/api/workshop/*` |

## AI 快读结构

```yaml
product:
  name: InkWild
  type: AI interactive narrative engine
  promise: choose a world, choose a mode, play through natural-language actions
  core_tension: scripted structure vs open-ended freedom

modes:
  script:
    player_goal: discover truth and reach an ending
    hidden_content: script_setting, events, endings
    ui: case board
    ending: hard conditions plus AI judgment
    should_not_do: reveal truth directly or force a fixed route
  free:
    player_goal: self-defined exploration and roleplay
    hidden_content: NPC secrets and world tensions, not a required main plot
    ui: unified side panel
    ending: no hard forced ending by default
    should_not_do: inject a fake main quest just to create progress

entities:
  world: setting, locations, NPCs, playable characters, cover images
  script: world-bound story line with events and endings
  character: player's entry identity
  session: one playthrough owned by one user
  game_state: current time, location, inventory, clues, relations, events, memory-facing state
  draft: unpublished generated content in workshop

turn_loop:
  - moderate input
  - advance world tick
  - director decides state/NPC/scene/quick actions/case board/ending
  - NPC agents speak or stay silent based on knowledge, trust, mood, schedule and memory
  - narrator writes player-facing prose
  - update state and persist useful memories

voice_rules:
  player_copy: concise, immersive, no system jargon
  narrator: third-person limited, era-consistent, no player mind-reading
  npc: private knowledge boundary, character-consistent, may withhold information
  product_docs: separate player-facing truth from spoiler/internal truth
```

## 维护原则

- 玩家说明优先讲体验，不讲实现细节。
- AI/开发说明可以讲实体、流程、约束，但不要把内部秘密写进公开玩家文案。
- 文档过期时，优先改本文，而不是新增平行产品说明。
- 技术细节参考：
  - `CLAUDE.md`
  - `docs/ARCHITECTURE.md`
  - `docs/modules/orchestrator.md`
  - `docs/modules/world-creator.md`
  - `frontend/AGENTS.md`「Play 页」（旧 play-mode-spec 已并入并归档到 `docs/_archive/`）
