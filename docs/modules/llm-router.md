# LLM Router 模块技术说明

> 状态截至 2026-07-16。覆盖 LLMProvider 抽象、首包/流停顿超时、生成调用完整 deadline、bounded retry、prefix_hash 日志和三层 slot/provider/model 动态绑定。

LLM Router 是 InkWild 调用一切大模型的统一入口。`LLMRouter` 包一层 fallback chain + stream-stall timeout + transient retry；生成槽额外有完整调用 deadline。前面再叠 `services/model_management.py` 的三层抽象（Slot → ModelSlotBinding → ProviderModel → ModelProvider）把"业务调用什么模型"动态化——admin 后台改个绑定就生效，业务代码全程只见 slot 名（`game_main` / `npc_agent` / `moderation_slot` / ...）。

它**不直接**做的事：
- 不做业务编排（orchestrator / agents 各自负责）
- 不做 SSE 序列化（`api/game.py::to_sse_event`）
- 不做 token 成本核算（`services/game_service.py` + `models/token_usage.py`）

紧密耦合的上下游：
- 上：`api/game.py::get_game_service`（解析 game_main / npc_agent / 等 slot 拿 router）；`services/world_creator_agent.py`（admin_generation slot）；`engine/content_filter.py`（moderation_slot）
- 下：`llm/*.py` 各 provider 实现；`models/model_management.py` 三张表

## 1. 能力矩阵

### A. Provider 抽象与具体实现

| 能力 | 状态 | 实现 |
|---|---|---|
| `LLMProvider.stream_with_tools` 文本 + tool use 流式接口 | ✅ | `llm/base.py:13` |
| `ImageGenerator.generate_image` 图像生成接口 | ✅ | `llm/base.py:61` |
| `WebSearcher.web_search` 联网检索接口 | ✅ | `llm/base.py:74` |
| DeepSeek（OpenAI 兼容 chat completions） | ✅ | `llm/deepseek.py::DeepSeekProvider` |
| Claude（anthropic SDK，messages.stream） | ✅ | `llm/claude.py::ClaudeProvider` |
| Gemini（OpenAI 兼容 generativelanguage 端点） | ✅ | `llm/gemini.py::GeminiProvider` 继承 OpenAICompatibleProvider |
| Grok / xAI（chat + Responses API web_search + Imagine 生图） | ✅ | `llm/grok.py::GrokProvider`（同时实现 LLMProvider / WebSearcher / ImageGenerator） |
| OpenAI 兼容通用 provider | ✅ | `llm/openai_compatible.py::OpenAICompatibleProvider` |
| Seedream（OpenAI 兼容 + retry + placeholder 兜底） | ✅ | `llm/seedream.py::SeedreamImageProvider` 继承 OpenAICompatibleImageProvider |
| Tavily 联网检索（独立 service，不走 router） | ✅ | `services/tavily_search.py::TavilySearch` |
| Anthropic-style tool schema（`input_schema`）统一约定，OpenAI 系 provider 用 `_convert_tool_to_openai` 映射 | ✅ | 各 provider 实现内 |

### B. LLMRouter 调度

| 能力 | 状态 | 实现 |
|---|---|---|
| Fallback chain（多个 provider 顺序尝试，记录最后一个 error） | ✅ | `LLMRouter.stream_with_tools` line 113-180 |
| `provider_name` 参数把指定 provider 顶到 chain 头部 | ✅ | line 122-123 |
| 首包/逐 chunk 停顿 timeout；只在首个 event 前允许 retry | ✅ | `_stream_one_provider` |
| 完整调用 deadline（生成槽 600s，覆盖持续吐 token 但不结束） | ✅ | `total_timeout_seconds` + `GENERATION_TOTAL_TIMEOUT_SECONDS` |
| Bounded retry（默认 1 次）只在 first event 之前生效 | ✅ | line 231-253 |
| `_is_transient` 通过类名 + 5xx status_code 识别可重试错误（不 import openai/httpx） | ✅ | `llm/router.py:48` |
| 已 yield first event 之后不再重试（避免 partial output 重发） | ✅ | line 256-261 |
| Identity 注入 usage 事件（`provider_name` / `model_id`，不 clobber 已有） | ✅ | line 162-168 |
| Prefix hash 日志（每次 stream 起 head 1024 byte 哈希到 16 位 hex） | ✅ | `_system_prefix_signature` + `prompt.prefix_hash` log |
| `response_format` 透传（DeepSeek / OpenAI 兼容 / Grok / Gemini 支持，Claude 静默忽略） | ✅ | line 144-145 + 各 provider |
| 同步设置惰性解析（test 可不带 env 构造 router） | ✅ | `_resolved_settings` line 88 |
| StopAsyncIteration 视为空流，正常 return | ✅ | line 221-223 |

