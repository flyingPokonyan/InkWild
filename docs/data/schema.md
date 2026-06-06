# 数据库 Schema 参考

> 状态截至 2026-05-08。覆盖所有 Alembic 已上 head 的表（head = `9b3c4d5e6f7a`）。字段名 / 类型逐字从 `backend/models/*.py` + `backend/migrations/versions/*.py` 复制；含义来自代码注释 + Phase 任务上下文。

字段背后的 phase 任务用 `（0.A.X / 1.A.X / 1.B.X / 2.D.X）` 标注；migration revision id 在每个表的"引入记录"里给出，方便交叉对查 `MIGRATION_NOTES.md`。

---

## 1. 概览

按域划分，InkWild 当前共 **23 张表**：

```
用户域 (3)
   users ─┬─ auth_identities (provider, provider_user_id)
          └─ web_sessions    (cookie session)

内容域 — 已发布世界 / 剧本 (7)
   worlds ─┬─ world_characters  (NPC + 可玩主角统一表)
           ├─ events            (世界事件)
           ├─ endings           (剧本结局)
           ├─ scripts           (剧情线，附属于 world)
           ├─ npcs              (legacy，已弃用，未删)
           └─ characters        (legacy，已弃用，未删)

会话域 (5)
   game_sessions ─┬─ messages              (对话流水 + npc_dialogues)
                  ├─ memory_entries        (结构化记忆 + embedding)
                  ├─ npc_reflections       (NPC 长期内心总结)
                  ├─ npc_relations         (NPC↔NPC 持久关系)
                  ├─ case_board_history    (案件板增量 ops)
                  └─ token_usage           (单局 LLM 计费)

创作工坊域 (4)
   world_drafts / script_drafts                (草稿 → 发布)
   generation_tasks ── generation_task_events  (AI 生成任务 + SSE 事件流)

模型管理域 (4)
   model_providers ── provider_models ── model_slot_bindings
                                       └─ model_capability_probes

审计域 (1)
   admin_audit_logs

计费域 — 实际归属 "会话域"
   token_usage（单独列说明：跨域 - 既挂在 session_id 也是计费/分析视角）
```

关系总览（粗箭头表示 FK）：

```
users ──< game_sessions >── worlds ──< world_characters
                                 │           ▲
                                 ├──< scripts (剧本绑定 world)
                                 ├──< events
                                 └──< endings

game_sessions ──< messages
              ├──< memory_entries
              ├──< npc_reflections
              ├──< npc_relations
              ├──< case_board_history
              └──< token_usage

generation_tasks ──< generation_task_events  (按 seq 顺序回放)
world_drafts ─?─ worlds        (发布后 world_id 反向 FK；草稿创建时为 NULL)
script_drafts ─?─ scripts      (同上)

model_providers ──< provider_models ──< model_slot_bindings
                                     └─< model_capability_probes
```

---

## 2. 各表详解

### 2.1 `users` — 用户主体

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid(as_uuid=False)` | no | 主键 |
| `status` | `String(20)` | no | `active` / 禁用等 |
| `is_admin` | `Boolean` | no | admin 权限标记（取代废弃的 `X-Admin-Key`） |
| `nickname` | `String(50)` | yes | 昵称 |
| `avatar_url` | `String(500)` | yes | 头像 URL |
| `created_at` | `datetime` | no | utcnow |
| `updated_at` | `datetime` | no | utcnow，onupdate |
| `last_login_at` | `datetime` | yes | 最近登录 |

引入：`c6f6a2f4f8d1_add_user_auth_tables`；`is_admin` 列由 `2c8b7e5a9d01_add_user_is_admin` 追加（首批 admin 需手动 SQL `UPDATE`）。

设计要点：用户表不挂凭证，凭证落 `auth_identities`，支持同一 user 多种登录方式（邮箱 + 微信 等）通过 `union_id` 收敛。

### 2.2 `auth_identities` — 多登录方式映射

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid(as_uuid=False)` | no | 主键 |
| `user_id` | `Uuid` FK→`users.id` | no | 关联用户 |
| `provider` | `String(32)` | no | `email` / `wechat` / `google`... |
| `provider_user_id` | `String(191)` | no | 该 provider 下的稳定用户 id |
| `credential_hash` | `Text` | yes | 邮箱密码场景存 bcrypt；OAuth 场景为空 |
| `email` | `String(255)` | yes | 冗余 email（便于反查） |
| `phone` | `String(32)` | yes | 冗余手机号 |
| `union_id` | `String(191)` | yes | 微信 unionid 等同账号收敛 id |
| `profile` | `JSON` | no | provider 返回的原始 profile（默认 `{}`） |
| `created_at` | `datetime` | no | |
| `last_login_at` | `datetime` | yes | |

