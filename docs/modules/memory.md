# Memory 模块技术说明

> 状态截至 2026-05-08。覆盖 Phase 0.A.3（NPC 记忆隔离 + info_propagation 双视角写入）+ Phase 1.B.2（语义召回）+ Phase 1.B.4（voice anchor）+ Phase 2.D.3（batch query 修 N+1）+ NPC reflection（长期内心总结）+ NPC-2（持久 NPC↔NPC 关系）落地后的形态。

Memory 是世界引擎的**记忆系统**——管理"谁知道什么、什么时候知道、怎么调出来"。包含三层：

1. **结构化 memory_entries**：每条记忆带 `related_npc` 锚点（隔离边界）+ `embedding`（语义召回）+ importance/round 等元数据
2. **InfoPropagation**：信息在 NPC 之间随时间扩散的模型（同场即知 / 社交关系延迟 / 全镇延迟）
3. **长期反思**：每个 NPC 累积 ≥ 阈值新记忆时，LLM 重写第一人称内心总结（`npc_reflections` 表）

外加几个辅助查询：
- **voice anchor**（最近 3 句自己的话）—— 来自 `messages.npc_dialogues` JSON 列
- **NPC↔NPC peer relations**（NPC-2 持久静态关系）—— `npc_relations` 表
- **search_messages**（关键词扫旧 message）—— Director 的 `recall_memory` 工具

它**不直接**做的事：
- 不直接调度 NPC（orchestrator 调）
- 不直接写 game_state / 不参与 SSE 流（数据通过参数返回 / 异步任务持久化）
- 不做内容审核（来源在生成端）

紧密耦合的上下游：
- 上：[orchestrator](./orchestrator.md)（写入收集 + 查询调度）+ [game_service](./state-and-persistence.md)（done 后置持久化 + reflection 异步触发）
- 下：[llm-router](./llm-router.md)（embedding + reflection 各自走 LLM）+ [npc](./npc.md)（消费查询结果）

## 1. 能力矩阵

### A. Memory 写入路径（who writes what）

| 来源 | 触发点 | 写什么 | 实现 |
|---|---|---|---|
| Director `memory_extracts` 字段 | 每回合 done | 一条 `general/player_claim/npc_attitude/discovery/causal_chain/environment_change` 类型 entry | `parse_memory_extracts` |
| Director `inform_npc_calls` | 每回合 done | 类型 `director_told` 的 entry，related_npc=指定 NPC | orchestrator line ~497-520 |
| World event `npc_action`（≥2 NPC） | tick 时 | NPC↔NPC 双视角各一条 `npc_interaction` entry | `write_dual_perspective_memories` |
| World event `info_spread` | tick 时 | 每个新知情 NPC 一条 `info_propagation` entry | `write_info_propagation_memories` |
| 生成端 importance 映射 high/medium/low | 全部 | 数值 8/5/3 | `IMPORTANCE_MAP` |
| Director extract 里 NPC 名提取 | parse_memory_extracts | `related_npc` 锚点（NPC 名出现在 content 里 → 标 related） | `_detect_npc` |
| 写入时 attach embedding | done 后置 | `embedding` JSON 列填值（失败 None 不阻塞） | `attach_embeddings` + embedding_service |

### B. Memory 隔离与查询

| 能力 | 状态 | 实现 |
|---|---|---|
| 严格 `related_npc` 锚点过滤（NPC agent 看不到全局） | ✅ | `filter_npc_memory_entries` + 数据库 query 带 `related_npc=npc_name` |
| 单 NPC 查询 + 语义重排 | ✅ | `query_npc_memories` |
| 批量多 NPC 查询（一次 SQL + 一次 embed，N+1 修复） | ✅ | `batch_query_npc_memories`（2.D.3） |
| 候选池放大 3× 给 cosine 重排空间 | ✅ | `_SEMANTIC_CANDIDATE_MULTIPLIER=3` / `_MIN=20` |
| 重排 fallback 到 importance/round 排序（embed 失败/无 embedding 列） | ✅ | `_semantic_rerank` 返回 None 触发 |
| 同时存在有 embedding 和无 embedding 行 → 有 embedding 的优先（哨兵 -1.0） | ✅ | `_semantic_rerank` line ~191-197 |
| 顶层 `attach_embeddings` 失败逐行回退 None | ✅ | `embedding_service` exception path |

### C. 语义召回 / Embedding 服务