### C. 三层 slot/provider/model 动态绑定

| 能力 | 状态 | 实现 |
|---|---|---|
| `model_providers` 表：name / provider_type / base_url / api_key_env_name / status | ✅ | `models/model_management.py::ModelProvider` |
| `provider_models` 表：provider_id × model_id × model_kind 唯一 | ✅ | `ProviderModel`（UniqueConstraint `uq_provider_models_identity`） |
| `model_slot_bindings` 表：slot_name 全局唯一，绑到一个 model | ✅ | `ModelSlotBinding`（unique slot_name） |
| `model_capability_probes` 表：缓存 chat_basic / streaming / tool_use / json_output / image_generation / web_search 探活结果 | ✅ | `ModelCapabilityProbe` + `_probe_expiry_deadline`（默认 168h TTL） |
| Slot 清单（9 个）：game_main / npc_agent / conversation_compression / ending_summary / admin_generation / moderation_slot / research_planning / research_summary / image_generation | ✅ | `SLOT_DEFINITIONS` line 39-103 |
| Slot required_capabilities 校验（绑定时强制探活通过） | ✅ | `_ensure_capabilities` + `bind_model_slot` |
| Provider 类型支持：openai_compatible / xai / gemini / seedream_image | ✅ | `PROVIDER_TYPES` line 29 |
| `resolve_slot_router(db, slot)` → `LLMRouter`，未绑定 fallback 到 `_legacy_text_router` | ✅ | line 1183-1198 |
| `resolve_slot_provider` / `resolve_slot_image_generator` / `resolve_research_web_searcher` 同款解析 | ✅ | line 1201-1229 |
| Bootstrap 自动建 system 默认 DeepSeek + xAI provider/model（`MODEL_MANAGEMENT_BOOTSTRAP_ENABLED=true`）| ✅ | `ensure_default_model_management_state` + `_default_bootstrap_specs` |
| API key 解析三段：`os.getenv` → `.env` 文件 → settings 字段兜底 | ✅ | `_configured_secret_value` line 183 |
| Provider healthcheck（按 provider 跑所有 model 的 chat_basic / image_generation 探活） | ✅ | `healthcheck_model_provider` |

### D. Admin 管理 API

| 能力 | 状态 | 实现 |
|---|---|---|
| `GET /api/admin/model-dashboard` 一次拉所有 providers/models/slots | ✅ | `admin_models.py::get_model_dashboard_route` |
| `POST/PUT/DELETE /api/admin/model-providers[/{id}]` | ✅ | `admin_models.py:93-182` |
| `POST/PUT/DELETE /api/admin/provider-models[/{id}]` | ✅ | `admin_models.py:215-302` |
| `POST /api/admin/provider-models/{id}/probe` 触发能力探活 | ✅ | `admin_models.py:305-328` |
| `GET/PUT /api/admin/model-slots[/{slot_name}]` 查/绑 slot | ✅ | `admin_models.py:331-359` |
| `POST /api/admin/model-providers/{id}/healthcheck` 整批 provider 探活 | ✅ | `admin_models.py:185-207` |
| 所有写操作走 `record_admin_action`（admin_audit_logs 落审计） | ✅ | 路由内显式调用 |
| 路由整体挂 `Depends(get_current_admin_user)`（Cookie auth） | ✅ | `router = APIRouter(..., dependencies=[Depends(get_current_admin_user)])` |
| 前端管理 UI（`frontend/app/admin`） | ✅ | 见前端 admin 路由 |
| `extra_config.source = "system_bootstrap"` 标记自动创建的 provider，重命名后仍能识别 | ✅ | line 506-525 |