约束：`UNIQUE (provider, provider_user_id)` = `uq_auth_identity_provider_user`；`INDEX (user_id)`、`INDEX (union_id)`。

### 2.3 `web_sessions` — 浏览器会话

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | 主键，同时是 cookie 值 |
| `user_id` | `Uuid` FK→`users.id` | no | |
| `expires_at` | `datetime` | no | 过期时间 |
| `created_at` | `datetime` | no | |
| `last_seen_at` | `datetime` | no | 每次请求刷新 |
| `user_agent` | `String(500)` | yes | UA 留痕 |
| `ip_address` | `String(64)` | yes | IP 留痕 |

`INDEX (user_id)`、`INDEX (expires_at)`（清理过期任务用）。

### 2.4 `worlds` — 世界（舞台）

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | 主键 |
| `name` | `String(100)` | no | |
| `description` | `Text` | no | 简介 |
| `genre` | `String(50)` | no | 类型（民国 / 赛博 / 武侠...） |
| `era` | `String(50)` | no | 时代 |
| `difficulty` | `SmallInteger` | no | 难度 1-5 |
| `estimated_time` | `String(50)` | no | 预估时长文案 |
| `cover_image` | `String(500)` | no（默认 `""`） | 封面图 |
| `poster_image` | `String(500)` | no | 海报图（`e4b3c2d1f0a9` 引入） |
| `hero_image` | `String(500)` | no | 详情页大图（`e4b3c2d1f0a9` 引入） |
| `base_setting` | `Text` | no | 世界观（NPC / Director 共享） |
| `locations_data` | `JSON` | no（默认 `[]`） | 地点列表（`b1f5c4d9e2a1` 引入） |
| `script_setting` | `Text` | yes | 剧本核心秘密（仅 Director 可见） |
| `free_setting` | `Text` | yes | 自由模式额外设定 |
| `status` | `String(20)` | no（默认 `published`） | 发布状态 |
| `play_count` | `Integer` | no | 累计游玩次数 |
| `free_playable_character_ids` | `JSON` | no | 自由模式可玩角色 id 列表（`01f437c7c05d` 引入） |
| `created_at` | `datetime` | no | |

设计：`base_setting` vs `script_setting` 是关键边界——前者 NPC 看，后者只有 Director 看（防止剧透）。`free_setting` 给纯沙盒模式补充背景。

### 2.5 `world_characters` — 角色（NPC + 可玩主角统一表）

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | |
| `world_id` | `Uuid` FK→`worlds.id`, indexed | no | |
| `name` | `String(50)` | no | |
| `personality` | `Text` | no（默认 `""`） | 性格 |
| `secret` | `Text` | yes | NPC 秘密（玩家不该直接得知） |
| `knowledge` | `JSON` | no（默认 `[]`） | 开局前角色已知事项 |
| `schedule` | `JSON` | no（默认 `{}`） | `{time_slot: location}` |
| `initial_location` | `String(100)` | no（默认 `""`） | |
| `playable` | `Boolean`, indexed | no（默认 `False`） | 是否可作为玩家角色 |
| `description` | `Text` | yes | playable=True 时使用 |
| `abilities` | `JSON` | no（默认 `[]`） | 主角技能 |
| `starting_inventory` | `JSON` | no（默认 `[]`） | 起始物品 |
| `avatar` | `String(500)` | yes | 头像（`d3a1b2c4e5f6` 引入） |
| `mode` | `String(20)` | no（默认 `both`） | `script` / `free` / `both` |
| `initial_peer_relations` | `JSON` | yes | NPC-2：`[{target, trust, label, history_summary}]`，session 启动时灌 `npc_relations`（`7f2c3d4e5a08` 引入） |
| `created_at` | `datetime` | no | |

引入：`01f437c7c05d_add_world_characters_table`（合并 legacy `npcs` + `characters` 两张表为一张统一表）。`game_sessions.character_id` 后续 FK 切到这里（`a21226f5c969`）。

常见查询：`SELECT * WHERE world_id=? AND id != self_id`（同场 NPC 列表）— 见 `services/game_service.py`。

### 2.6 `npcs` / `characters` — Legacy（弃用未删）

`045766d633e1_initial_schema` 创建的旧表。代码注释明确写"Legacy table — kept temporarily for migration. Use WorldCharacter instead."。当前 `services/` `engine/` `seeds/` 都不再读写，仅 `models/__init__.py` 还导出（保持 metadata 完整避免 alembic autogen 误删）。

