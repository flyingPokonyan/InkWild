# 剧本级可玩角色名单 (Script Playable Roster)

- 日期：2026-06-01
- 状态：设计已确认，待写实现 plan
- 范围：后端（生成 / 发布 / 开局校验）+ 前端（start 页过滤 + 创作工坊编辑器）

## 1. 背景与问题

一个世界的可玩角色（`WorldCharacter.playable == True`）可能很多，但**单个剧本通常只围绕其中一部分主角展开**。`Script.playable_character_ids` 字段早就声明了（`models/script.py:24`），本应表达"这个剧本里可玩的角色子集"，但这条链路从未真正接通：

1. **生成层**：脚本生成的可玩角色建议被存成**角色名字符串**（`world_creator_agent.py:2340`，`_build_script_result` 取 `item.get("name")`），不是 `WorldCharacter` UUID。
2. **发布层**：`apply_script_payload`（`publish_service.py:338-350`）**根本没写**这个字段 → DB 里几乎所有已发布剧本的 `playable_character_ids` 都是默认 `[]`。`normalize_script_payload`（`publish_service.py:233`）也不转发它。
3. **读取层**：`get_world` 返回的 `ScriptDTO`（`api/worlds.py:110-118`）不带该字段；前端 `ScriptDTO` 类型（`types.ts:183`）也没有。
4. **选择层**：start 页角色步骤直接渲染 `world.characters`（`worlds/[id]/start/page.tsx:463`），即**世界全量**可玩角色，与所选剧本无关。
5. **开局层**：`game_service.start_game:149` 只 `db.get(WorldCharacter, character_id)` 验存在性，**既不校验角色属于该世界，也不校验属于该剧本**。

### 后果：选了"不在剧本里"的角色会怎样

不报错——是**静默的剧情质量退化**：

- **该角色被从 NPC 名册抽走**：NPC = 世界里除玩家外的所有角色（`start_game:169-174`）。若剧本把这个角色当关键 NPC（凶手/死者/线索人/对手），该 NPC 消失，剧本引用"他"的桥段全部悬空。
- **谜题完整性破坏 / 剧透**：选到凶手或"秘密即谜底"的角色，导演/旁白会把其 secret 当成玩家已知信息。
- **结局不可达 → 收束失败**：`endings_data` 的硬/软条件围绕预期主角的弧线写；脱离选角的主角起始地点/能力/物品都对不上，事件 trigger 永不触发，故事无法收敛（加重已知 climax 收束脆弱问题）。
- **开局叙事脱节**：开场 prompt 用"玩家扮演 C，抵达 C 的 initial_location"（`start_game:265`），与剧本 `script_setting` 的预期开场对不上。
- **附带漏洞**：`start_game` 不校验 `character.world_id == world.id`，API 层信任客户端传任意 `character_id`。

## 2. 目标 / 非目标

### 目标
- 让 `Script.playable_character_ids` 真正接通：生成时由 AI 建议 → 落库为 UUID → 发布持久化 → API 暴露 → 前端过滤 → 后端校验。
- 创作工坊脚本编辑器支持**手动编辑**剧本可玩角色名单（以 AI 建议为默认值，可增删）。
- 修复 `character.world_id == world.id` 硬化漏洞。

### 非目标（明确不做）
- **不做剧本级角色属性覆盖**：`select_script_playable` 工具会为每个角色生成"该剧本下的 description / abilities / starting_inventory"，但 `Script` 表无处存储，运行时角色描述/能力仍取自 `WorldCharacter`（世界级）。本次**只保留"选了哪些角色"（id 集合）**，丢弃 per-script 文案。per-script 覆盖是更大的特性，列为后续可能跟进项。
- **不写数据迁移回填**：现有剧本保持 `[]`，靠"空=放行全部"语义兼容。
- **不引入 feature flag**：空名单短路即向后兼容。

## 3. 关键决策（已与用户确认）

| 决策 | 选定 |
|---|---|
| 空名单语义 | **空 `playable_character_ids` = 放行世界全部可玩角色**（老剧本零迁移、上线即安全） |
| 授权编辑 UI | **本次一起做**（创作工坊脚本编辑器加可玩角色多选） |
| `world_id` 硬化漏洞 | **本次一起修** |
| 草稿存名字 vs UUID | **存 UUID**（角色改名不影响；编辑器直接按 id 勾选） |
| 生成建议 | 复用**已存在**的 `select_script_playable` + `review_script_playable`，无需新 LLM 工具；但要**修准**（见 A1：候选只给世界可玩角色 + 返回后按名硬过滤 + 数量交回自适应 brief，不写死 3-4） |

## 4. 数据模型与语义