### E. 可观测 / 容错

| 能力 | 状态 | 实现 |
|---|---|---|
| `prompt.prefix_hash` 日志（哈希 + tool_count + response_format 类型 + system 总字节） | ✅ | `LLMRouter._system_prefix_signature` |
| `llm_provider_failed` warn（含 error_type） | ✅ | line 173-178 |
| `llm.timeout` warn + `llm.retry` info | ✅ | line 225-251 |
| `llm.stream_stall` / `llm.total_timeout` warn | ✅ | `llm/router.py` |
| `image_generation.retry` / `image_generation.failed` warn | ✅ | `seedream.py:62-79` |
| Image 失败返回 placeholder URL，不 raise（创作工坊不被一次失败卡死） | ✅ | `seedream.py:80` + `IMAGE_PLACEHOLDER_URL` |
| Grok web_search 部署失败时记 `_web_search_disabled_reason` 后续直接跳过 | ✅ | `llm/grok.py:148-184` |
| `token_usage` 表写 `provider_name` / `model_id`（identity 透传到分析侧） | ✅ | `models/token_usage.py` + `game_service._consume_turn` |

### F. 配置 / 边界

| 能力 | 状态 | 实现 |
|---|---|---|
| `LLM_CALL_TIMEOUT_SECONDS=60` | ✅ | `config.py:66` |
| `LLM_CALL_MAX_RETRIES=1` / `LLM_CALL_RETRY_BACKOFF_SECONDS=0.5` | ✅ | `config.py:67-68` |
| `MODEL_PROBE_TTL_HOURS=168` | ✅ | `config.py:40` |
| `MODEL_MANAGEMENT_BOOTSTRAP_ENABLED=true` | ✅ | `config.py:41` |
| API key 全部环境变量化（`api_key_env_name` 字段不存 secret 本身） | ✅ | `_configured_secret_value` |
| Slot 绑定校验 `model_kind` 与 slot 期望一致（text vs image） | ✅ | `bind_model_slot` line 1131 |
| 业务代码禁止 hardcode provider/model 名（必走 `resolve_slot_*`） | ✅ | CLAUDE.md 约束；`get_game_service` 全部 slot 解析 |

## 2. 关键能力实现要点

### 2.1 First-token timeout + bounded retry（Phase 2.B.1）

**问题**：之前 `LLMRouter.stream_with_tools` 直接 `async for` 上游 provider，DeepSeek 偶发抽风（30s 不返第一个 token）整局僵在那；fallback chain 也只在 generator 抛错时才切换，超时一直挂着用户看不到。

**解决**：把 provider 流式拆成"等第一个事件"和"第一个事件之后继续取 chunk"两段，每次 `__anext__` 都有停顿超时。第一段超时 / transient error 可以重试（同 provider）或 fallback（chain 下一个）；一旦已有输出就不能重启，避免把两段答案拼接。`admin_generation` / `research_planning` 另有 600 秒完整调用 deadline，防止上游持续发心跳或零碎 token 而永不 EOF。

**实现**：
- `llm/router.py::_stream_one_provider`：用 `iterator.__anext__()` 单独 await 拿首个事件，超时阈值取 `settings.llm_call_timeout_seconds`（默认 60s）
- 重试条件：`asyncio.TimeoutError` 总是重试；其他异常按 `_is_transient` 判断（类名 in `_TRANSIENT_EXC_NAMES` 或 `status_code` ∈ [500, 600)）
- 重试上限 `settings.llm_call_max_retries`（默认 1，即最多 2 次尝试）；之后让 outer chain 切到下一个 provider
- 类名匹配规避了 import 顺序耦合：不需要在 router 里 import openai / anthropic / httpx
- `services/model_management.py` 只给生成槽注入 `total_timeout_seconds=600`；实时游戏槽不受这个长任务 deadline 影响

**取舍**：完整 deadline 不是全局默认，只用于离线生成槽。正常长输出可以运行数分钟，但单次模型调用不能无限占住整条世界 workflow；超时后由当前节点按既有失败语义处理，不增加 circuit breaker 或额外重试层。