候选清理：未来确认无 ETL / 备份脚本依赖后可一次性 drop。

### 2.7 `events` — 世界事件

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | |
| `world_id` | `Uuid` FK→`worlds.id` | no | |
| `name` | `String(100)` | no | |
| `trigger_type` | `String(50)` | no | 触发条件类型（`7b9e4a1d2c3f` 把 20→50） |
| `trigger_condition` | `JSON` | no | 触发条件细节 |
| `description` | `Text` | no | |
| `effects` | `JSON` | no | 触发后效果 |
| `mode` | `String(20)` | no（默认 `both`） | |
| `priority` | `SmallInteger` | no | |

### 2.8 `endings` — 剧本结局

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | |
| `world_id` | `Uuid` FK | no | |
| `ending_type` | `String(50)` | no | `good` / `bad` / `true`... |
| `title` | `String(100)` | no | |
| `description` | `Text` | no | |
| `priority` | `SmallInteger` | no | |
| `hard_conditions` | `JSON` | yes | 硬性触发条件 |
| `soft_conditions` | `Text` | yes | 软性条件（自然语言，LLM 判定） |
| `mode` | `String(20)` | no（默认 `script_only`） | |

### 2.9 `scripts` — 剧本

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | |
| `world_id` | `Uuid` FK→`worlds.id` | no | |
| `name` | `String(100)` | no | |
| `description` | `Text` | no | |
| `difficulty` | `SmallInteger` | no（默认 `3`） | |
| `estimated_time` | `String(50)` | no（默认 `"30-60 min"`） | |
| `events_data` | `JSON` | no（默认 `[]`） | 事件 inline |
| `clues_data` | `JSON` | no（默认 `{}`） | 线索 inline |
| `endings_data` | `JSON` | no（默认 `[]`） | 结局 inline |
| `script_setting` | `Text` | no（默认 `""`） | 该剧本的核心秘密 |
| `playable_character_ids` | `JSON` | no（默认 `[]`） | |
| `cover_image` | `String(500)` | yes | （`d3a1b2c4e5f6` 引入） |
| `script_type` | `String(30)` | no（默认 `mystery`） | （`5561197da50c` 引入） |
| `is_published` | `Boolean` | no（默认 `False`） | 草稿/已发布门 |
| `created_at` | `datetime` | no | |

引入：`472da503b7df_add_scripts_table_and_session_fields`。Script 是独立实体，不只是 world 上的字段——`game_sessions.script_id` 选填，剧本模式才指。

### 2.10 `world_drafts` / `script_drafts` — 创作工坊草稿

`world_drafts`：

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | |
| `world_id` | `Uuid` FK→`worlds.id`, **UNIQUE** | yes | 发布前 NULL；发布后回填 |
| `payload` | `JSON` | no（默认 `{}`） | 整个草稿内容 |
| `created_at` / `updated_at` | `datetime` | no | |

`script_drafts`：

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | |
| `world_id` | `Uuid` FK→`worlds.id` | no | 草稿一定挂在某个 world 下 |
| `script_id` | `Uuid` FK→`scripts.id`, **UNIQUE** | yes | 发布后回填 |
| `payload` | `JSON` | no | |
| `created_at` / `updated_at` | `datetime` | no | |

引入：`b1f5c4d9e2a1_add_world_and_script_drafts`。`script_drafts` 加 `INDEX (world_id)`。

### 2.11 `generation_tasks` — 创作工坊 AI 生成任务

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | |
| `kind` | `String(20)` | no | `world` / `script` |
| `draft_type` | `String(20)` | no | 同 kind，便于按草稿类型查 |
| `draft_id` | `Uuid`, indexed | no | 关联 draft 表 id |
| `status` | `String(20)`, indexed | no（默认 `pending`） | `pending` / `running` / `succeeded` / `failed` |
| `request_payload` | `JSON` | no | 用户输入快照 |
| `current_phase` | `String(50)` | yes | 当前阶段（前端显示） |
| `current_code` | `String(50)` | yes | 当前事件码 |
| `current_message` | `Text` | yes | |
| `last_event_seq` | `Integer` | no（默认 `0`） | SSE 续传用游标 |
| `error_message` | `Text` | yes | |
| `started_at` | `datetime` | yes | |
| `finished_at` | `datetime` | yes | |
| `created_at` / `updated_at` | `datetime` | no | |

引入：`9d1a2b3c4d5e_add_generation_tasks`。

