# 可观测与备份

> 状态截至 2026-05-08。覆盖 Sentry 后端/前端集成、`/health` 健康检查、SQLAlchemy 连接池、structlog 日志脱敏、关键 structured event 清单（grep 自动整理）、`ops/backup.sh` 03:00 备份与恢复流程。

这份是给 SRE / 运维 / 排障读的。线上出问题先看哪里、怎么看、看什么字段——三件事在这里都给到。配置部分跟 `docs/operations/deploy-and-config.md` 互补：那份是"怎么把项目跑起来"，这份是"跑起来之后怎么观测它健康"。

---

## 1. 能力矩阵

### A. Sentry 错误追踪

| 能力 | 状态 | 实现 |
|---|---|---|
| 后端 SDK init（FastAPI / SQLAlchemy / logging 集成） | ✅ | `backend/sentry_config.py::init_sentry` 在 `main.py:25` 主入口调 |
| 后端 DSN env：`BACKEND_SENTRY_DSN` 优先，回落 `SENTRY_DSN` | ✅ | `sentry_config.py:57` |
| `before_send` 脱敏（递归 scrub + query string） | ✅ | `sentry_config.py:48-53` |
| `release` 标签从 `RELEASE_TAG` 注入 | ✅ | `sentry_config.py:72` |
| `environment` 标签从 `ENVIRONMENT` 注入 | ✅ | `sentry_config.py:71` |
| `traces_sample_rate=0.0`（不采性能 trace） | ✅ | `sentry_config.py:79` |
| 前端 SDK（@sentry/nextjs） | ✅ | `frontend/sentry.{server,edge}.config.ts` + `instrumentation.ts` |
| 前端 DSN env：`NEXT_PUBLIC_SENTRY_DSN` | ✅ | 三个 sentry config 文件统一读 |
| 前端 sourcemap 上传 | ✅ | `next.config.ts` 内 `withSentryConfig({...sourcemaps})`，需 `SENTRY_AUTH_TOKEN` + `SENTRY_ORG` + `SENTRY_PROJECT` |
| 全局错误边界 → 自动 captureException | ✅ | `frontend/app/global-error.tsx:14` `Sentry.captureException(error)` |
| Router transition 追踪 | ✅ | `instrumentation-client.ts:14` `onRouterTransitionStart` |
| 真实 DSN smoke test | 🔵 | 待开生产 DSN 后跑一次端到端验证 |

### B. `/health` 健康检查

| 能力 | 状态 | 实现 |
|---|---|---|
| 端点：`GET /health` | ✅ | `backend/main.py:76-95` |
| DB ping（`SELECT 1`） | ✅ | `check_database()` |
| Redis ping | ✅ | `check_redis()` |
| 任一组件不健康返 503 | ✅ | `main.py:86-93` `raise HTTPException(503)` |
| 返 components 字段（细分 db / redis 状态） | ✅ | `{"status": "ok|degraded", "components": {...}}` |
| Redis client 用完即关 | ✅ | `check_redis` line 71-72 finally aclose |
| 健康检查不需要认证 | ✅ | router 直接挂在 app 上，没 Depends |
| 集成 Docker Compose healthcheck | 🟡 | compose 当前 healthcheck 只用 `pg_isready` + `redis-cli ping`，不调 backend `/health` |

### C. structlog 结构化日志

| 能力 | 状态 | 实现 |
|---|---|---|
| 全局 logger（structlog） | ✅ | `middleware/logging.py::logger = structlog.get_logger()` |
| HTTP 请求埋点（method / path / status / duration_ms） | ✅ | `LoggingMiddleware.dispatch` line 46-52 |
| 日志脱敏 helper `scrub_log_value` | ✅ | `middleware/logging.py:27-37` |
| 脱敏字段：password / api_key / authorization / cookie / session / x_admin_key | ✅ | `SENSITIVE_FIELDS` set |
| key 大小写不敏感（`_is_sensitive_key` 归一化） | ✅ | `middleware/logging.py:22-24` 同时支持 dash 和 underscore |
| Mapping / list / tuple 递归脱敏 | ✅ | 三种 collection 类型都处理 |
| 应用在 Sentry before_send | ✅ | `sentry_config.py:48-53` 调 `_scrub_value` + `_scrub_query_string` |
| query string 脱敏（解析 + 重组） | ✅ | `sentry_config.py:37-45` |
| `print()` 全局禁用（用 logger） | ✅ | CLAUDE.md 项目原则 |