### 2.2 Slot → Binding → Model → Provider 三层动态绑定

**问题**：早期业务代码 `DeepSeekProvider()` 直接 new，换模型要改 Python；多个用途想用不同模型档位（NPC 用便宜的、game_main 用强的、moderation 用最便宜的）只能加 if/else 硬编码。

**解决**：把"业务调用 → 实际模型"用一张 slot 绑定表解耦。业务代码全程只认 slot 名；admin 后台 `PUT /api/admin/model-slots/{slot_name}` 改 binding，下次新会话就生效。

**实现**：
- 9 个 slot 在 `SLOT_DEFINITIONS` 写死（`game_main` / `npc_agent` / `conversation_compression` / `ending_summary` / `admin_generation` / `moderation_slot` / `research_planning` / `research_summary` / `image_generation`）
- 每个 slot 声明 `required_capabilities`（如 `game_main` 需要 chat_basic + streaming + tool_use）
- 绑定时调 `_ensure_capabilities` 检查最近一次 probe 是否 fresh + passed；不通过直接 raise `ModelManagementError`
- `resolve_slot_router(db, slot_name)` 拿 binding → 构造 `LLMRouter(providers={model.id: provider}, identity={...})`；未绑定 fallback `_legacy_text_router`（DeepSeek 默认值）
- `LLMRouter.identity` 在 usage 事件里塞 `provider_name` / `model_id`，下游 `token_usage` 表落两列方便 admin 算"某 binding 这个月烧了多少"

**取舍**：拒绝了"用环境变量配 slot → model 名"——环境变量只能改一组，且改完要重启；DB 表能 admin UI 改 + audit log。代价是每次解析 slot 都查一次 DB，但 GameService 一个 turn 只解析一次，不是热路径。

### 2.3 Identity 注入 usage 事件

**问题**：当 `LLMRouter` 持有多个 provider 时，下游 `game_service` 写 `token_usage` 拿不到"实际跑的是哪个 binding"；fallback 触发后这个信息更乱。

**解决**：在 router 构造时通过 `identity={"provider_name": ..., "model_id": ...}` 注入；`stream_with_tools` 透传 usage 事件时，**不 clobber** provider 已设置的 identity 字段（少数 provider 自己会设），只在 missing 时填。

**实现**：`llm/router.py:162-168`：

```python
if event.get("type") == "usage":
    if stamped_provider_name and not event.get("provider_name"):
        event = {**event, "provider_name": stamped_provider_name}
    if stamped_model_id and not event.get("model_id"):
        event = {**event, "model_id": stamped_model_id}
```

`stamped_model_id` 优先取 `identity["model_id"]`，否则 fallback 到 `getattr(provider, "model", None)` —— provider 实例都有 `self.model` 字段。

**取舍**：拒绝了"在每个 provider 实现里都自己塞 identity"——provider 不该知道自己被绑到哪个 slot。在 router 层注入隔离干净。

### 2.4 Seedream image retry + placeholder fallback

**问题**：图像生成 (1) 比文本慢且易抽风（4-8s），(2) 创作工坊一个世界要生成 1 主图 + N 头像，挂掉一个不该让整个流程崩。

**解决**：
- 最多 3 次尝试（backoff 0.5s、2s）—只对 transient（`APIConnectionError` / `APITimeoutError` / `InternalServerError` / `RateLimitError` / 5xx `APIStatusError`）重试
- 最终失败**不 raise**，返回 `ImageResult(url=IMAGE_PLACEHOLDER_URL, model=...)`；上游创作工坊把 placeholder 持久化，admin 之后可以手动重生

**实现**：`llm/seedream.py:42-80`，`_is_transient` 显式 isinstance（这里 import openai 是 ok 的，因为本来就直接走 openai sdk）。

**取舍**：跟 `LLMRouter` 不同，这里**不复用** `LLMRouter._is_transient`——image 走 `OpenAICompatibleImageProvider.generate_image` 不是 stream_with_tools，没必要硬塞进 router 抽象里。两套 retry 逻辑并行，简单。

### 2.5 Bootstrap 自动建立 system 默认 provider