### 2.12 `generation_task_events` — SSE 事件流持久化

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | |
| `task_id` | `Uuid` FK→`generation_tasks.id`, indexed | no | |
| `seq` | `Integer` | no | 单调递增，断线续传时按 `> seq` 拉 |
| `event_name` | `String(20)` | no | 事件类型 |
| `payload` | `JSON` | no | |
| `created_at` | `datetime` | no | |

事件 schema 和前端 `frontend/lib/admin-sse-events.ts` 保持同步——新增事件类型必须前后端一起改。

### 2.13 `game_sessions` — 游戏会话主记录

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | |
| `user_id` | `Uuid` FK→`users.id` | no | 取代废弃的 `player_id`（`c6f6a2f4f8d1` 重建） |
| `world_id` | `Uuid` FK→`worlds.id` | no | |
| `character_id` | `Uuid` FK→`world_characters.id` | no | （`a21226f5c969` 切 FK） |
| `script_id` | `Uuid` FK→`scripts.id` | yes | free 模式为 NULL |
| `authors_note` | `Text` | yes | 玩家自留备注 |
| `state_snapshot` | `JSON` | yes | 用于 retry / resume |
| `last_action_text` | `Text` | yes | 最近动作文本，retry 时复用 |
| `retry_count` | `Integer` | no（默认 `0`） | retry 次数 |
| `version` | `Integer` | no（默认 `0`） | 乐观锁版本号（`0a5b6c7d8e9f` 引入），写时 `WHERE version=?` 冲突回 409 |
| `mode` | `String(20)` | no | `script` / `free` |
| `status` | `String(20)` | no（默认 `playing`） | `playing` / `ended` |
| `game_state` | `JSON` | no（默认 `{}`） | 完整运行时状态（NPC trust / mood / intent / case_board / 时间 等） |
| `context_summary` | `Text` | yes | 压缩后的对话摘要 |
| `ending_type` | `String(50)` | yes | 结束后的结局类型 |
| `rounds_played` | `Integer` | no | |
| `started_at` | `datetime` | no | |
| `last_played_at` | `datetime` | no | |
| `ended_at` | `datetime` | yes | |

索引：`idx_game_sessions_user_status (user_id, status)`、`idx_game_sessions_user_last_played (user_id, last_played_at)`、`idx_game_sessions_world_id (world_id)`（`8a2b1c3d4e5f` 后加，便于 admin 按 world 聚合）。

设计要点：
- `game_state` 是个大 JSON——所有运行时状态（包括 case_board 当前快照）都在这里。`case_board_history` 是这份快照的增量历史。
- `version` 字段是 SessionLock 之外的第二层保护，跨进程也能用。
- `state_snapshot` + `last_action_text` 是 retry 路径的核心——retry 时回滚到 snapshot 再用 last_action_text 重跑。

### 2.14 `messages` — 对话流水

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Integer` autoincrement | no | |
| `session_id` | `Uuid` FK→`game_sessions.id` | no | |
| `role` | `String(20)` | no | `user` / `assistant` |
| `content` | `Text` | no | 完整文本（玩家 action / narrator 输出） |
| `state_snapshot` | `JSON` | yes | 这一轮结束后的状态快照（debug / 回放） |
| `npc_dialogues` | `JSON` | yes | `{npc_name: dialogue_text}`（1.B.4 voice anchor 用，`5d0a1b2c3e06` 引入） |
| `is_compressed` | `Boolean` | no | 是否已被压缩进 `context_summary` |
| `created_at` | `datetime` | no | |

索引：`idx_messages_session_created (session_id, created_at)`、`idx_messages_session_compressed (session_id, is_compressed)`、`idx_messages_session_role (session_id, role)`（`8a2b1c3d4e5f` 加，replay/exporter 加速）。

### 2.15 `memory_entries` — 结构化记忆

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Integer` autoincrement | no | |
| `session_id` | `Uuid` FK | no | |
| `memory_type` | `String(30)` | no | `event` / `dialogue` / `director_told` 等 |
| `content` | `Text` | no | 记忆文本 |
| `round_number` | `Integer` | no | 发生回合 |
| `importance` | `SmallInteger` | no（默认 `5`） | 1-10 |
| `related_npc` | `String(50)` | yes | NPC 隔离锚点（0.A.3，`f5a2b3c4d6e7` 引入），NULL = 全局事实 |
| `embedding` | `JSON list[float] \| None` | yes | 向量召回（1.B.2，`3b8d9e1c2f04` 引入），NULL 时回落 importance 排序 |
| `created_at` | `datetime` | no | |

索引：`idx_memory_session (session_id)`、`idx_memory_session_type (session_id, memory_type)`、`idx_memory_npc (session_id, related_npc)`。

