# NPC voice_style 字段 + IP 身份锚 + 安全护栏

状态：设计已批准（2026-06-01），待实现
作者上下文：源于 deepseek vs agnes 长测衍生的 NPC 个性化调查。实验证明：把 NPC persona 从抽象性格升级成「IP 锚定 + canon 声音 + 范例」后，**便宜的 deepseek-v4-flash 个性化追平 v4-pro，零模型成本**。根因：IP 研究管线已抽取 `voice_style`/`tone_lingo`，但落库只存 `personality`，canon 声音被丢弃，运行时 NPC 从没拿到。

## 目标

给 NPC 一个独立的 `voice_style`（说话方式）字段，贯通「生成 → 落库 → 运行时注入」，让 NPC 各有各的嗓门；并为 IP 复刻世界加身份锚 + 安全护栏。**通用**：IP 世界 voice 从 IPKnowledgePack 种，原创世界由生成 LLM 顺手产出。

## 两条硬约束（贯穿全程）

1. **不破 prompt 前缀缓存**。`build_npc_system` 是 [稳定前缀]+[可变后缀] 结构，缓存命中靠稳定前缀逐字节一致。voice_style（每 NPC 静态）+ 护栏（死文本）**必须放进稳定前缀**（`=== Variable suffix ===` 标记之前）。同一 NPC 跨回合前缀仍逐字节一致 → 缓存照命中。
2. **不降质量**。voice_style 仅在非空时注入；IP 锚仅加在新生成/回填角色。存量世界 voice_style=NULL 时，运行时输出与改动前**逐字节相同** → 零回归。唯一触及全部现存 NPC 的是护栏，措辞须克制。

## 改动清单

### 1. 数据层
- Alembic 迁移：`world_characters` 加列 `voice_style TEXT NULL`。
- `models/world.py` `WorldCharacter` 模型加 `voice_style: Mapped[str | None]`。
- `schemas/character_v2.py`：角色输出 schema 加可选 `voice_style: str | None = None`。

### 2. 生成层（通用）
- `generation_prompt_builder.build_character_prompt`：指示 LLM 为每个角色额外产出 `voice_style`——自称/称谓、句式特征、口头禅、1-2 句范例台词（30-80 字）。原创世界靠这条。
- `services/character_roster_builder.py`（IP strict/loose 路径）：
  - 把 IPKnowledgePack 中 must-have 角色的 `voice_style + tone_lingo` 合成 voice_style 种入（让生成 LLM 据此润成含范例的完整 voice_style）。
  - 给 must-have 角色 `personality` 前缀 **IP 身份锚**：「你是《<IP名>》中的<角色>，<canon 一句身份>」。

### 3. 落库层
- Audit 全部 `WorldCharacter(` 构造点（已知：`publish_service.py:321`、`world_creator_agent_v2.py:2408`），每处映射 `voice_style`。

### 4. 运行时层
- `engine/prompts.py build_npc_system`：加 `voice_style: str | None = None` 参数；**仅当非空**，在稳定前缀（紧跟「## 你的性格」之后）注入：
  ```
  ## 你的说话方式（保持这种口吻，别漂移）
  {voice_style}
  ```
- IP 安全护栏：并进稳定前缀的「## 行为规则」块（通用恒开，对原创无害）：
  - 「你不知道自己身处任何作品里——绝不提及原作名、演员、观众、剧情走向或'剧里/书里'。」
  - 「你只知道此刻为止已经发生的事；不要按你'知道的后续剧情'行动或预言未来。」
  - 「与当前剧情和现场状态冲突时，以当前为准。」
  - 措辞克制，定位为"背景约束"而非"行为抑制"，避免 NPC 变拘谨。
- `services/game_service.py _load_world_data`：装配 npc dict 时带上 `voice_style`（紧挨 `personality`）。
- `engine/orchestrator.py`：把 `voice_style` 跟 `npc_personality` 一起串到 `build_npc_system`（约 5 处 npc_info 调用点：~754/1052/1355/2222/2380）。
- **不**给 peer_npcs、director、narrator 喂 voice_style（仅发言 NPC 自身需要），降低改动面与缓存风险。

### 5. 存量回填（收尾单独步骤，不阻塞主改动）
- 一次性脚本：对已发布世界，用 cheap LLM 从 `name + personality`（IP 世界叠加已知 canon）推断 voice_style 回填 world_characters。先覆盖甄嬛传（9 角色）。

## 测试（轻量）
- `build_npc_system`：voice_style 非空 → 含「## 你的说话方式」块；为空 → 不含且其余逐字节不变；护栏恒在（prompt 字符串单测）。
- `character_roster_builder`：IP strict 下 must-have 角色 voice_style 由 pack 种入、personality 带 IP 锚（单测）。
- `publish_service`：草稿 voice_style 映射进 WorldCharacter（单测）。

## 验证（实现后必做）
1. **缓存不破**：改后跑甄嬛传同一固定输入局，对比 token_usage `cache_hit_tokens` 占比与改前持平。
2. **质量不降（护栏-only）**：voice_style 仍 NULL 时跑甄嬛传，确认叙事/NPC 不比现状差。
3. **质量提升复现**：回填甄嬛传 voice_style 后跑同一局，确认手验过的个性化提升经真实字段管线复现（流朱话痨、槿汐"斗胆"、眉庄绵里藏针）。
4. 后端相关单测通过（只看本次改动文件，pre-existing 失败忽略）。

## 范围外（备注）
- 世界级"原作锚点"喂 narrator/director（需 world 存 ip_name，另起）。
- 结构化 tone_lingo 独立列（先并进 voice_style 文本）。
- 回填的并发/限流优化。