### D. 关键 structured event 清单（grep 整理）

| 事件名 | logger 级别 | 文件 / 触发场景 |
|---|---|---|
| `request` | info | `middleware/logging.py:47` — 每个 HTTP 请求 |
| `stage.timing` | info | `engine/orchestrator.py:67` — 每阶段 wall-time（moderation_input / world_tick / director / npc_sequential / npc_parallel / narrator_first_token / narrator_prelude / narrator / moderation_output / turn_total / compressor）|
| `compressor.run` | info | `orchestrator.py:202`（成功）/ `:287`（失败 retry）— 上下文压缩日志 |
| `compressor.retry` | warning | `orchestrator.py` 压缩重试 |
| `prompt.prefix_hash` | info | LLM prefix cache hit/miss 追踪 |
| `llm.timeout` | warning | `llm/router.py:226` — LLM 第一个 token 超时 |
| `llm.retry` | info | `llm/router.py:235` / `:246` — provider transient retry |
| `llm_provider_failed` | warning | LLM provider chain 失败 |
| `llm_returned_empty` | warning | LLM 返回空字符串 |
| `llm_no_tool_or_json` | warning | LLM 既没 tool_use 也没 valid JSON |
| `llm_json_retry_succeeded` | info | LLM JSON 校验失败重试成功 |
| `llm_json_retry_failed` | warning | LLM JSON 校验失败重试也失败 |
| `director.parse_failure_retrying` | warning | `engine/director_agent.py:307` — director 工具输出解析失败首次 |
| `director.parse_failure` | warning | `director_agent.py:371` — director 解析最终失败 |
| `director.unrecoverable` | warning | `orchestrator.py:419` — director 崩溃终止 turn |
| `director.json_mode_empty_output` / `_non_object` / `_provider_failed` / `_parse_failed` | warning | `engine/director_agent.py` json mode 路径异常 |
| `director_inform_npc_unknown` | warning | `orchestrator.py:504` — Director inform_npc 指向不存在的 NPC |
| `director_tool_payload_malformed` | warning | director 工具 payload 不合规 |
| `npc.run_failed` | warning | `orchestrator.py:704` / `:724` — 单个 NPC LLM 调用失败（顺序 + 并行两路径） |
| `npc_voice_anchor_load_failed` | warning | `orchestrator.py:579` — voice anchor 加载失败 |
| `npc_peer_relations_load_failed` | warning | `orchestrator.py:594` — peer relations 加载失败 |
| `npc_reflection_load_failed` | warning | `orchestrator.py:565` — NPC reflection 加载失败 |
| `npc_reflection.updated` | info | `services/npc_reflection_service.py:194` — reflection 成功更新 |
| `npc_reflection.llm_failed` | warning | `npc_reflection_service.py:160` |
| `npc_reflection.empty_output` | warning | `npc_reflection_service.py:170` |
| `npc_reflection.maybe_failed` | warning | `npc_reflection_service.py:226` |
| `npc_reflection.background_task_failed` | warning | `services/game_service.py:55` — async reflection task 异常 |
| `npc_memory_batch_query_failed` | warning | `orchestrator.py:537` — batch_query_npc_memories 失败 |
| `batch_query_embed_failed` | warning | embedding batch 失败 |
| `embedding.failed` / `embedding.timeout` | warning | embedding 调用失败 / 超时 |
| `narrator_prelude_failed` | warning | `orchestrator.py:780` — narrator 早流式 prelude 抛错 |
| `case_board_invalid_ops` | warning | `orchestrator.py:839` — director 案件板 op 引用不存在的 clue_id |
| `output_filtered` | warning | `orchestrator.py:914` — moderation 输出审核命中（不阻断） |
| `moderation_llm_failed` | warning | `engine/moderation.py:148` — LLM 审核失败兜底本地规则 |
| `moderation_slot_resolve_failed` | warning | `orchestrator.py:82` — moderation slot 解析失败 |
| `info_propagation_error` | warning | `engine/world_simulator.py:62` — 信息传播失败 |
| `intent_system_error` | warning | NPC intent 计算失败 |
| `world_clock_error` | warning | `world_simulator.py:70` — 时钟推进异常 |
| `image_generation.retry` | warning | `llm/seedream.py:64` |
| `image_generation.failed` | warning | `llm/seedream.py:74` |
| `image_generation_failed` / `hero_image_failed` / `poster_image_failed` / `avatar_image_failed` / `visual_brief_generation_failed` | warning | 创作工坊配图各阶段失败 |
| `image_saved_local` / `image_saved_oss` / `image_deleted_local` / `image_deleted_oss` | info | 图片存储读写日志 |
| `generation_task_record_event_failed` | warning | `services/generation_task_service.py:421` — 创作工坊 SSE 事件入库失败 |
| `world_base_generation_failed` / `script_base_generation_failed` / `characters_generation_failed` / `events_generation_failed` / `endings_generation_failed` | error | 创作工坊各阶段 LLM 生成失败 |
| `world_validation` / `script_validation` | warning | 创作工坊 schema 校验告警 |
| `world_critic_repair_failed` / `script_critic_repair_failed` | warning | 创作工坊 critic 修复失败 |
| `world_generation_task_failed` / `script_generation_task_failed` / `generation_background_task_failed` | exception | 创作工坊整体任务失败 |
| `playable_recommendations_trimmed` | info | playable 推荐被 trim |
| `playable_selection_failed` / `script_playable_selection_failed` | warning | playable 选择失败 |
| `research_plan_failed` / `research_query_failed` / `research_stage_failed` / `research_summary_failed` | warning | Tavily 联网检索各阶段失败 |
| `research_skipped_by_policy` | info | 检索被策略跳过 |
| `tavily_search_error` / `tavily_search_skipped` / `tavily_search_timeout` | warning | Tavily API 直接异常 |
| `grok_image_generation_failed` / `grok_web_search_failed` / `grok_web_search_disabled` / `grok_web_search_skipped` | warning | xAI grok 异常 |
| `xai_sdk_not_installed` | warning | xai-sdk 缺失 |
| `model_management_bootstrap_failed` | warning | `main.py:34` — 启动 bootstrap 默认 provider/slot 失败 |
| `game_stream_failed` | warning | `api/game.py:196` — SSE event_generator 顶层异常 |
| `ending_summary_generation_failed` / `ending_summary_json_parse_failed` | warning | 结局总结失败 |
| `no_tool_call` | warning | LLM agent 没返工具调用 |