设计：JSON 存 embedding 而非 pgvector，是为了 SQLite 测试也能跑；未来 PG 切 pgvector 可原地迁。

### 2.16 `npc_reflections` — NPC 长期内心总结

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Integer` autoincrement | no | |
| `session_id` | `Uuid` FK | no | |
| `npc_name` | `String(50)` | no | |
| `summary` | `Text` | no | 第一人称内心总结 |
| `last_memory_id` | `Integer` | no（默认 `0`） | 上次反思覆盖到的最大 `memory_entries.id` |
| `reflection_count` | `Integer` | no（默认 `1`） | 反思次数（telemetry） |
| `created_at` / `updated_at` | `datetime` | no | |

约束：`UNIQUE (session_id, npc_name)` = `uq_npc_reflections_session_npc`；`INDEX (session_id)`。

引入：`4c9e0f2d3a05_add_npc_reflections`（Phase 1.B "NPC reflection"）。触发逻辑：累积 ≥ `NPC_REFLECTION_THRESHOLD`（默认 5）条新 memory 时 `services/npc_reflection_service.py` 重新提炼。

### 2.17 `npc_relations` — NPC↔NPC 持久关系

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Integer` autoincrement | no | |
| `session_id` | `Uuid` FK | no | |
| `npc_a` | `String(50)` | no | 主语（"A 怎么看 B"） |
| `npc_b` | `String(50)` | no | 宾语 |
| `trust` | `SmallInteger` | no（默认 `0`） | 硬限 [-10, 10] |
| `relationship_label` | `String(50)` | yes | `邻居` / `情敌`... |
| `history_summary` | `Text` | yes | 一句话过去摘要 |
| `last_event_round` | `SmallInteger` | no（默认 `0`） | NPC-3 用；NPC-2 阶段恒 0 |
| `created_at` / `updated_at` | `datetime` | no | |

约束：`UNIQUE (session_id, npc_a, npc_b)` = `uq_npc_relations_session_pair`；`INDEX (session_id, npc_a)`。

引入：`6e1b2c3d4f07_add_npc_relations`（NPC-2）。Session 启动时由 `services/game_service.py::_seed_npc_relations` 从 `world_characters.initial_peer_relations` 双向灌入。当前 read-only：NPC-3 后台模拟启用后才会改写。

### 2.18 `case_board_history` — 案件板增量 ops

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Integer` autoincrement | no | |
| `session_id` | `Uuid` FK | no | |
| `round_number` | `Integer` | no | |
| `op_type` | `String(50)` | no | `add` / `remove` / `update` 等 |
| `path` | `JSON list` | no | JSON pointer 风格的路径 |
| `payload` | `JSON dict` | no | op 参数 |
| `before` | `JSON \| None` | yes | 改前值 |
| `after` | `JSON \| None` | yes | 改后值 |
| `reason` | `Text` | yes | Director 解释 |
| `created_at` | `datetime` | no | |

索引：`idx_case_board_history_session_id`、`idx_case_board_history_session_id_id`。

引入：`2a7c9d4e1f03_add_case_board_history`。`MIGRATION_NOTES.md` 已记录：从 director snapshot 改为 ops 序列，当前快照仍存在 `game_sessions.game_state.case_board`，本表是该快照的增量审计 + 回放数据。

### 2.19 `token_usage` — 单局 LLM token / cost

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Integer` autoincrement | no | |
| `session_id` | `Uuid` FK | no | |
| `provider` | `String(20)` | no | 短类型（`claude` / `deepseek`...），legacy |
| `model` | `String(50)` | no | 模型短名，legacy |
| `provider_name` | `String(64)` | yes | 完整 provider name（2.D.1，`9b3c4d5e6f7a` 引入） |
| `model_id` | `String(255)` | yes | 完整 model id（2.D.1） |
| `input_tokens` | `Integer` | no | |
| `output_tokens` | `Integer` | no | |
| `cost_cents` | `Integer` | no（默认 `0`） | 折成 cent 的成本 |
| `created_at` | `datetime` | no | |

索引：`idx_token_usage_session`、`idx_token_usage_created`。

设计取舍：legacy `provider` / `model` 列保留没删，只为老数据兼容；新写都填 `provider_name` / `model_id`。Phase 2 单局 cost guardrail 看的是新列。