| 能力 | 状态 | 实现 |
|---|---|---|
| OpenAI 兼容 embeddings API（`text-embedding-3-small` 默认） | ✅ | `embedding_service.embed_text/embed_texts` |
| 单文本/批量两个 API | ✅ | `embed_text` / `embed_texts` |
| Cosine similarity 数学（手工实现） | ✅ | `cosine_similarity` |
| 5s 调用超时（`embedding_timeout_seconds`） | ✅ | embedding_service |
| 失败 fallback：返回空 list / None，不阻塞游戏 | ✅ | embedding_service exception path + `attach_embeddings` 兜底 |
| 写入时同步 embed（阻塞 done 后置任务） | 🟡 | 同步 5s timeout；P2 改异步 |
| `EMBEDDING_ENABLED` 默认 False（需 admin 显式开） | ✅ | `config.py` |
| 维度 `embedding_dim=1536`（仅文档用，不强制校验） | 🟡 | settings 字段没在代码里强制 |

### D. InfoPropagation（信息传播）

| 能力 | 状态 | 实现 |
|---|---|---|
| `info_items: list[InfoItem]` 在 GameState 里 | ✅ | `state_manager.GameState.info_items` |
| 三档传播延迟：同场=0 轮 / 社交关系=2 轮 / 全镇=5 轮 | ✅ | `SAME_LOCATION_DELAY/SOCIAL_TIE_DELAY/TOWN_WIDE_DELAY` |
| 同场判定：`npc_locations[npc] == npc_locations[knower]` | ✅ | `_same_location` |
| 社交关系判定：双向查 `npc_relations` 字典 | ✅ | `_has_social_tie` |
| 传播 emit `info_spread` WorldEvent（含 involved_npcs） | ✅ | `propagate` |
| WorldSimulator.tick 调用 propagate（详见 [world-simulator.md](./world-simulator.md)） | ✅ | tick 阶段 |
| info_spread 事件 → orchestrator → write_info_propagation_memories | ✅ | 闭环 |
| info_items 持久化（GameState 序列化保存） | ✅ | `to_dict` 包含 |

### E. Voice anchor（Phase 1.B.4）

| 能力 | 状态 | 实现 |
|---|---|---|
| 拉每个 NPC 最近 3 句自己说过的话 | ✅ | `get_npc_recent_utterances` |
| 数据源：`messages.npc_dialogues` JSON 列（`{npc_name: dialogue}`） | ✅ | `models/game.py::Message.npc_dialogues` |
| 拉宽窗口（4× limit）以防最近消息没这个 NPC 发言 | ✅ | `candidate_window = max(limit*4, 8)` |
| 注入 NPC system prompt（详见 [npc.md §3.5](./npc.md)） | ✅ | `prompts.build_npc_system(voice_anchor=...)` |
| 加载失败 fallback 空 list，warn `npc_voice_anchor_load_failed` | ✅ | orchestrator try/except |
| Legacy 行 `npc_dialogues=None` 不崩 | ✅ | `if not isinstance(row.npc_dialogues, dict)` |

### F. NPC↔NPC 持久关系（NPC-2）

| 能力 | 状态 | 实现 |
|---|---|---|
| `npc_relations` 表（A→B / B→A 各一行） | ✅ | `models/npc_relation.py` |
| `get_npc_peer_relations(npc_name)` 只返回 `npc_a=self` 方向 | ✅ | `memory_manager.py:311` |
| 信息隔离：反向 trust（B→A）永不返回 | ✅ | query 限定 `npc_a == self` |
| 信息隔离：第三方关系（C↔D）永不返回 | ✅ | 同上 |
| Session 启动时从 `world_characters.initial_peer_relations` 灌入 | ✅ | `services/game_service.py::_seed_npc_relations`（详见 [npc.md §3.11](./npc.md)） |
| 加载失败 fallback 空 list，warn `npc_peer_relations_load_failed` | ✅ | orchestrator try/except |
| 关系**只读**（runtime 不变） | 🟡 | NPC-3 后台模拟会让它动态化，未做 |

### G. NPC 长期反思（reflection）