### E. SQLAlchemy 连接池

| 能力 | 状态 | 实现 |
|---|---|---|
| async engine（asyncpg 驱动） | ✅ | `backend/database.py:20` `create_async_engine(...)` |
| `pool_size` 默认 5 | ✅ | `settings.db_pool_size` + `_engine_options` |
| `max_overflow` 默认 10 | ✅ | `settings.db_max_overflow` |
| `pool_timeout` 默认 30s | ✅ | `settings.db_pool_timeout` |
| pool 配置仅对非 sqlite 启用 | ✅ | `database.py:9-16` `if not settings.database_url.startswith("sqlite")` |
| `expire_on_commit=False` | ✅ | `async_sessionmaker(...)` |
| `echo=settings.debug` | ✅ | DEBUG 时 SQL 全打 |
| 健康检查走独立 session | ✅ | `main.py::check_database` `async with async_session()` |
| 长事务 / 连接泄漏告警 | ❌ | 当前未配置 |

### F. 备份与恢复

| 能力 | 状态 | 实现 |
|---|---|---|
| `ops/backup.sh`（pg_dump + gzip） | ✅ | 32 行 shell |
| 03:00 daily cron（容器内自循环） | ✅ | `docker-compose.yml:85-104` busybox-compatible 时差计算 |
| 7 天滚动保留 | ✅ | `BACKUP_RETENTION_DAYS=7` + `find -mtime +7 -delete` |
| 命名 pattern：`inkwild-YYYY-MM-DD.sql.gz` | ✅ | `ops/backup.sh:23-24` `stamp="$(date +%F)"` |
| named volume 持久化 | ✅ | `backups:/backups`（compose volumes） |
| 失败不致命（仅 echo + 下次再跑） | ✅ | `docker-compose.yml:103` `|| echo` |
| `restart: unless-stopped` 容器重启自恢复 | ✅ | compose line 105 |
| 恢复命令文档化 | ✅ | `ops/backup.sh:8-12` 注释 |
| 异地备份 / 离机备份 | ❌ | 当前只在同一 docker volume，要加 OSS / S3 sync |
| 备份完整性校验（pg_restore --list） | ❌ | 跑完不验证可读性 |

---

## 2. 关键能力实现要点

### 2.1 Sentry 后端 init + before_send 脱敏

**问题**：错误上报到 Sentry 不能把 cookie / api_key / password 一起带过去——一来违规，二来真的有人会泄密。