### 2.20 `model_providers` — LLM 厂商

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | |
| `name` | `String(80)` | no | |
| `provider_type` | `String(32)` | no | `claude` / `deepseek` / `openai_compatible`... |
| `base_url` | `String(500)` | yes | OpenAI 兼容端点 |
| `api_key_env_name` | `String(80)` | no | 凭据放 env var，DB 只存名字 |
| `extra_config` | `JSON` | no（默认 `{}`） | provider 特定配置 |
| `status` | `String(20)` | no（默认 `active`） | |
| `last_healthcheck_at` | `datetime` | yes | |
| `last_healthcheck_error` | `Text` | yes | |
| `created_at` / `updated_at` | `datetime` | no | |

约束：`UNIQUE (name)` = `uq_model_providers_name`；`INDEX (provider_type, status)`。

### 2.21 `provider_models` — 每个 provider 暴露的具体模型

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | |
| `provider_id` | `Uuid` FK→`model_providers.id` | no | |
| `model_id` | `String(120)` | no | provider 内的模型标识 |
| `display_name` | `String(120)` | no | |
| `model_kind` | `String(16)` | no | `text` / `image` / `embedding` |
| `is_enabled` | `Boolean` | no | 是否启用 |
| `notes` | `Text` | yes | |
| `created_at` / `updated_at` | `datetime` | no | |

约束：`UNIQUE (provider_id, model_id, model_kind)` = `uq_provider_models_identity`；`INDEX (provider_id, model_kind)`。

### 2.22 `model_slot_bindings` — 业务 slot → 模型动态绑定

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | |
| `slot_name` | `String(50)`, **UNIQUE** + indexed | no | `game_main` / `npc_agent` / `narrator` / `conversation_compression` / `moderation` / `image` / `embedding`... |
| `model_id` | `Uuid` FK→`provider_models.id` | no | |
| `status` | `String(20)` | no（默认 `active`） | |
| `last_verified_at` | `datetime` | yes | |
| `last_verified_error` | `Text` | yes | |
| `created_at` / `updated_at` | `datetime` | no | |

注意：表名 `model_slot_bindings`（DB），ORM 类名 `ModelSlotBinding`（代码里有时简写为 `model_slots`，但实际表名是 `model_slot_bindings`）。Slot 名跟代码里 `LLMRouter` 的常量同步。

### 2.23 `model_capability_probes` — 模型能力探测结果

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | |
| `model_id` | `Uuid` FK→`provider_models.id` | no | |
| `capability` | `String(32)` | no | `chat` / `tool_use` / `streaming`... |
| `status` | `String(20)` | no | `ok` / `failed` / `unknown` |
| `latency_ms` | `Integer` | no（默认 `0`） | |
| `error_message` | `Text` | yes | |
| `response_sample` | `Text` | yes | |
| `verified_at` | `datetime` | no | |
| `expires_at` | `datetime` | yes | 探测结果有效期 |

索引：`idx_model_capability_probes_model_capability (model_id, capability)`、`idx_model_capability_probes_verified_at`。

### 2.24 `admin_audit_logs` — Admin 写操作审计

| 字段 | 类型 | nullable | 含义 |
|---|---|---|---|
| `id` | `Uuid` | no | |
| `admin_user_id` | `Uuid` FK→`users.id` (`ON DELETE SET NULL`) | yes | 删除 admin 后保留日志 |
| `action` | `String(80)` | no | `world.publish` / `script.delete`... |
| `resource_type` | `String(80)` | no | |
| `resource_id` | `String(191)` | yes | |
| `payload` | `JSON` | no | diff / 参数 |
| `ip_address` | `String(64)` | yes | |
| `user_agent` | `Text` | yes | |
| `created_at` | `datetime` | no | |

索引：`idx_admin_audit_logs_admin_created (admin_user_id, created_at)`、`idx_admin_audit_logs_resource (resource_type, resource_id)`。

引入：`4d6f8a1b3c92_add_admin_audit_log`。所有写接口必须 `record_admin_action`。

---

## 3. Alembic 演进列表

按 down_revision 链顺序整理（左→右 = 旧→新；最后一行是 head）：