**问题**：fresh DB 启动时 `model_slot_bindings` 是空的，`resolve_slot_router` 全部走 legacy fallback —— 但 legacy 也只有 DeepSeek + Grok 这两条路；想用 Gemini / Claude 还得 admin 先手动建。新部署体验差。

**解决**：app 启动 / 任何 model_management 路由首次调用前，`ensure_default_model_management_state` 看 `MODEL_MANAGEMENT_BOOTSTRAP_ENABLED` + 各 settings 字段的存在性，自动建：
- "系统默认 DeepSeek" provider + 其上的 default / compression model + 5 个文本 slot 默认绑定（如果 `DEEPSEEK_API_KEY` 已配）
- "系统默认 xAI" provider + grok text/image model + research_summary / image_generation slot 默认绑定

**实现**：`services/model_management.py::_default_bootstrap_specs` line 410；`ensure_default_model_management_state` line 477。Bootstrap provider 通过 `extra_config.source = "system_bootstrap"` 标识，admin 后续重命名仍能识别（按 type + api_key_env_name 兜底匹配）。

**取舍**：拒绝了"DB migration 写死 seed 数据"——seed 跑一次就锁死值；这里每次 app 启动都校准（renamed bootstrap 仍能更新 base_url / status）。代价是有点慢，但只在 list/dashboard 路由前跑一次。

## 3. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/llm/base.py` | `LLMProvider` / `ImageGenerator` / `WebSearcher` 抽象 + `ImageResult` / `WebSearchResult` |
| `backend/llm/router.py` | `LLMRouter` + first-token timeout + bounded retry + identity + `_system_prefix_signature` |
| `backend/llm/deepseek.py` | DeepSeek（OpenAI 兼容，默认 fallback provider） |
| `backend/llm/claude.py` | Claude（anthropic SDK，response_format 静默忽略） |
| `backend/llm/gemini.py` | Gemini（OpenAI 兼容 generativelanguage 端点） |
| `backend/llm/grok.py` | xAI Grok（chat + Responses API web_search + Imagine 生图，三接口合一） |
| `backend/llm/openai_compatible.py` | OpenAI 兼容通用 chat + image provider 基类 |
| `backend/llm/seedream.py` | Seedream image（独立 retry + placeholder fallback） |
| `backend/services/model_management.py` | 三层 slot/provider/model + `resolve_slot_router` / `bind_model_slot` / `probe_model_capabilities` / bootstrap |
| `backend/services/tavily_search.py` | Tavily 联网检索（独立 service，不进 router） |
| `backend/api/admin_models.py` | admin 管理路由（dashboard / providers / models / slots / probe / healthcheck） |
| `backend/models/model_management.py` | 4 张 DB 表 ORM 定义 |
| `backend/services/image_storage.py` | `IMAGE_PLACEHOLDER_URL`（image 失败兜底） |