**解决**：`init_sentry` 注册 `before_send=before_send` hook。每个 event 落地前递归遍历 dict / list / tuple，凡是 key 命中 `SENSITIVE_FIELDS`（`password` / `api_key` / `authorization` / `cookie` / `session` / `x_admin_key`）的字段全替换成 `[Filtered]`。query string 单独处理（先 parse 再 urlencode 过滤）。

**实现**：
- 模块：`backend/sentry_config.py`（81 行）
- DSN 优先级：`BACKEND_SENTRY_DSN` > `SENTRY_DSN`（兼容旧字段）
- 集成：FastApiIntegration / LoggingIntegration / SqlalchemyIntegration 三个
- traces_sample_rate=0.0（不采性能 trace，节约配额）
- ImportError fallback：`sentry-sdk` 没装也不崩（line 66-67）
- DSN 空时 init 直接 return（开发环境无 DSN 不报错）

**取舍**：脱敏字段选了 6 个核心；如果业务发现 LLM 调用 payload 里夹带 user_id 或自定义 token 也想过滤，应该扩 `SENSITIVE_FIELDS` 而不是改 hook 逻辑。`scrub_log_value` 跟 `_scrub_value` 是两份近乎一样的代码（一份在 `middleware/logging.py` 给业务 logger 用，一份在 `sentry_config.py` 给 Sentry 用）——P3 可统一到 `utils/scrub.py`。

### 2.2 `/health` 双向检查 + 503 降级

**问题**：load balancer / k8s liveness probe / docker compose healthcheck 都要一个机器可读的健康状态接口；只检查 backend 进程活着不够，DB 或 Redis 挂掉时 backend 接受请求也是徒劳。

**解决**：`/health` 同时检查 db（`SELECT 1`）和 redis（PING），任一失败返 503 + `components` 字段说明哪个组件挂了；都正常返 200 + `{"status": "ok", "components": {"database": "ok", "redis": "ok"}}`。

**实现**：
- 入口：`backend/main.py:76-95`
- DB 检查：`check_database()` 复用 `async_session` 跑 `text("SELECT 1")`
- Redis 检查：`check_redis()` 临时建 client 调 `ping()`，finally `aclose()` 不泄漏连接
- 失败兜底：每个 check 单独 try/except，结果写进 components dict；最后整体判定
- 不需要认证（line 76 router 直接挂 app，没 Depends）

**取舍**：拒绝了"DB 挂时还返 200"——k8s / LB 探活全靠这个，假阳性会把崩溃流量扔给挂了的服务。当前 docker-compose 的 healthcheck 用的是 `pg_isready` / `redis-cli ping` 直连基础设施，没调 backend `/health`——这是 P2 待补，目前 backend 健康靠 `depends_on` 隐式保证。

### 2.3 structlog 全链路脱敏

**问题**：业务代码里 `logger.info("xxx", request=request_dict)` 很方便但容易把 cookie / authorization header 一起打进日志。Sentry 那一层有脱敏，但 stdout / 远端日志 sink 也得有。

**解决**：`middleware/logging.py::scrub_log_value` 提供脱敏 helper，递归处理 Mapping / list / tuple；命中 `SENSITIVE_FIELDS` 的 key 替换为 `[Filtered]`。业务代码可以显式调（写 `request=scrub_log_value(req.headers)`）。

**实现**：
- helper：`scrub_log_value`（line 27-37）
- key 归一化：`_is_sensitive_key`（line 22-24）大小写 + dash/underscore 都识别
- 当前用法：scrub_log_value 是 helper，业务里没强制每个 logger 调用前调。**关键事实**是 sensitive 字段名（authorization、cookie、session）平时不会作为 logger.info 的 keyword 名，业务侧不主动塞就不会泄漏；Sentry 那一层 before_send 是兜底
- HTTP 请求中间件：`LoggingMiddleware.dispatch` 只打 method/path/status/duration_ms，**不打 headers / body**，从源头规避

**取舍**：没在 structlog processor 链路里强制注册 scrub processor——会有性能开销 + 开发会"不知道为什么字段被改了"造成困惑。当前靠"中间件不打敏感字段 + Sentry before_send 兜底 + 业务显式调"三层防御。如果未来发现日志泄漏可加 processor。

### 2.4 关键 event 清单的运维用法

§1.D 那张表是给排障用的——按"现象 → 看哪个事件"反查：