| revision | 描述 | Create Date | 验证脚本 |
|---|---|---|---|
| `045766d633e1` | initial schema（worlds / npcs / characters / events / endings / game_sessions / messages / token_usage） | 2026-04-08 | — |
| `472da503b7df` | 加 scripts 表 + game_sessions.script_id | 2026-04-08 | — |
| `8c4c7c1d2c41` | 加 memory_entries 表 | 2026-04-08 | — |
| `b1f5c4d9e2a1` | 加 worlds.locations_data + world_drafts / script_drafts | 2026-04-08 | — |
| `c6f6a2f4f8d1` | 加 users / auth_identities / web_sessions；重建 ownership-sensitive 表（`player_id` → `user_id`） | 2026-04-08 | — |
| `7b9e4a1d2c3f` | events.trigger_type 长度 20→50 | 2026-04-08 | — |
| `01f437c7c05d` | 加 world_characters；加 worlds.free_playable_character_ids | 2026-04-09 | — |
| `a21226f5c969` | game_sessions.character_id FK 切到 world_characters | 2026-04-09 | — |
| `d3a1b2c4e5f6` | world_characters.avatar + scripts.cover_image | 2026-04-10 | — |
| `e4b3c2d1f0a9` | worlds.poster_image + worlds.hero_image | 2026-04-10 | — |
| `f5a2b3c4d6e7` | memory_entries.related_npc + `idx_memory_npc`（0.A.3） | 2026-04-12 | — |
| `9d1a2b3c4d5e` | 加 generation_tasks / generation_task_events（**多 down_revision merge**：`7b9e4a1d2c3f` + `f5a2b3c4d6e7`） | 2026-04-13 | — |
| `5561197da50c` | scripts.script_type；统一 generation_tasks 索引命名（`ix_*`） | 2026-04-14 | — |
| `6f1c2a4b8d9e` | 加 model_providers / provider_models / model_slot_bindings / model_capability_probes | 2026-04-17 | — |
| `2c8b7e5a9d01` | users.is_admin | 2026-04-30 | `verify_user_is_admin.py`（也是 revision `7e1a9c0d4b2f`） |
| `4d6f8a1b3c92` | 加 admin_audit_logs | 2026-04-30 | — |
| `7e1a9c0d4b2f` | verify users.is_admin（既是 verify 脚本也是空 revision） | 2026-04-30 | 自身 |
| `0a5b6c7d8e9f` | game_sessions.version（乐观锁） | 2026-04-30 | `verify_session_version.py`（revision `1b6c7d8e9f0a`） |
| `1b6c7d8e9f0a` | verify session version | 2026-04-30 | 自身 |
| `2a7c9d4e1f03` | 加 case_board_history | 2026-04-30 | — |
| `3b8d9e1c2f04` | memory_entries.embedding（1.B.2） | 2026-05-06 | — |
| `4c9e0f2d3a05` | 加 npc_reflections | 2026-05-06 | — |
| `5d0a1b2c3e06` | messages.npc_dialogues（1.B.4 voice anchor） | 2026-05-06 | — |
| `6e1b2c3d4f07` | 加 npc_relations（NPC-2） | 2026-05-07 | — |
| `7f2c3d4e5a08` | world_characters.initial_peer_relations（NPC-2 seed 源） | 2026-05-07 | — |
| `8a2b1c3d4e5f` | 加 `idx_game_sessions_world_id` + `idx_messages_session_role` | 2026-05-08 | — |
| `9b3c4d5e6f7a` | token_usage 加 model_id + provider_name（2.D.1，**当前 head**） | 2026-05-08 | — |

共 **27 条** alembic revision（含 3 条纯 verify 节点）。链是单线 + 一处 merge（`9d1a2b3c4d5e` 合并 `7b9e4a1d2c3f` 跟 `f5a2b3c4d6e7` 两支）。

---

## 4. 关键约束 / 索引清单

### 单 head 约束

`alembic upgrade head` 必须只有一个 head；`9d1a2b3c4d5e` 之后链路保持单线。当前 head 是 `9b3c4d5e6f7a`。

### 唯一约束（业务关键）

| 表 | 约束 | 含义 |
|---|---|---|
| `auth_identities` | `UNIQUE (provider, provider_user_id)` | 同一 provider 下用户身份唯一 |
| `world_drafts` | `UNIQUE (world_id)` | 一个世界最多一份草稿 |
| `script_drafts` | `UNIQUE (script_id)` | 一份剧本最多一份草稿 |
| `model_providers` | `UNIQUE (name)` | provider name 全局唯一 |
| `provider_models` | `UNIQUE (provider_id, model_id, model_kind)` | 同一 provider 下同 kind 同 model_id 不能重复 |
| `model_slot_bindings` | `UNIQUE (slot_name)` | 一个 slot 只绑一个模型 |
| `npc_reflections` | `UNIQUE (session_id, npc_name)` | 一个 session 一个 NPC 一份 reflection |
| `npc_relations` | `UNIQUE (session_id, npc_a, npc_b)` | 有向关系唯一（A→B 跟 B→A 是两行） |

### 关键索引（按表）