- `Script.playable_character_ids: list[str]` 语义改为 **WorldCharacter UUID 列表**。
- **非空** = 该剧本仅这些角色可玩；**空** = 放行该世界全部 `playable==True` 角色。
- `ScriptDraftPayload` 增 `playable_character_ids: list[str]`（UUID），承载 AI 建议 + 用户编辑。
- 不改表结构（字段已存在、JSON 列）；**无 Alembic 迁移**。

## 5. 实现分层

### A. 数据接通（生成 → 草稿 → 发布 → 读取）

**A1. 生成建议：修准 + 落 UUID**

现状：脚本生成已有完整的可玩角色建议链（`_select_script_playable` → `_review_script_playable`），数量由自适应 `playable_brief` 决定（`recommended_count_target`，`normalize_playable_brief` 钳到 [1,6]，默认 4；prompt 已带"宁缺毋滥/总数不超 N"）。但有两个准确性缺陷 + 一个落库缺陷：

**A1a. 候选池只给"世界可玩角色"**
- `_select_script_playable`（`world_creator_agent.py:2216`）当前把**全部**世界角色（含非可玩 NPC）作为候选 `all_chars` 喂给 prompt（`all_chars = world_data["world_characters"]`，`create_script:1200`）。改为候选池只取 `playable==True` 的角色（`generation_task_service.py:943` 的角色字典已带 `playable` 标记）。这样 AI 不会把 NPC 选成可玩主角，且与"剧本可玩 ⊆ 世界可玩"前提一致。
  - 边界：若世界 0 个可玩角色（已发布世界不该出现）→ 回退全量或跳过该步。

**A1b. 返回后按名硬过滤（不只是 warning）**
- `_select_script_playable` 与 `_review_script_playable` 拿到工具结果后，**先按"世界可玩角色名集合"做归一化精确匹配过滤**，丢弃幻觉名/非可玩名，再走 `_limit_playable_recommendations`。每个被丢弃的名字记一条 `quality_warning`。
  - 现状 `_validate_script`（`world_creator_agent.py:809`）只对越界名字**警告**、不剔除 → 把"剔除"提前到选择/复检出口，做到"绝不把不存在/非可玩的人设为可玩"。
- 这样 A1d 的 name→id 解析变成干净查表（每个存活名字都能映射到真实可玩 WorldCharacter id）。与发布期 A3 过滤构成双保险。

**A1c. 数量不写死 3-4（交回自适应 brief）**
- 根因：`SCRIPT_PLAYABLE_TOOL` 的 schema 描述（`world_creator_agent.py:371`）硬编码"3-4个可选角色"，**与自适应 brief 打架**——brief 可能给 1（单主角本格推理）或 6（群像本）。
- 改：把该静态描述改成 brief 中性措辞（如"按推荐策略返回核心可玩角色；数量以提示词中的推荐数量为准，宁缺毋滥，不要凑数"），让真正的数量约束来自 prompt（`generation_prompt_builder.py:146-148` 已写）+ `_limit_playable_recommendations`（按 `recommended_count_target` 截断）。
- 对称修世界侧 `PLAYABLE_TOOL` 描述（`world_creator_agent.py:274`）同样的"3-4"硬编码（世界侧候选是"定义谁可玩"，名校验仍按"存在于人物表"，不是 playable 子集）。
- 结果：可玩角色数量随题材自适应（本格单视角 → 1-2；群像 → 5-6），不再钉死 3-4。

**A1d. 落 UUID**
- `generation_task_service.py:943` 构造 `world_data["world_characters"]` 时**补 `"id": str(wc.id)`**（当前只有 name，下游无法解析）；`api/admin.py` 的 world_data builder 同步补 id。
- `_build_script_result`（`world_creator_agent.py:~2300-2341`）：`playable_character_ids` 从"取 name"改为**按 world 角色 name→id 映射解析成 UUID**（经 A1b 过滤后必能匹配）。

**A1e. 生产路径是 V2（实现时发现，关键）**
- `world_creator_v2_enabled` 默认 True，脚本生成走 `WorldCreatorAgentV2.create_script`，**不经过上面 base agent 的 `select_script_playable`/`_build_script_result`**。V2 原本只产出 `playable`（name/role/personality），**完全不产 `playable_character_ids`** → 若不修，每个 V2 生成的剧本名单恒为空。
- 已修：V2 `create_script` 的 final_payload 增 `playable_character_ids`，由 `_select_script_playable_v2` 选出的名字按 world 角色 **name→id 解析、且只取 world-playable**（保证 ⊆ 世界可玩 + 不含幻觉/NPC）。
- 注意 **V2 的选择是规则式（is_image_target/playable/role_tag），非 LLM 按剧情定制**——默认名单 ≈ 世界全部可玩角色，由创作者在编辑器收窄。base agent 的 LLM `select_script_playable`（A1a–A1c 的"修准"）只在 v2 关闭时生效。若要 V2 也做"按剧情定制"的 AI 建议，是另一项增强。