## 4. 配置项

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `LLM_CALL_TIMEOUT_SECONDS` | `60.0` | first-token 超时（秒） |
| `GENERATION_TOTAL_TIMEOUT_SECONDS` | `600.0` | 生成槽单次完整调用上限（代码常量） |
| `LLM_CALL_MAX_RETRIES` | `1` | 单 provider transient 重试次数 |
| `LLM_CALL_RETRY_BACKOFF_SECONDS` | `0.5` | 重试退避秒数 |
| `MODEL_PROBE_TTL_HOURS` | `168` | 能力探活结果缓存 TTL（一周） |
| `MODEL_MANAGEMENT_BOOTSTRAP_ENABLED` | `true` | 启动时自动建 system 默认 provider/binding |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` | — | DeepSeek 凭证 + 端点 |
| `GROK_API_KEY` / `GROK_BASE_URL` / `GROK_MODEL` / `GROK_IMAGE_MODEL` | — | xAI 凭证 + 默认模型 |
| `ANTHROPIC_API_KEY` | — | Claude 凭证 |
| `GEMINI_OPENAI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai` | Gemini OpenAI 兼容端点 |
| `LLM_DEFAULT_MODEL` / `LLM_COMPRESSION_MODEL` | `deepseek-chat` | legacy fallback router 默认模型 |
| `TAVILY_API_KEY` | — | Tavily 联网检索凭证 |

| Slot | 默认 model_kind | required_capabilities | 用途 |
|---|---|---|---|
| `game_main` | text | chat_basic + streaming + tool_use | Director / Narrator 主链路 |
| `npc_agent` | text | chat_basic + streaming | NPC 对话（可绑廉价档） |
| `conversation_compression` | text | chat_basic + streaming | 长会话压缩（同时被 NPC reflection 复用） |
| `ending_summary` | text | chat_basic + streaming + json_output | 结局 JSON 总结 |
| `admin_generation` | text | chat_basic + streaming + tool_use | 创作工坊主链路 |
| `moderation_slot` | text | chat_basic + streaming + tool_use | 内容审核（廉价档） |
| `research_planning` | text | chat_basic + streaming + tool_use | 联网研究规划 |
| `research_summary` | text | chat_basic + streaming | 研究摘要（默认 grok） |
| `image_generation` | image | image_generation | 世界 / 角色封面图 |

## 5. 数据库 schema

```sql
model_providers (
  id, name UNIQUE, provider_type,
  base_url, api_key_env_name,        -- 环境变量名，secret 本身不入库
  extra_config JSON,                 -- {"source": "system_bootstrap"} 等
  status,                            -- active / invalid
  last_healthcheck_at, last_healthcheck_error,
  ...
)
INDEX (provider_type, status)

provider_models (
  id, provider_id FK, model_id, display_name,
  model_kind,                        -- text | image
  is_enabled, notes,
  ...
)
UNIQUE (provider_id, model_id, model_kind)

model_slot_bindings (
  id, slot_name UNIQUE, model_id FK,
  status,                            -- active
  last_verified_at, last_verified_error,
  ...
)

model_capability_probes (
  id, model_id FK, capability,       -- chat_basic | streaming | tool_use | json_output | image_generation | web_search
  status,                            -- passed | failed
  latency_ms, error_message, response_sample,
  verified_at, expires_at,           -- TTL = MODEL_PROBE_TTL_HOURS
)
INDEX (model_id, capability)
INDEX (verified_at)
```

## 6. 测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_llm_router.py` | first-token timeout / 重试 / fallback chain / identity 注入 / prefix_hash |
| `tests/test_deepseek_provider.py` | DeepSeek streaming + tool_use + response_format |
| `tests/test_grok_provider.py` | Grok chat + web_search 兜底 + image fallback |
| `tests/test_model_management_api.py` | admin CRUD + bind + probe + healthcheck + bootstrap |
| `tests/test_orchestrator_npc_slot.py` | npc_agent slot 解析 + 未绑定 fallback 到 game_main |

## 7. 已知短板与未来扩展

### P1

- **Provider-level circuit breaker**：当前同一 provider 连续失败仍按 `max_retries` 重试，没有"暂时拉黑这个 provider 30s"的机制。高频翻车时反而增加 latency。

### P2

- **Streaming 中途断流的二次重试**：first event 后的中断（partial output 已发给前端）当前直接 raise，前端走 connection_lost。理论上可以做"前端记 received_chars，断了重发请求带 offset"，但要 provider 支持 prefix-cache 才划算。
- **能力探活的成本**：probe 跑实际 LLM 调用，admin 一键验证全 model 时容易触发各家的 rate limit。可以加并发 cap 或异步队列。
- **Slot 多 binding（A/B）**：当前一个 slot 只能绑一个 model；想做"灰度切流"或"按 user 分流"需要 binding 表加 weight / criterion 字段。

### P3

- **跨 region failover**：当前 fallback chain 是 provider 维度的，没考虑同 provider 多区域 endpoint。如果 DeepSeek 某区域全挂，整条 chain 都跪。
- **Cost-aware routing**：每个 turn 根据当前 session 累计成本动态选模型档位（接近 cap 自动降到便宜档）。需要把 cost guardrail 跟 router 打通。
- **Embedding 模型独立 slot**：当前 embedding 走 `EMBEDDING_*` 环境变量直接配，没进 slot 体系。Phase 2 把它收进来后业务能跟其他 slot 一样 admin 改。