| 能力 | 状态 | 实现 |
|---|---|---|
| `npc_reflections` 表（UNIQUE session_id × npc_name） | ✅ | `models/npc_reflection.py` |
| `get_reflection / should_reflect / reflect / maybe_reflect` 四个 service 函数 | ✅ | `npc_reflection_service.py` |
| 触发条件：自上次 reflection 以来新增 memory_entries ≥ 阈值（默认 5） | ✅ | `should_reflect` SQL count |
| 阈值可调 `NPC_REFLECTION_THRESHOLD` | ✅ | settings |
| 总开关 `NPC_REFLECTION_ENABLED` 默认 True | ✅ | settings |
| LLM 调用走 `conversation_compression` slot（廉价档） | ✅ | game_service 后置 task |
| 第一人称内心独白 prompt 模板（150-200 字目标） | ✅ | `_build_reflection_prompt` |
| 失败兜底：留旧 reflection 不变，warn `npc_reflection.llm_failed` / `empty_output` | ✅ | reflect line ~158-174 |
| 成功更新 `last_memory_id` + `reflection_count` + `updated_at` | ✅ | line ~176-191 |
| **异步 fire-and-forget**（不阻塞 SSE done） | ✅ | `game_service` 用 `asyncio.create_task` 启 |
| 触发时机：每回合 done 后，对 `involved_npcs_for_reflection` 各启一个 task | ✅ | game_service `_consume_turn` 后置 |
| 注入 NPC system prompt 稳定前缀（"你最近的内心总结"段） | ✅ | `prompts.build_npc_system(reflection=...)` |

### H. Director `recall_memory` 工具

| 能力 | 状态 | 实现 |
|---|---|---|
| 关键词搜旧 messages（不是 memory_entries！） | ✅ | `search_messages` |
| 按 round 倒序，最多 3 条 | ✅ | `max_results=3` 默认 |
| 注入 Director 通过 `recall_fn` 回调 | ✅ | orchestrator line ~389-392 |
| 仅在 `all_messages` 非空时启用 | ✅ | 同上 |
| Director tool-use 内多轮交互（详见 [director.md §2.1](./director.md)） | ✅ | director_agent `_run_tool_use` 3 轮循环 |

### I. 跨模块上下文构造

| 能力 | 状态 | 实现 |
|---|---|---|
| `build_memory_context(entries)` → "[第N轮] 内容\n..." 字符串 | ✅ | `memory_manager.py:408` |
| Director 端拼装到 effective_memory_context（详见 [orchestrator.md §1.E](./orchestrator.md)） | ✅ | orchestrator line ~374 |
| NPC 端从 batch_query_npc_memories 拿 list[dict]，prompt 端渲染 | ✅ | `prompts.build_npc_system(memories=...)` |

## 2. 关键能力实现要点

### 2.1 NPC 记忆隔离（Phase 0.A.3 — 系统安全契约）

**问题**：早期 NPC agent 直接拿 `recent_messages`（全局对话流）作为上下文——意味着 NPC A 知道玩家私下跟 NPC B 说了什么。这是信息泄露的根源，剧情瞬间崩。

**解决**：
1. NPC agent 调用时强制 `recent_messages=[]`
2. NPC 上下文只来自 `memory_entries WHERE related_npc = NPC名` 的行
3. World event 通过 `info_propagation` 系统的 last-mile write 给每个**应该知道**的 NPC 各写一条 memory（双视角不同）
4. Director 想强行植入某事进 NPC 私域，用显式 `inform_npc_calls` 工具

**实现**：
- 表层：`MemoryEntry.related_npc` 列（migration `f5a2b3c4d6e7`）
- 写入端：`parse_memory_extracts` / `write_dual_perspective_memories` / `write_info_propagation_memories` / orchestrator 的 inform_npc 处理 — 都强制设 `related_npc`
- 查询端：`query_npc_memories` SQL `WHERE related_npc = npc_name`；batch 版用 `IN (...)` 但仍按 NPC 桶分
- 详见 [npc.md §4 信息隔离原则](./npc.md)

**取舍**：
- 拒绝了"NPC 仍读全局对话但加 prompt 约束 LLM 自己别用"——LLM 偶发会"用了"，无法可靠
- 拒绝了"用 ACL 列表标记每条 memory 的可见 NPC"——schema 复杂度爆炸，single-NPC 锚点 + dual write 等价但简单
- 接受了"同一事件需要写两条 memory"的存储成本（NPC↔NPC 互动每个视角各一条）—— 表大小不是瓶颈，简单胜于巧妙

### 2.2 语义召回（Phase 1.B.2）