- `users` — 无业务索引（PK 即可）
- `auth_identities` — `(user_id)` `(union_id)`
- `web_sessions` — `(user_id)` `(expires_at)`
- `world_characters` — `(world_id)` `(playable)`
- `game_sessions` — `(user_id, status)` `(user_id, last_played_at)` `(world_id)`
- `messages` — `(session_id, created_at)` `(session_id, is_compressed)` `(session_id, role)`
- `memory_entries` — `(session_id)` `(session_id, memory_type)` `(session_id, related_npc)`
- `token_usage` — `(session_id)` `(created_at)`
- `npc_reflections` — `(session_id)` + UNIQUE
- `npc_relations` — `(session_id, npc_a)` + UNIQUE
- `case_board_history` — `(session_id)` `(session_id, id)`
- `admin_audit_logs` — `(admin_user_id, created_at)` `(resource_type, resource_id)`
- `generation_tasks` — `(draft_id)` `(status)`
- `generation_task_events` — `(task_id)`
- `model_providers` — `(provider_type, status)` + UNIQUE
- `provider_models` — `(provider_id, model_kind)` + UNIQUE
- `model_capability_probes` — `(model_id, capability)` `(verified_at)`

### 跨表设计约束（业务层强制，非 DB constraint）

- **`game_sessions.version` 乐观锁**：每次写自增；`UPDATE ... WHERE version=?` 冲突 → API 返 409，前端按文档 retry。
- **`memory_entries.related_npc` 隔离锚点**：NPC agent 只读 `WHERE related_npc=自己`，全局 `recent_messages` 不传给 NPC（信息隔离契约，详见 `docs/modules/npc.md` §4）。
- **Draft → Published 单向**：发布时 `world_drafts.world_id` / `script_drafts.script_id` 回填，不再手动改 draft。
- **Admin 写操作必走 audit**：`record_admin_action` 写 `admin_audit_logs`，不能绕。

---

## 5. 已知短板与未来扩展

### P2（短期可做）

- **legacy `npcs` / `characters` 表清理**：`045766d633e1` 创建后已被 `world_characters` 完全替代；`services` / `engine` / `seeds` 全部不读不写，仅模型还导出。确认无外部 ETL 依赖后可一次性 drop（或留一条 alembic migration 做正式删除）。
- **`token_usage` 新维度**：当前只有 provider/model + token 数 + cents，缺 `slot_name`（哪个业务环节的成本）、`turn_id` / `request_id`（关联具体一轮交互，便于 trace）。Phase 2 cost guardrail 升级时一起加。
- **`memory_entries.embedding` JSON → pgvector**：JSON 是为了 SQLite 测试兼容，但 PG 上 cosine 走 Python 端做。生产数据规模上去后可换 pgvector + ANN 索引。
- **`case_board_history` 老 session 清理**：长会话操作多时这张表会膨胀。加一个按 session 状态归档的批处理（session ended 后 N 天压缩历史）。

### P3（长期愿景）

- **跨 session NPC 档案表**：`docs/modules/npc.md` §9 P3 提到的"同一 NPC 在不同玩家不同局里有性格延续性"，需要新表 `npc_persona_archive (user_id, npc_canonical_id, ...)`。NPC-3/NPC-4 落地后再评估。
- **`game_sessions.game_state` JSON 拆表**：当前 `game_state` 是个大 JSON，所有运行时状态都在里面。负载大时可考虑把 NPC 实时状态（trust/mood/intent）拆出独立表，便于按 NPC 维度查询。但拆完会增加写入复杂度，需要先看真实瓶颈。
- **`generation_task_events` 归档**：任务结束后事件流主要用于 debug；可加冷热分层。
- **多租户 / 工作室概念**：当前没有"组织"维度，所有 worlds / scripts 共享一个发现页。引入 workshop / studio 后，`worlds` / `scripts` / `model_providers` 都要加 `org_id`。

### 候选清理（确认无依赖即可删）

| 表 | 理由 |
|---|---|
| `npcs` | legacy，被 `world_characters` 替代 |
| `characters` | legacy，被 `world_characters` 替代 |

注意：删除前需 grep `seeds/` / 备份脚本 / 数据迁移工具，确认无外部依赖；建议先 `RENAME` 一段时间观察。

---

## 参考

- 模型源码：`backend/models/*.py`（每个表的注释字段是字段含义的第一来源）
- Alembic：`backend/migrations/versions/*.py`（按 revision id 查"何时引入"）
- Breaking changes：`docs/MIGRATION_NOTES.md`
- NPC 子系统的 schema 视角：`docs/modules/npc.md` §8
- 创作工坊 SSE 事件类型：`frontend/lib/admin-sse-events.ts`（前后端共契约）