- **某 turn 卡死/超时**：grep `stage.timing` 看哪个 stage `duration_ms` 异常；配合 `llm.timeout` / `llm.retry` 看 LLM 是不是慢
- **多 NPC 场景轮流刷屏 / 单 NPC 沉默**：grep `npc.run_failed` 看是不是某 NPC 抛错被 fallback；`stage.timing stage=npc_sequential` vs `npc_parallel` 看走哪条路径
- **director 行为奇怪**：grep `director.parse_failure_retrying` / `director.parse_failure` / `director.unrecoverable`；`director_inform_npc_unknown` 看 director 有没幻觉 NPC 名
- **moderation 异常**：grep `moderation_llm_failed` / `output_filtered` / `moderation_slot_resolve_failed`
- **创作工坊任务失败**：grep `world_generation_task_failed` / `script_generation_task_failed` / `generation_task_record_event_failed`
- **图片生成 retry**：grep `image_generation.retry` 看尾部一段；`hero_image_failed` / `poster_image_failed` 看创作工坊配图
- **NPC reflection 没生效**：grep `npc_reflection.updated` 看触发频次；`npc_reflection.llm_failed` / `npc_reflection.background_task_failed` 看异常路径
- **embedding 召回失败**：grep `embedding.failed` / `embedding.timeout` / `npc_memory_batch_query_failed`
- **联网检索异常**：grep `tavily_search_error` / `research_*_failed`

### 2.5 daily 备份 + 7 天滚动 + 恢复

**问题**：DB 数据无限重要——剧本 / 玩家进度 / 创作工坊产物全在里面。需要稳定、低维护成本的备份方案。

**解决**：独立 `backup` service（postgres:16-alpine 镜像），用 busybox-compatible 时差计算睡眠到下个 03:00 → 跑 `/scripts/backup.sh` → 用 `pg_dump | gzip` 写 named volume `backups` → `find -mtime +7 -delete` 删掉过期 → 循环。失败不阻断（仅 echo + 下次再跑），`restart: unless-stopped` 保证容器重启后继续。

**实现**：
- 脚本：`ops/backup.sh`（32 行）
- 调度：`docker-compose.yml:85-104` 容器内 shell 自循环
- 环境变量：`PGHOST=db` / `PGUSER=postgres` / `PGPASSWORD=postgres` / `PGDATABASE=inkwild` / `BACKUP_DIR=/backups` / `BACKUP_RETENTION_DAYS=7`
- 命名：`inkwild-YYYY-MM-DD.sql.gz`（`stamp="$(date +%F)"`）
- 持久化：named volume `backups`（compose `volumes:` 段声明）

**恢复**（来自 `ops/backup.sh` 注释）：
```bash
# 从宿主（stack 运行时）：
gunzip < inkwild-2026-05-08.sql.gz | docker compose exec -T db psql -U postgres -d inkwild

# 从容器内部：
gunzip < /backups/inkwild-2026-05-08.sql.gz | psql -h db -U postgres -d inkwild
```

**取舍**：用容器内 sleep loop 而不是宿主 cron——好处是部署只需要 `docker compose up`，没有"docker 起好了但 cron 没配"的两态。缺点：容器重启时间不规律的话备份点会漂移，但每天一次的密度下不重要。备份只在同一 docker volume 是 P2 风险——主机磁盘炸的话备份一起没——上线前应该 sync 到 OSS / S3 / 异地（详见 §4 P2）。

---

## 3. SQLAlchemy 连接池详解

| 维度 | 默认 | env override | 含义 |
|---|---|---|---|
| `pool_size` | 5 | `DB_POOL_SIZE` | 长期保持的连接数 |
| `max_overflow` | 10 | `DB_MAX_OVERFLOW` | 高峰允许超出 pool_size 的临时连接数（总上限 = pool_size + max_overflow = 15） |
| `pool_timeout` | 30s | `DB_POOL_TIMEOUT` | 取连接的等待超时 |
| `expire_on_commit` | False | — | commit 后不重读对象（async 必须） |
| `echo` | settings.debug | `DEBUG` | True 时打印所有 SQL |

实现：`backend/database.py:7-21`，sqlite URL 跳过 pool 配置（不支持）。

**实操建议**：
- 单实例 backend + 30 actions/min/user × 平均 turn 内 ~10 SQL 调用 → 默认 5+10 一般够
- 看到 `pool_timeout` 异常 → 连接泄漏 / 长事务 → grep 慢查询 → P3 待加监控
- 单实例承载 ~50 并发用户后建议 pool_size 升 10 / max_overflow 升 20