**问题**：早期 NPC 拉记忆按 importance + round 排序，结果是 LLM 看到 5 条"最重要+最新"的 entries——往往跟玩家当前问的事**毫无关系**（玩家这轮在问遗嘱，NPC 看到的是上周刚发现的尸体细节）。

**解决**：每条 memory 写入时同步生成 embedding（OpenAI 兼容 API）；查询时拉宽候选池（importance top 30），用 query_text（玩家本轮 action）算 cosine 重排，取 top 10。

**实现**：
- 候选池：`_SEMANTIC_CANDIDATE_MULTIPLIER=3` × `limit_per_npc` 或 `_MIN=20` 取大
- 重排函数 `_semantic_rerank`（单 NPC）+ `batch_query_npc_memories`（多 NPC 一次 SQL + 一次 embed）
- `attach_embeddings` 在写入前调，失败逐行回退 `embedding=None`
- 行级混合：有 embedding 的按 cosine 排，无 embedding 的塞末尾（哨兵 `-1.0`）
- `EMBEDDING_ENABLED=false` 默认关，admin 显式启用 + 配 base_url + api_key

**取舍**：
- 不用 pgvector 列：当前 JSON 列 + Python 端 cosine 够 100 玩家用；切到 pgvector 是"后期优化"（已记在 P2）
- 候选池 3×：经验值，<3× 漏召回明显，>3× 没显著收益但 embed 调用变多
- 写入同步 embed 阻塞 5s：当前是"对单条 done 后置任务多 5s 等待"，P2 改异步要解决"读侧 race（写没完读就来）"

### 2.3 InfoPropagation（信息扩散三档延迟）

**问题**：现实里"赵姐说茶刚泡好"如果只在茶摊里听到的人才知道，那远处的王福永远不知道——可如果王福下午回茶摊跟赵姐喝茶，他应该听说昨天发生了啥。模型需要表达"信息扩散有时间延迟"。

**解决**：把信息建模成 `InfoItem(source, content, known_by, created_at_round)`。每个 tick 跑 `propagate`：
- 同场（`_same_location`）的 NPC 立刻知道（延迟 0）
- 有社交关系（`_has_social_tie`，双向查 `npc_relations`）的 NPC 2 轮后知道
- 镇上其他 NPC 5 轮后知道（"小道消息"）

每个新知情 NPC 收到一条 `info_propagation` memory（通过 `write_info_propagation_memories`）。

**实现**：
- 数据：`InfoItem` dataclass + `GameState.info_items` 持久化
- 调用入口：`world_simulator.tick` 每轮调 `InfoPropagation().propagate(state)` 返回事件列表
- 事件 `info_spread` 流入 orchestrator → write_info_propagation_memories → 各 NPC 的私有记忆

**取舍**：
- 三档延迟是经验值，没基于真实社交学研究——只要看着合理就行
- 社交关系判定用 `npc_relations` dict（玩家与 NPC 的 trust dict），不是 NPC↔NPC 的 `npc_relations` 表（NPC-2）—— 这是个**早期的简化**，应该用 NPC-2 表更准确，但当前没人推这个改，记在 P3
- `info_items` 字段从来没被代码主动**注入新条目**（grep 找不到 `state.info_items.append`）—— 当前 InfoPropagation 是"功能在但没人用"的状态，P2 待评估是删还是补 director 工具填

### 2.4 长期反思（Reflection — Stanford "Generative Agents" 模式）

**问题**：即使有记忆隔离 + 语义召回，NPC 看到的还是离散的"事实条目"。长会话中（30+ 轮）NPC 性格容易漂移，因为它没有"我作为这个角色一路走来的整体感"。

**解决**：给每个 NPC 维护持久的**第一人称内心总结**（`npc_reflections` 表）。当该 NPC 累积 ≥ 5 条新 memory（自上次反思以来）时，触发 LLM 重写：合并旧 summary + 新记忆 → 新 summary。注入 NPC system prompt 稳定前缀。

**实现**：
- 表：`npc_reflections (id, session_id, npc_name, summary, last_memory_id, reflection_count, ...)`，UNIQUE(session_id, npc_name)
- 触发：`game_service._consume_turn` 收到 done 事件、commit 完毕后，对每个 `involved_npcs_for_reflection` 起一个 `asyncio.create_task(maybe_reflect(...))`，**用独立 db session**，不阻塞 SSE done
- LLM 用 `conversation_compression` slot（廉价档），`max_tokens=600`
- prompt 模板（`_build_reflection_prompt`）：第一人称、150-200 字、不写日记/流水账、含 trust 变化 + 关键转折 + 还在意的事
- 失败兜底：保留旧 summary，warn 不致命