**A2. 草稿持久化**
- `normalize_script_payload`（`publish_service.py:233`）：将 `playable_character_ids` 纳入 normalized 输出（默认 `[]`）。
- `generation_task_service` 写 `ScriptDraft.payload` 时携带该字段（经 A1 已是 UUID）。

**A3. 发布持久化 + 防腐过滤**
- `apply_script_payload`（`publish_service.py:338`）：`script.playable_character_ids = [id for id in payload.get("playable_character_ids", []) if id in 当前 world 的 playable 角色 id 集合]`。
  - 需要 world 当前 `playable==True` 的 WorldCharacter id 集合 → `apply_script_payload` 目前是同步纯函数、无 db。方案：把过滤所需的 `valid_ids` 由调用方（已 await 过 world 角色的发布流程）传入，或将该函数改为 async 接收 db。**实现 plan 里定**：倾向把 `valid_playable_ids: set[str]` 作为参数传入，保持函数可测。
  - 过滤后仍可能为空（建议全被删/失效）→ 落库 `[]` → 运行时自动 allow-all，安全。

**A4. API 暴露**
- `ScriptDTO`（后端 `schemas/world.py` 或 `api/worlds.py` 内联）+ 前端 `types.ts:183` 增 `playable_character_ids: list[str]`。
- `get_world`（`api/worlds.py:110`）填充该字段。

### B. 前端 start 页过滤

- 新增纯函数 `resolvePlayableCharacters(world, script)` 进 `lib/world-entry.ts`：
  - 自由模式 / 隐式剧本 / 名单为空 → 返回 `world.characters`（全量）。
  - 剧本模式且名单非空 → 返回 `world.characters.filter(c => script.playable_character_ids.includes(c.id))`；若过滤后为空（异常）→ 回退全量。
- `worlds/[id]/start/page.tsx:463`：角色步骤改用 `resolvePlayableCharacters(world, selectedScript)` 而非 `world.characters`。
- `getInitialWorldSelection`（`world-entry.ts:73`）：默认选中的 character 要落在"首个剧本的可玩集合"内；start 页 `selectScript` 切换剧本时，若当前已选 character 不在新剧本名单内，清空/重选。
- 自由模式路径完全不变。
- vitest 覆盖 `resolvePlayableCharacters` + 默认选中纯函数。

### C. 后端开局校验

`game_service.start_game`（`game_service.py:149` 之后）：
- **C1（硬化）**：`character` 取出后校验 `str(character.world_id) == str(world.id)`，否则 `AppError(40002, "角色不存在")`（不泄露细节）。
- **C2（名单）**：`mode == "script"` 且 `resolved_script` 的 `playable_character_ids` 非空时，校验 `character.id in playable_character_ids`，否则 `AppError(40009, "该角色不在此剧本中")`。
  - 注意：`resolved_script_id` 已在 154-165 解出，需把 `script` 对象（含 `playable_character_ids`）一起留用。
- 确认 40009 未被占用（现有用到 40001/40002/40004/40005/40006/40007/40008）。
- 前端 `stores/game.ts` / start 页对新错误码给出可读提示（"该角色不属于此剧本，请重新选择"）。

### D. 授权编辑 UI + 生成建议落地（创作工坊脚本编辑器）

**D1. 后端：把世界可玩角色清单喂给编辑器**
- `_script_draft_detail`（`api/workshop.py:261`）响应增 `world_playable_characters: [{id, name, avatar}]`——服务端按 `draft.world_id` join `WorldCharacter (playable==True)`。
  - 理由：脚本编辑器当前拿不到世界角色（`scripts/drafts/[id]/page.tsx:92-95` 明确 `knownNpcs = []`）；服务端 join 兼容私有世界、省二次请求。
  - `_script_draft_detail` 当前是同步函数、无 db → 改为 async 或由各 handler 预查后传入。实现 plan 定。
- `update_script_draft`（`api/workshop.py:987`）：接受 payload 内 `playable_character_ids` 并写回草稿。