---

## 4. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/sentry_config.py` | 后端 Sentry init + before_send 脱敏 |
| `backend/main.py` | FastAPI 入口 + `/health` + Sentry init 调用 |
| `backend/middleware/logging.py` | structlog HTTP 中间件 + scrub helper |
| `backend/database.py` | async engine + 连接池配置 |
| `frontend/sentry.server.config.ts` | 前端 server runtime Sentry init |
| `frontend/sentry.edge.config.ts` | 前端 edge runtime Sentry init |
| `frontend/instrumentation.ts` | Next.js instrumentation 入口（按 runtime 路由 sentry config） |
| `frontend/instrumentation-client.ts` | 浏览器侧 Sentry init + router transition tracking |
| `frontend/next.config.ts` | `withSentryConfig` 集成 + sourcemap 上传 |
| `frontend/app/global-error.tsx` | 全局错误边界 → captureException |
| `ops/backup.sh` | DB pg_dump + gzip + 滚动删除 |
| `docker-compose.yml` | backup service 03:00 cron 编排 |

---

## 5. 配置项

详见 `docs/operations/deploy-and-config.md §2.2` 全清单。本文档相关核心：

| env | 默认 | 含义 |
|---|---|---|
| `BACKEND_SENTRY_DSN` | `""` | 后端 Sentry DSN（优先） |
| `SENTRY_DSN` | `""` | 兼容旧字段 |
| `NEXT_PUBLIC_SENTRY_DSN` | `""` | 前端 DSN |
| `SENTRY_AUTH_TOKEN` | `""` | sourcemap 上传，仅 build 阶段 |
| `SENTRY_ORG` / `SENTRY_PROJECT` | `""` | sourcemap 关联 |
| `RELEASE_TAG` | `""` | Sentry release 标签 |
| `ENVIRONMENT` | `development` | Sentry environment 标签 |
| `DB_POOL_SIZE` | `5` | SQLAlchemy pool |
| `DB_MAX_OVERFLOW` | `10` | pool overflow |
| `DB_POOL_TIMEOUT` | `30` | 取连接超时秒数 |
| `BACKUP_RETENTION_DAYS` | `7`（compose env 内） | 备份滚动保留天数 |

---

## 6. 已知短板与未来扩展

### P1（上线前必须确认）

- **Sentry 真实 DSN smoke test**：当前代码路径都对，但没在生产 DSN 上端到端验证过。上线前必须故意抛个 exception，确认 Sentry 那边能收到 + `[Filtered]` 字段能 scrub
- **备份只在同一 docker volume**：主机磁盘炸的话备份一起没。上线前必须加 OSS/S3 sync 异地备份（cron 或 backup.sh 末尾扩展）

### P2

- **Compose healthcheck 调 `/health` 而不是 `pg_isready`**：当前 backend 没自己的 healthcheck，依赖 `depends_on` 隐式；改成调 `/health` 能更早暴露 Redis 不可用
- **DB 慢查询 / 连接泄漏告警**：当前没埋点，pool_timeout 异常只在调用方 catch；可加 `events.PoolEvents.checkout` 监控连接持有时间
- **structlog 跟 sentry_config 的 scrub 逻辑重复**：两份近乎一样的代码（`scrub_log_value` vs `_scrub_value`），抽到 `utils/scrub.py` 统一
- **备份完整性校验**：跑完 `pg_restore --list` 验证文件可读
- **关键 event 看板**：当前 §1.D 那个清单是 grep 整理的；可在 grafana / sentry 上做 dashboard 把高频 warning 跑成图

### P3

- **traces_sample_rate 提升 + 性能监控**：当前 `traces_sample_rate=0.0`，不采性能 trace；上规模后可调 0.05-0.1 看 LLM 调用瓶颈
- **多区域备份**：当前 backup volume 单点；多区域部署需要扩
- **日志中央化（loki / es）**：当前是 stdout，靠 docker logs 拉；上规模后接日志栈
- **健康检查扩展**：除了 DB / Redis 也可加 LLM provider connectivity 探活

---

## 7. 参考

- 配套：`docs/operations/deploy-and-config.md`（部署与全 env 清单）
- 配套：`docs/modules/cost-rate-moderation.md`（限流 / 成本 / 审核）
- 上层：`CLAUDE.md` 项目根（技术栈、目录结构、开发原则）