**取舍**：
- 阈值 5 是经验值；太低导致频繁 reflection 浪费 token，太高导致 NPC 性格漂移
- 用 conversation_compression slot 复用：reflection 跟压缩都是"廉价档把长上下文凝练成短总结"任务，slot 划分不必更细
- Fire-and-forget：reflection 失败不影响玩家本轮体验（玩家看到的是这轮 NPC 的反应，下一轮看到的是新 reflection 注入）
- Async 路径让 commit + SSE done 不被反思阻塞——但代价是 reflection 写完时 session 可能已经关了；用独立 db session 避开

### 2.5 batch_query_npc_memories（Phase 2.D.3 — 修 N+1）

**问题**：早期每个 involved NPC 一次 query_npc_memories → 每次一次 SQL（找候选）+ 一次 embedding 调用（embed query_text）。3 个 NPC 同场就是 3 次 SQL + 3 次 embed → 显著拖 TTFB + 加 embedding 成本。

**解决**：单次 SQL 拿所有 NPC 的候选行（`WHERE related_npc IN (...)`），Python 端按 NPC 分桶；query_text 只 embed 一次，复用给每个 NPC 的 cosine 重排。

**实现**：
- `batch_query_npc_memories` line ~212-309
- 单 SQL `IN` 子句一次拉，每 NPC 配 `candidate_limit_per_npc = 3× limit_per_npc`
- 单 embed 调用在外层（line ~263-269），失败 fallback `query_vec=None` → 后续每 NPC 走 importance 排序
- 返回 `{npc_name: [memory_dict]}`，未命中 NPC 返回空 list

**取舍**：
- 桶分阶段做了 candidate_limit 截断，避免热门 NPC（memory 太多）挤占其它 NPC 的候选预算
- 排序在 SQL 端做（`importance.desc(), round_number.desc()`）比 Python 排省事
- 不用 EXISTS / window function：SQL 跨 DBMS 兼容性好，性能在 100 玩家级足够

## 3. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/engine/memory_manager.py` | MemoryManager 主类（写入构造 + 查询 + 重排 + 各种辅助查询） |
| `backend/services/embedding_service.py` | embed_text / embed_texts / cosine_similarity（OpenAI 兼容 + 失败 fallback） |
| `backend/engine/info_propagation.py` | InfoItem / InfoPropagation（三档延迟规则） |
| `backend/services/npc_reflection_service.py` | get_reflection / should_reflect / reflect / maybe_reflect + 反思 prompt |
| `backend/models/memory.py` | MemoryEntry ORM（含 related_npc + embedding 列） |
| `backend/models/npc_reflection.py` | NPCReflection ORM |
| `backend/models/npc_relation.py` | NPCRelation ORM（NPC-2 持久关系） |
| `backend/models/game.py` | Message.npc_dialogues 列（voice anchor 数据源） |
| `backend/engine/orchestrator.py` | 写入收集 + batch_query 调用点 + reflection 触发 |
| `backend/services/game_service.py` | done 后置：attach_embeddings / 持久化 / 反思 task |
| `backend/engine/prompts.py` | NPC system prompt 渲染 memory / reflection / voice_anchor / peer_relations 段（详见 [npc.md](./npc.md)） |

## 4. 配置项

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `EMBEDDING_ENABLED` | `false` | 总开关；False 跳过整个语义召回路径 |
| `EMBEDDING_BASE_URL` | `""` | OpenAI 兼容 embeddings endpoint |
| `EMBEDDING_API_KEY` | `""` | embedding 服务 API key |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | embedding 模型名 |
| `EMBEDDING_DIM` | `1536` | 向量维度（仅文档用，不强制校验） |
| `EMBEDDING_TIMEOUT_SECONDS` | `5.0` | 单次 embedding 调用超时 |
| `NPC_REFLECTION_ENABLED` | `true` | 总开关 |
| `NPC_REFLECTION_THRESHOLD` | `5` | 累积多少条新 memory 触发反思 |

| Slot | 模型档位 | 用途 |
|---|---|---|
| `conversation_compression` | 廉价档 | NPC reflection + 上下文压缩共享；廉价档对"长摘要"任务够用 |

## 5. 数据库 schema