**D2. 前端：脚本编辑器加"可玩角色"小节**
- `frontend/lib/types.ts`：`ScriptDraftPayload` 增 `playable_character_ids: string[]`；`AdminScriptDraftDetail` 增 `world_playable_characters`。
- `frontend/lib/draft-schemas.ts`：脚本空 payload 默认 `playable_character_ids: []`。
- `workshop/scripts/drafts/[id]/page.tsx`：在"基础"小节后新增 `section-playable`（rail 加一项），渲染**头像+名字的多选 checklist**（数据源 `detail.world_playable_characters`），勾选写入 `payload.playable_character_ids`。
  - 复用现有 editor 原子组件；如无合适的多选，新增轻量 `components/admin/editor/fields/CharacterPicker.tsx`（≥44px 触摸目标、复用 token）。
  - AI 生成的建议（A1 落进 payload 的 UUID）作为**默认勾选项**，用户可增删——满足"生成时给建议"。
  - 空选 = 放行全部，UI 给一行说明文案。
- `ScriptPreviewPane`（`components/admin/editor/preview/ScriptPreviewPane.tsx`）：轻量展示已选角色名。
- i18n：`i18n/zh.json` + `en.json` 补 `admin.editor.script.sections.playable` 等文案。

## 6. 错误处理与边界

| 场景 | 行为 |
|---|---|
| 剧本名单为空 | 放行世界全部可玩角色（前后端一致） |
| 名单含已删除/已变 non-playable 的 id | 发布时过滤（A3）；读取时 `get_world` 也只返回现存 playable 角色，前端 filter 自然忽略失效 id |
| 前端过滤后为空 | 回退全量（防止无角色可选） |
| 客户端绕过前端直传非名单角色 | 后端 C2 拦截 → 40009 |
| 客户端传跨世界 character_id | 后端 C1 拦截 → 40002 |

## 7. 测试

**后端（pytest）**
- `start_game`：①名单非空时拒绝非名单角色（40009）②接受名单内角色 ③空名单 allow-all ④跨世界角色拒绝（40002）。
- `apply_script_payload`：name→id 已是 UUID 时原样写；过滤掉失效/非 playable id；全失效 → `[]`。
- `_build_script_result`：名字解析成 UUID；未匹配名字丢弃 + warning。
- 生成建议修准（纯函数层，不打真 LLM）：①候选池只含 playable 角色；②`_select_script_playable` / `_review_script_playable` 出口把幻觉名/非可玩名过滤掉 + 出 warning；③数量随 `playable_brief.recommended_count_target` 截断（给 brief=1 / brief=6 两组断言不写死 3-4）。可把"按名过滤 + 截断"抽成可单测的纯函数。
- 注意 `get_db` 测试覆盖坑：新路由若用到 db 依赖，确保 `from dependencies import get_db`。

**前端（vitest）**
- `resolvePlayableCharacters`：自由/隐式/空名单 → 全量；非空 → 子集；过滤空 → 回退。
- `getInitialWorldSelection`：默认 character 落在首个剧本名单内。

## 8. 兼容 / 回滚

- 无表结构变更、无迁移。
- 老剧本 `playable_character_ids == []` → 全链路 allow-all，行为与今日一致。
- 回滚 = 还原代码即可，无数据残留风险。

## 9. 受影响文件清单

**后端**
- `services/world_creator_agent.py` — A1：`SCRIPT_PLAYABLE_TOOL`/`PLAYABLE_TOOL` 描述去掉硬编码"3-4"；`_select_script_playable`/`_review_script_playable` 候选池限 playable + 出口按名硬过滤；`_build_script_result` 名字→UUID 解析
- `services/generation_task_service.py` — `world_data` 角色补 `id`（~943）
- `services/publish_service.py` — `normalize_script_payload`（233）+ `apply_script_payload`（338）
- `api/worlds.py` — `ScriptDTO` 增字段（110）
- `api/workshop.py` — `_script_draft_detail`（261）增 `world_playable_characters`、`update_script_draft`（987）
- `services/game_service.py` — `start_game` C1+C2 校验（149+）
- `schemas/world.py`（若 ScriptDTO 在此）

**前端**
- `lib/types.ts` — `ScriptDTO` / `ScriptDraftPayload` / `AdminScriptDraftDetail`
- `lib/world-entry.ts` — `resolvePlayableCharacters` + 默认选中
- `lib/draft-schemas.ts` — 脚本空 payload 默认
- `app/worlds/[id]/start/page.tsx` — 角色步骤过滤
- `app/workshop/scripts/drafts/[id]/page.tsx` — 可玩角色小节
- `components/admin/editor/fields/CharacterPicker.tsx`（新增，按需）
- `components/admin/editor/preview/ScriptPreviewPane.tsx` — 展示已选
- `stores/game.ts` / start 页 — 40009 错误文案
- `i18n/zh.json` + `en.json`

**测试**
- `backend/tests/` — start_game 校验、publish 过滤、build_script_result 解析
- `frontend/lib/world-entry.test.ts` — 过滤 + 默认选中