参见 [data/schema.md](../data/schema.md) 的 `memory_entries` / `npc_reflections` / `npc_relations` 三张表详解。本节只列要点：

```sql
memory_entries (
  id, session_id, memory_type, content, round_number, importance,
  related_npc,                -- 0.A.3：隔离锚点
  embedding JSON,             -- 1.B.2：nullable，cosine 重排用
  created_at
)
INDEX (session_id, related_npc)

messages (
  ...,
  npc_dialogues JSON,         -- 1.B.4：{npc_name: dialogue}，仅 assistant 消息
  ...
)

npc_reflections (
  id, session_id, npc_name, summary,
  last_memory_id,             -- 上次反思覆盖到的最大 memory_entries.id
  reflection_count,
  created_at, updated_at
)
UNIQUE (session_id, npc_name)

npc_relations (
  id, session_id, npc_a, npc_b,
  trust SMALLINT,             -- [-10, 10]
  relationship_label,
  history_summary,
  last_event_round,           -- NPC-3 用，NPC-2 始终 0
  created_at, updated_at
)
UNIQUE (session_id, npc_a, npc_b)
INDEX (session_id, npc_a)
```

## 6. 测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_memory_semantic_recall.py` | cosine 重排 + fallback 路径 |
| `tests/test_memory_batch_query.py` | batch query 分组、单次 embed、limit |
| `tests/test_embedding_service.py` | embedding service 失败兜底、cosine 数学 |
| `tests/test_npc_reflection.py` | should_reflect 阈值、reflect 创建/更新、LLM 失败兜底 |
| `tests/test_npc_voice_anchor.py` | get_npc_recent_utterances + prompt 注入 |
| `tests/test_npc_peer_relations.py` | NPC-2 双向 seed + 显式不对称 + trust clamp + 信息隔离（不暴露反向 / C↔D） |
| `tests/test_orchestrator.py::test_orchestrator_does_not_pass_global_recent_messages_to_npc_agent` | 信息隔离回归（NPC agent 收 `recent_messages=[]`） |
| `tests/test_director_inform_npc.py` | inform_npc 写 director_told memory + 拒绝未知 NPC |

## 7. 已知短板与未来扩展

### P2

- **Embedding 同步阻塞**：`attach_embeddings` 写入时同步调 OpenAI 兼容 API，最多阻塞 5s × 条数。改异步要处理"读侧 race"（reflection / 下一回合的 batch_query 可能赶在 embedding 写入前 SELECT 出来）。需要双写策略或 background reembed 任务。
- **InfoPropagation 没人用**：`info_items` 字段在 GameState 但没代码主动 append 新 InfoItem；当前是 dead code path。要么删（把 propagate / write_info_propagation_memories 一起清理），要么补 Director 工具显式注入 InfoItem。
- **Director recall_memory 用关键词不用语义**：`search_messages` 是简单 substring 匹配，关键词不准就漏。可以改用 embedding 重排，但 Director 主动调 recall 频次不高，工作量收益比一般。
- **Reflection LLM 失败的可观测**：当前失败只 warn `npc_reflection.llm_failed`，没有"这个 NPC 已经连续 N 轮反思失败"的累积告警。如果某个 session 反思全挂，NPC 性格漂移会逐渐暴露。

### P3

- **NPC↔NPC 关系动态化（NPC-3）**：当前 npc_relations 是只读 seed。NPC-3 spec 是"玩家不在场时跑后台模拟，按 deterministic 规则累计 trust delta，阈值触发 LLM 重写 history_summary"。等 NPC-1+2 上线观察一周后再决定。
- **Director 主动改 NPC 关系（NPC-4）**：`DIRECTOR_TOOL.npc_relation_updates` 字段还没加。配合 NPC-3 让 Director 有显式编辑能力。
- **跨 session 角色档案**：同一 NPC 在不同玩家的不同局里有性格延续性。需要 `user_id × npc_id` 维度的持久档案表 + 跨 session 召回机制。Phase 3 长期愿景。
- **pgvector 列**：JSON 列 + Python cosine 在 100 玩家内够用。流量上来后切 pgvector 能让 SQL 端做 cosine 排序，删掉 Python 端 _semantic_rerank 大段代码。
- **Reflection 触发频率自适应**：当前固定 5 条阈值；可以让"重要事件多"时阈值降低（比如发现关键线索 +3）实现"剧情急转弯时 NPC 反应更快"。
