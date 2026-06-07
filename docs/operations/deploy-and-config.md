# 部署与配置

> 状态截至 2026-05-23。覆盖 docker-compose 编排（dev/prod 双套）、环境变量全清单、Alembic 迁移流程、首位 admin 引导、Cloudflare/nginx 入口配置、静态文件目录与 OSS 切换。

这份文档目标是**实操向**：跟着这份从 0 把项目跑起来。配置项数量大，按域分组阅读；不用全填，每节标了"必填"和"可选"。

> **TL;DR**：
> - 本地开发：`docker compose up -d db redis`，前后端在 host 上跑 `npm run dev` / `uvicorn --reload`。
> - 整套都在 docker 跑（调试用）：`docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`。
> - **生产部署**：`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`。
> - 直接 `docker compose up` 跑的是**生产基底**（无 bind-mount、无 reload、`npm start`），但缺少生产 URL/cookie domain/CORS 等配置，**不要在服务器上这么用**。

---

## 0. 生产运维速查（2026-06-06 上线 · 权威，先看这节）

线上：主站 **https://inkwild.app**（+www）· 后台 **https://admin.inkwild.app**。

**环境**
- 服务器：AWS EC2 ap-northeast-1，`ssh inkwild`（ec2-user）。**共享机**——同机还跑 chatgpt2api / video-site-91 / gptimage / hermes，**只动 `inkwild` 项目，别碰别的**。
- 代码：私有库 clone 到 `~/inkwild`（服务器 deploy key，SSH 别名 `github-inkwild`）。
- 运行：compose 项目名 `inkwild`，命令前缀
  `docker compose -f docker-compose.yml -f docker-compose.prod.yml -p inkwild`
- 入口：host nginx（`/etc/nginx/conf.d/inkwild.conf`）反代 → frontend `127.0.0.1:3100`、admin `:3001`、backend `:8000`（`/api/` 路由到 backend）；certbot TLS 自动续期；域名走 Cloudflare（apex/admin 代理，www 直连源站）。
- 密钥：`~/inkwild/backend/.env`（gitignore，**永不进库**）；LLM provider key 另存 DB（admin 后台管）。
- 备份：每日 03:00 backup 容器；上线前全量备份留在 `~/inkwild_pre_wipe_*.sql.gz` + `~/inkwild_backend.env.bak`。

**改动分三类 —— 关键原则：代码走 git，密钥/数据不走 git**

**① 改代码（前端 / 后端 / 迁移）→ git + 重建镜像**
> 生产把代码 COPY 进镜像（无源码挂载），所以 `git pull` 后**必须 rebuild 镜像、重建容器**才生效——restart 无效。
```bash
# 本地：改 → 验证 → 提交推送
cd frontend && npx tsc --noEmit && npm run lint     # 后端改则 python -m pytest
git add -A && git commit -m "..." && git push
# 服务器：拉取 + 只重建改动的服务
ssh inkwild 'cd ~/inkwild && git pull --ff-only && \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml -p inkwild up -d --build <服务>'
```
- 前端改 → `frontend`；后端 / `migrations/` 改 → `backend`（启动自动跑 `alembic upgrade head`）；后台改 → `admin-frontend`。
- 只重建改动的服务；`db` / `redis` / 数据卷不动，数据安全。

**② 改密钥 / 配置（`.env`）→ 不走 git，改完重启容器**
> `.env` 是 gitignore 的；env_file 在容器启动时读，改完重启即可，不用 rebuild。
```bash
ssh inkwild   # 编辑 ~/inkwild/backend/.env
docker compose -f docker-compose.yml -f docker-compose.prod.yml -p inkwild up -d backend
```

**③ 改线上数据（世界 / 封面 / provider / 管理员）→ 直接 psql 或一次性脚本，不进 git**
```bash
# 建/提升管理员：
docker compose -f docker-compose.yml -f docker-compose.prod.yml -p inkwild \
  run --rm --no-deps backend python -m cli.create_admin <email> --password <pw>
```

**验证**：`curl -s -o /dev/null -w '%{http_code}\n' https://inkwild.app/`（再测 `/login`、`/api/worlds`）。

**已知坑**：① 全新空库首次迁移需库里先有 ≥1 admin（已修 `c45bcbdcd049`，但换库要记得）；② 前端宿主端口用 **3100**（3000 被同机 chatgpt2api 占）；③ 无蓝绿/零停机，重建期该服务短暂中断（几十秒）。

---

## 1. 启动能力矩阵

### A. Docker Compose 服务编排

仓库里共三份 compose 文件，**显式组合使用**：

| 文件 | 角色 | 说明 |
|---|---|---|
| `docker-compose.yml` | 生产基底（默认） | 6 个 service（db / redis / backend / frontend / admin-frontend / backup）。`npm start` + `uvicorn`（无 --reload），无源码 bind-mount，依赖镜像里 `npm run build` 产物 |
| `docker-compose.dev.yml` | dev override | bind-mount 源码 + `npm run dev` + `uvicorn --reload` + `DEBUG=true`，端口绑 `0.0.0.0` |
| `docker-compose.prod.yml` | prod override | 生产 URL（`https://inkwild.app` / `admin.inkwild.app`）、`SESSION_COOKIE_DOMAIN`、`CORS_EXTRA_ORIGINS`、`NEXT_PUBLIC_*` build args、端口绑 `127.0.0.1`（由前置 nginx 终结 HTTPS） |

> 历史上服务器上手写过一份 `docker-compose.override.yml`（Compose 默认会自动 merge），现已废弃——所有生产差异都进 `docker-compose.prod.yml` 跟仓库走，避免"隐式 override"导致 dev/prod 行为悄悄分叉。

| 能力 | 状态 | 实现 |
|---|---|---|
| `db`（postgres:16） | ✅ | `docker-compose.yml`，pgdata 持久化 + healthcheck |
| `redis`（redis:7） | ✅ | `docker-compose.yml`，无持久化（session lock + rate limit 都是临时态） |
| `backend`（FastAPI + uvicorn） | ✅ | 生产模式不带 `--reload`；dev override 加 `--reload` |
| `frontend`（Next.js） | ✅ | 生产 `npm start`（构建产物）；dev override `npm run dev` + bind-mount |
| `admin-frontend`（Next.js） | ✅ | 同 frontend，独立后台 |
| `backup`（postgres:16-alpine + 03:00 cron） | ✅ | `docker-compose.yml`，详见 `docs/operations/observability-backup.md §5` |
| `depends_on` healthcheck 串联 | ✅ | backend 等 db + redis 健康；backup 等 db |
| 端口映射 | ✅ | dev：`0.0.0.0:5432/6379/8000/3000/3001`；prod：`127.0.0.1:*`（仅 nginx 可访问） |
| volumes 持久化（pgdata + backups） | ✅ | named volumes |

### B. 配置加载

| 能力 | 状态 | 实现 |
|---|---|---|
| Pydantic Settings 全局配置类 | ✅ | `backend/config.py::Settings`（57 个字段） |
| `.env` 文件加载 | ✅ | `model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}` |
| 容器内可被 docker-compose `environment` override | ✅ | DB_URL / REDIS_URL / DEBUG 在 compose 里硬覆盖 |
| 不区分大小写 + 自动类型转换（int / float / bool） | ✅ | Pydantic Settings 行为 |
| 模型 provider 配置不在 env，在 DB（动态绑定） | ✅ | `services/model_management.py` + admin 后台 |
| 生产环境 `.env.example` 全字段注释 | ✅ | `backend/.env.example`（130 行，每条带中文注释） |
| 前端 `.env.example` | ✅ | `frontend/.env.example`（13 行，含 Sentry 字段） |

### C. 数据库迁移

| 能力 | 状态 | 实现 |
|---|---|---|
| Alembic async 迁移 | ✅ | `backend/migrations/env.py::run_migrations_online` 用 `create_async_engine` |
| 启动时自动 `alembic upgrade head` | ✅ | docker-compose backend command（`docker-compose.yml:44`） |
| 单 head 约束 | ✅ | 所有 revision 链条单线，CI 可加 `alembic heads | wc -l == 1` |
| 离线 SQL 模式（`run_migrations_offline`） | ✅ | env.py:17-23 |
| 模型注册表 | ✅ | `backend/models/__init__.py` 聚合所有 SQLAlchemy 模型给 `Base.metadata` |

### D. 首次启动引导

| 能力 | 状态 | 实现 |
|---|---|---|
| Bootstrap 默认 LLM provider/slot（DeepSeek + xAI） | ✅ | `services/model_management.py::ensure_default_model_management_state` 在 lifespan startup 调（`main.py:30-34`） |
| 创建第一个 admin 用户 CLI | ✅ | `backend/cli/create_admin.py`，`python -m cli.create_admin <email>` |
| 已有 password identity 时升级为 admin（不重复创建） | ✅ | `create_or_promote_admin` line 33-40 |
| 默认 dev_user（开发环境免登录调试） | ✅ | `ENABLE_DEV_AUTH=true` + `DEV_USER_EMAIL` / `DEV_USER_PASSWORD_HASH` |
| 静态目录自动创建 | ✅ | `backend/main.py:99` `_static_dir.mkdir(parents=True, exist_ok=True)` |

### E. 静态文件与 OSS

| 能力 | 状态 | 实现 |
|---|---|---|
| 本地图片存储后端 | ✅ | `IMAGE_STORAGE_BACKEND=local` + `IMAGE_STORAGE_DIR=static/images` |
| `/static/images` 路由挂载 | ✅ | `backend/main.py:99-101` `app.mount(...)` |
| 阿里云 OSS 后端切换 | ✅ | `IMAGE_STORAGE_BACKEND=oss` + `OSS_*` 系列字段 |
| OSS 公网 base URL 自定义 | ✅ | `OSS_PUBLIC_BASE_URL`（CDN 域名） |
| OSS key prefix 自定义 | ✅ | `OSS_KEY_PREFIX=inkwild/images` |

### F. 日志与监控集成

| 能力 | 状态 | 实现 |
|---|---|---|
| structlog 全局 logger | ✅ | `middleware/logging.py::LoggingMiddleware` |
| Sentry 后端 SDK init | ✅ | `backend/sentry_config.py::init_sentry` 在 `main.py:25` 主入口调 |
| Sentry 前端 SDK | ✅ | `frontend/sentry.{server,edge}.config.ts` + `instrumentation.ts` |
| `/health` endpoint（DB + Redis） | ✅ | `main.py:76-95`，详见 observability-backup.md |
| 详见运维细节 | — | 见 `docs/operations/observability-backup.md` |

---

## 2. 关键能力实现要点

### 2.1 docker-compose dev/prod 双套编排

**问题**：同一份 compose 既要支持本地热重载开发（bind-mount + `next dev` + `--reload`），又要支持生产部署（构建产物 + `next start` + 无 reload），还要管 URL/cookie/CORS 这些环境差异。早期把 dev 配置写在 `docker-compose.yml` 里、生产用 `docker-compose.override.yml` 改环境变量但**不覆盖 command 和 volumes**——结果是上线后跑的还是 `next dev`，HMR WebSocket 连不上 Cloudflare，turbopack chunk URL 每次重启就换、缓存命中即 404。

**解决**：把 compose 拆成"基底 + 双 override"三份文件，**显式组合**：

```
docker-compose.yml         # 基底：6 service 编排 + 生产形态（npm start / uvicorn）
docker-compose.dev.yml     # dev override：bind-mount + npm run dev + --reload + DEBUG=true
docker-compose.prod.yml    # prod override：生产 URL/cookie/CORS + build args + 127.0.0.1 端口
```

**实现要点**：

| 关键点 | 怎么做 | 为什么 |
|---|---|---|
| 基底默认就是生产形态 | `docker-compose.yml` 不写 `command:`（用 Dockerfile 的 `CMD ["npm","start"]`）和 bind-mount | 服务器上即便有人误用 `docker compose up`，跑出来也不是 dev server |
| `NEXT_PUBLIC_*` 通过 build args 传入 | `docker-compose.prod.yml` 的 `build.args` → `Dockerfile` 的 `ARG` → `RUN npm run build` 时烤进 client bundle | Next.js 在 `npm run build` 阶段把 `NEXT_PUBLIC_*` 内联进客户端 JS，运行时改 env 无效；不通过 build arg 浏览器拿到的 API 地址永远是 `http://localhost:8000` |
| dev / prod 端口绑定不同 | dev：`0.0.0.0:3000`；prod：`127.0.0.1:3000` | 生产环境前面有 nginx 终结 HTTPS，3000 直接暴露公网会绕开 nginx 的限流/header 注入/access log |
| 生产用显式 `-f` 而非 override.yml | 不再使用 Compose 默认自动 merge 的 `docker-compose.override.yml` | 自动 merge 是隐式行为，dev 跑还是 prod 跑取决于"override.yml 此刻是什么"，行为不可读；显式 `-f file` 写在部署命令里所有人一眼看明白 |
| Alembic 迁移自动跑 | `docker-compose.yml` backend command：`alembic upgrade head && uvicorn ...` | 迁移失败直接挂掉，不会写脏数据 |

**取舍**：dev compose 仍保留 `rm -rf .next` 强制清空——turbopack 在 docker volume mount 下偶发 globals.css / tailwind 改动漏检测，多花 ~10s 全量编译换稳定 HMR。生产因为不 bind-mount 不存在这个问题。

### 2.2 .env 配置全清单按域分组

`backend/.env.example`（130 行）已经按域分组并加中文注释。下面把 57 个字段按业务域整理，**M = 必填，O = 可选**：

#### 运行环境与可观测

| 字段 | 默认 | M/O | 说明 |
|---|---|---|---|
| `ENVIRONMENT` | `development` | M | Sentry tag + 日志元数据 |
| `RELEASE_TAG` | `""` | O | Sentry release，CI 可注入 git sha |
| `SENTRY_DSN` | `""` | O | 旧字段（向后兼容） |
| `BACKEND_SENTRY_DSN` | `""` | O | 后端专用 DSN，优先级高于 SENTRY_DSN |
| `DEBUG` | `false`（compose override `true`） | O | echo SQL + 日志 verbose |

#### 数据库 + Redis

| 字段 | 默认 | M/O | 说明 |
|---|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/inkwild` | M | 必须 `+asyncpg` 驱动 |
| `DB_POOL_SIZE` | `5` | O | SQLAlchemy connection pool 大小 |
| `DB_MAX_OVERFLOW` | `10` | O | pool 满时额外允许的连接数 |
| `DB_POOL_TIMEOUT` | `30` | O | 取连接超时秒数 |
| `REDIS_URL` | `redis://localhost:6379/0` | M | 用于 SessionLock + rate limit |

#### 认证

| 字段 | 默认 | M/O | 说明 |
|---|---|---|---|
| `AUTH_COOKIE_NAME` | `inkwild_session` | O | 不要随便改 |
| `WEB_SESSION_DAYS` | `90` | O | session cookie 有效期 |
| `ENABLE_DEV_AUTH` | `false` | O | 开发免登录用 |
| `DEV_USER_EMAIL` | `pokonyan1666@gmail.com` | O | 仅 ENABLE_DEV_AUTH=true 生效 |
| `DEV_USER_PASSWORD_HASH` | `(scrypt hash)` | O | 同上 |

#### LLM provider（fallback / bootstrap）

| 字段 | 默认 | M/O | 说明 |
|---|---|---|---|
| `LLM_PROVIDER` | `deepseek` | O | model_slots 优先；这里 fallback |
| `ANTHROPIC_API_KEY` | `""` | O | Claude；admin 后台绑 slot 后从 DB 读 |
| `DEEPSEEK_API_KEY` | `""` | M（fallback） | DeepSeek 调用 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | O | 自部署反代时改 |
| `LLM_DEFAULT_MODEL` | `deepseek-chat` | O | fallback 模型 |
| `LLM_COMPRESSION_MODEL` | `deepseek-chat` | O | 上下文压缩 fallback |
| `GROK_API_KEY` | `""` | O | xAI grok |
| `GROK_BASE_URL` | `https://api.x.ai/v1` | O | xAI 端点 |
| `GROK_MODEL` | `grok-4.20-0309-reasoning` | O | grok 文本模型 |
| `GROK_IMAGE_MODEL` | `grok-imagine-image` | O | grok 图像模型 |
| `GEMINI_OPENAI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai` | O | Gemini OpenAI 兼容端点 |
| `MODEL_PROBE_TTL_HOURS` | `168` | O | 模型探测结果缓存 |
| `MODEL_MANAGEMENT_BOOTSTRAP_ENABLED` | `true` | O | 启动时自动建默认 provider/slot |

#### 上下文与压缩

| 字段 | 默认 | M/O | 说明 |
|---|---|---|---|
| `MAX_CONTEXT_ROUNDS` | `15` | O | 喂给 LLM 的最近回合数上限 |
| `COMPRESSION_THRESHOLD` | `20` | O | 触发上下文压缩的阈值（轮数） |
| `SESSION_LOCK_TIMEOUT` | `60` | O | SessionLock TTL（秒） |

#### NPC 子系统

| 字段 | 默认 | M/O | 说明 |
|---|---|---|---|
| `NPC_REFLECTION_ENABLED` | `true` | O | 长期反思总开关 |
| `NPC_REFLECTION_THRESHOLD` | `5` | O | 触发反思所需新 memory 条数 |
| `NPC_MAX_CONCURRENCY` | `6` | O | 单回合 NPC LLM 并发上限 |
| `NPC_DIALOGUE_SEQUENTIAL_ENABLED` | `true` | O | 顺序对话开关 |
| `NPC_MAX_SPEAKERS_PER_TURN` | `3` | O | 单回合发声 NPC 上限 |
| `NPC_PEER_RELATIONS_ENABLED` | `true` | O | NPC↔NPC 持久关系 |

#### 语义记忆 embedding（可选）

| 字段 | 默认 | M/O | 说明 |
|---|---|---|---|
| `EMBEDDING_ENABLED` | `false` | O | 启用语义召回 |
| `EMBEDDING_BASE_URL` | `""` | O（启用时 M） | OpenAI 兼容 embeddings 端点 |
| `EMBEDDING_API_KEY` | `""` | O（启用时 M） | embedding API key |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | O | embedding 模型名 |
| `EMBEDDING_DIM` | `1536` | O | 向量维度 |
| `EMBEDDING_TIMEOUT_SECONDS` | `5.0` | O | 单次调用硬超时 |

#### 内容审核 + 限流 + 成本（详见 `docs/modules/cost-rate-moderation.md`）

| 字段 | 默认 | M/O | 说明 |
|---|---|---|---|
| `CONTENT_FILTER_ENABLED` | `true` | O | 历史开关 |
| `GAME_ACTION_RATE_LIMIT_PER_MINUTE` | `30` | O | 每用户每分钟动作上限 |
| `GAME_ACTION_RATE_LIMIT_WINDOW_SECONDS` | `60` | O | 限流窗口长度 |
| `GAME_SESSION_SOFT_WARN_COST_CENTS` | `500` | O | ¥5 软警告 |
| `GAME_SESSION_HARD_CAP_COST_CENTS` | `600` | O | ¥6 硬上限 |
| `GAME_INPUT_COST_CENTS_PER_MILLION_TOKENS` | `0` | **生产 M** | 默认 0 → 成本永远算 0，必须配置 |
| `GAME_OUTPUT_COST_CENTS_PER_MILLION_TOKENS` | `0` | **生产 M** | 同上 |

#### LLM router 韧性

| 字段 | 默认 | M/O | 说明 |
|---|---|---|---|
| `LLM_CALL_TIMEOUT_SECONDS` | `60.0` | O | 第一个 token 超时（不限流式总长） |
| `LLM_CALL_MAX_RETRIES` | `1` | O | 同 provider 重试次数 |
| `LLM_CALL_RETRY_BACKOFF_SECONDS` | `0.5` | O | 重试间隔 |

#### 多 Key 轮询与并发

| 字段 | 默认 | M/O | 说明 |
|---|---|---|---|
| `LLM_GLOBAL_CONCURRENCY` | `8` | O | 所有在途 LLM stream 的全局并发上限 |
| `KEY_COOLDOWN_SECONDS` | `45.0` | O | 某个 key 被 429 限流后冷却多久再被轮询选中 |

- 每个 provider 可配多个 API key：admin「模型管理 → Provider 编辑 → API Keys（直填，一行一个）」
  直接存进 DB（优先于环境变量名），或让环境变量值逗号分隔。原始 key 在所有响应里打码（`sk-…abcd`）。
- 运行时按**会话粘连**轮询（`llm/key_pool.py`）：同一局/同一生成任务恒定同一个 key，
  保住整局 prompt 缓存；不同会话散到不同 key 分摊并发。被 429 命中的 key 自动冷却
  `KEY_COOLDOWN_SECONDS` 后再用；全部冷却时取最早恢复的那个，不硬失败。
- **多 key 想真正提总并发，需相应调高 `LLM_GLOBAL_CONCURRENCY`**，否则总并发被这道闸卡住、
  散到每个 key 都远低于其单 key 限额。经验值：`LLM_GLOBAL_CONCURRENCY ≈ key 数 × 单 key 可用并发预算`。
- 冷却状态是进程内存，多 worker 各自一份（软优化）；跨进程一致后续可接 Redis。

#### Director / Narrator 行为

| 字段 | 默认 | M/O | 说明 |
|---|---|---|---|
| `DIRECTOR_PREFER_JSON_MODE` | `false` | O | 部分 provider 不支持 tool_use 时切到 json mode |
| `NARRATOR_EARLY_STREAM_ENABLED` | `true` | O | 早流式（详见 orchestrator.md §2.2） |

#### 联网检索 + 创作工坊

| 字段 | 默认 | M/O | 说明 |
|---|---|---|---|
| `TAVILY_API_KEY` | `""` | O | 创世联网检索 |

#### 图像存储

| 字段 | 默认 | M/O | 说明 |
|---|---|---|---|
| `IMAGE_STORAGE_BACKEND` | `local` | M | `local` 或 `oss` |
| `IMAGE_STORAGE_DIR` | `static/images` | O（local 时 M） | 本地存储目录 |
| `OSS_ACCESS_KEY_ID` | `""` | O（oss 时 M） | 阿里云 OSS |
| `OSS_ACCESS_KEY_SECRET` | `""` | O（oss 时 M） | 同上 |
| `OSS_ENDPOINT` | `""` | O（oss 时 M） | OSS endpoint |
| `OSS_BUCKET_NAME` | `""` | O（oss 时 M） | bucket |
| `OSS_PUBLIC_BASE_URL` | `""` | O | CDN 域名（不填用 endpoint） |
| `OSS_KEY_PREFIX` | `""` | O | 默认 inkwild/images |

#### 前端（`frontend/.env.example`）

| 字段 | 默认 | M/O | 说明 |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | M | 浏览器侧 API 地址 |
| `INTERNAL_API_URL` | `""` | O | Server Action 用，缺省回落到 NEXT_PUBLIC_API_URL |
| `NEXT_PUBLIC_SENTRY_DSN` | `""` | O | 前端 Sentry DSN |
| `SENTRY_AUTH_TOKEN` | `""` | O | sourcemap 上传，仅 build 阶段用 |
| `SENTRY_ORG` | `""` | O | Sentry org slug |
| `SENTRY_PROJECT` | `""` | O | Sentry project slug |

### 2.3 Alembic 迁移流程

**问题**：schema 变更要可重放、可回滚；async 引擎跟 sync alembic API 不兼容需要桥接；多人开发要避免 head 分叉。

**解决**：alembic 标准流程 + async 桥接。`migrations/env.py::run_migrations_online` 通过 `create_async_engine` 取连接，再用 `connection.run_sync(do_run_migrations)` 把 sync alembic 套在 async 连接上。

**实现**：
- 升级到最新：`cd backend && alembic upgrade head`
- 自动跑：`docker-compose.yml:44` backend 启动命令前缀
- 生成新迁移：`cd backend && alembic revision --autogenerate -m "<message>"`
- 验证单 head：`cd backend && alembic heads`（应该只有一行）；CI 可加 `alembic heads | wc -l` 断言 1
- 离线 SQL 模式：`alembic upgrade head --sql > schema.sql`（用于 review 不直接执行）

**取舍**：用 alembic 而不是 SQLAlchemy 的 `metadata.create_all()`——后者无法表达 ALTER COLUMN / 数据迁移 / 索引调整。代价是每次 schema 改动多一个 migration 文件，但带来的可回滚价值远大于成本。

### 2.4 首位 admin 用户引导

**问题**：第一次部署没有任何用户，admin 后台进不去——"鸡生蛋"问题。

**解决**：CLI 工具 `backend/cli/create_admin.py`，`python -m cli.create_admin <email>` 创建或把已有 password identity 升级成 admin。

**实现**：
- 首次：`cd backend && python -m cli.create_admin admin@example.com`，会 prompt 输入密码（或 `--password 'xxx'` 一次性传）
- 已有用户升级：同样命令；脚本会 detect 已存在的 password identity，直接 `user.is_admin = True`（line 33-40）
- 不重置密码：升级路径不会改密码，避免覆盖
- 用 `services/auth_service::hash_password` 加 scrypt 哈希

### 2.5 静态文件与 OSS 切换

**问题**：开发要快速看 AI 配图效果，本地存最方便；生产要走 CDN，不该让用户访问后端 IP 取图片。

**解决**：`IMAGE_STORAGE_BACKEND` env 切换 `local` / `oss`。`local` 时 backend 直接通过 `app.mount("/static/images", StaticFiles(...))` 提供文件；`oss` 时图片上传到阿里云 OSS，URL 用 `OSS_PUBLIC_BASE_URL` 拼接。

**实现**：
- 抽象层：`backend/services/image_storage.py`（local + oss 两个实现共用接口）
- 本地路径：`static/images` 自动创建（`main.py:100`）
- OSS 配置全集：`OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` / `OSS_ENDPOINT` / `OSS_BUCKET_NAME` / `OSS_PUBLIC_BASE_URL` / `OSS_KEY_PREFIX`
- 切换无需改代码，重启服务读新 env 即可

**取舍**：没接入 S3 / Cloudflare R2 / 七牛——首位部署目标在国内，OSS 优先；其他云接入参照 `image_storage.py` 加新后端 + 新 env 字段即可（一两小时工作量）。

---

## 3. 本地开发 — 从零跑起来

推荐路径：基础设施跑 docker，前后端跑 host。这是 CLAUDE.md 钉死的本地工作流，热重载最丝滑。

```bash
# 1. clone
git clone <repo> inkwild
cd inkwild

# 2. 准备 .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env  # 可选
# 编辑 backend/.env：至少填 DEEPSEEK_API_KEY

# 3. 起基础设施（db + redis）
docker compose up -d db redis

# 4. 后端依赖 + 迁移 + 启动
cd backend
pip install -e ".[dev]"
alembic upgrade head
python -m cli.create_admin admin@example.com  # 设第一个 admin
python -m seeds.seed                          # 灌入默认世界数据（wuyinzhen）
uvicorn main:app --reload --port 8000
cd ..

# 5. 前端
cd frontend
npm install
npm run dev          # http://localhost:3000
cd ..

# 6. （可选）admin 后台
cd admin-frontend && npm install && npm run dev   # http://localhost:3001
```

如果你想"整套都跑 docker"（少见，比如要在 Linux 上调 docker 网络问题）：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

注意点：
- 第一次启动会触发 `ensure_default_model_management_state` bootstrap 默认 LLM provider/slot（`main.py:30-34`），需要 `DEEPSEEK_API_KEY` 至少有
- `python -m cli.create_admin` 必须在 `backend/` 目录下跑（`PYTHONPATH` 已被 CLI 内部 fix，但 cwd 一致更稳）

---

## 4. 生产部署

### 4.1 环境前提

- 服务器：Linux + docker compose v2.20+（要支持 `-f file1 -f file2` 多文件合成）
- nginx：HTTPS 入口，反代到 `127.0.0.1:3000` / `:3001` / `:8000`（见 §4.5）
- DNS：`inkwild.app` 主站 / `admin.inkwild.app` 后台（按需）
- Cloudflare（可选但推荐）：CDN + 抗刷 + WS 直通

### 4.2 dev 跟 prod 的差异

| 维度 | 本地 dev | 生产 prod |
|---|---|---|
| Compose 调用 | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d` 或 host 直跑 | `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` |
| 前端模式 | `next dev`（turbopack，HMR） | `next start`（构建产物） |
| 后端 reload | `uvicorn --reload` | `uvicorn`（无 reload） |
| 端口绑定 | `0.0.0.0:*`（host 直访） | `127.0.0.1:*`（nginx 反代） |
| `NEXT_PUBLIC_API_URL` | 运行时 env，`http://localhost:8000` | **build arg**，`https://inkwild.app`（烤进客户端 bundle） |
| `SESSION_COOKIE_DOMAIN` | 空 | `.pokonyan.com`（跨子域共享 session） |
| `CORS_EXTRA_ORIGINS` | 空 | `https://inkwild.app,https://admin.inkwild.app` |
| `DEBUG` | `true` | `false` |
| `ENABLE_DEV_AUTH` | 可 `true` | **必须 `false`** |
| Sentry DSN | 通常空 | `BACKEND_SENTRY_DSN` + `NEXT_PUBLIC_SENTRY_DSN` 都填 |
| `IMAGE_STORAGE_BACKEND` | `local` | 通常 `oss` |
| LLM 单价（`GAME_*_COST_CENTS_PER_MILLION_TOKENS`） | 可 0 | **必须填真实值** |
| moderation_slot 绑定 | 可空（走本地 5 条关键词兜底） | **必须绑廉价 tool-use 模型** |
| 源码 bind-mount | 有（热更新） | **无**（用镜像内构建产物） |

### 4.3 首次部署

```bash
# 在服务器上
cd /inkwild

# 1. 同步代码（用 git pull / rsync / scp，按你的部署工具）
#    确保 docker-compose.yml / docker-compose.prod.yml / 两个 Dockerfile 都是最新

# 2. 准备 backend/.env（生产值，参考 §2.2 必填项清单）
vim backend/.env

# 3. 构建 + 起栈（注意必须带 --build，下面会解释为啥）
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 4. 等迁移跑完（看 backend 日志）
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend
# 看到 uvicorn 监听 8000 后 Ctrl+C 退出 follow

# 5. 创建第一个 admin
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  python -m cli.create_admin admin@yourdomain.com

# 6. 灌默认世界种子（首次）
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  python -m seeds.seed

# 7. 验证
curl -k https://inkwild.app/api/health
curl -k https://inkwild.app/ | head -c 200   # 应该看到 <!DOCTYPE html>...
```

### 4.4 更新/重新部署

```bash
# 后端代码改动（不涉及前端 NEXT_PUBLIC_*）
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build backend

# 前端代码改动
docker compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache frontend admin-frontend
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d frontend admin-frontend

# 全栈
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

**关键：前端发版必须带 `--build`**——`NEXT_PUBLIC_API_URL` 是 build arg，烤进 client bundle 后运行时改 env 没用。如果直接 `up -d` 复用旧镜像，浏览器拿到的还是旧 API 地址。

### 4.5 nginx 入口（参考配置）

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 443 ssl;
    server_name inkwild.app;
    client_max_body_size 25m;

    # /api/* 和 /static/* 进后端
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_buffering off;            # SSE 必须
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
    location /static/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # 其余进前端
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }

    ssl_certificate /etc/letsencrypt/live/inkwild.app/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/inkwild.app/privkey.pem;
}

# admin.inkwild.app 同理，location / 反代到 127.0.0.1:3001
```

**关键点**：
- `/api/` 段的 `proxy_buffering off` 必须有，否则 SSE 流式响应会被 buffer 累积成大块
- `Upgrade` / `Connection` header 必须传，给后端 SSE 和（如果用到）WebSocket 让路
- `client_max_body_size 25m` 留给封面图上传

### 4.6 Cloudflare（可选）

如果用 CF 做 CDN，加一条 cache rule：

| 字段 | 值 |
|---|---|
| Match | URI Path starts with `/_next/static/` |
| Cache eligibility | Eligible for cache |
| Edge TTL | Override origin → 1 year |
| Browser TTL | Override origin → 1 year |

`/_next/static/*` 在生产模式下文件名带 content hash，发版自动换名，缓存一年绝对安全。

**发版后必做**：在 CF dashboard 对该域名做一次 "Purge Everything"，清掉浏览器/边缘节点上残留的旧 HTML（旧 HTML 里写死了上一版的 chunk URL）。

WebSocket 不需要单独配，CF 默认放行。

### 4.7 故障速查

| 现象 | 可能原因 | 怎么定位 |
|---|---|---|
| 浏览器控制台 `wss://.../_next/webpack-hmr failed` | 跑的是 `next dev` 不是 `next start` | `docker inspect <frontend> --format '{{.Config.Cmd}}'`，应该看到 `npm start`；如果是 `rm -rf .next && npm run dev` 就是没用 `-f docker-compose.prod.yml` |
| 页面打开空白 / API 调用打到 `http://localhost:8000` | 前端 build 时没传 `NEXT_PUBLIC_API_URL` | `docker compose ... build --no-cache frontend` 重建 |
| 登录后立刻又跳登录页 | `SESSION_COOKIE_DOMAIN` 没设 | `docker exec <backend> env | grep SESSION_COOKIE` 检查 |
| `/api/*` 跨域 403 | `CORS_EXTRA_ORIGINS` 没包含主站域名 | 同上检查 env |
| SSE 卡住 / 几秒后断 | nginx `proxy_buffering on`（默认）或 `proxy_read_timeout` 太短 | 检查 nginx config，需要 `proxy_buffering off` + 300s timeout |
| 旧 chunk 404 一片 | CF 缓存了上一版的 HTML | CF Purge Everything |
| Alembic 迁移卡住 | 同时多个 backend 容器抢锁 | `docker compose ... ps`，缩到 1 个 backend 实例再重试 |

---

## 5. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `docker-compose.yml` | 生产基底：6 service 编排 + 03:00 backup cron |
| `docker-compose.dev.yml` | dev override：bind-mount + npm run dev + --reload + DEBUG |
| `docker-compose.prod.yml` | prod override：生产 URL/cookie/CORS + build args + 127.0.0.1 端口 |
| `frontend/Dockerfile` | `ARG NEXT_PUBLIC_API_URL` + `npm run build` + `npm start` |
| `admin-frontend/Dockerfile` | 同 frontend，多两个 build arg |
| `backend/.env.example` | env 全字段中文注释 |
| `frontend/.env.example` | 前端 env |
| `backend/config.py` | Pydantic Settings 全字段定义 |
| `backend/database.py` | async engine + pool 配置（详见 observability-backup.md §3） |
| `backend/migrations/env.py` | Alembic async 桥接 |
| `backend/migrations/versions/` | 所有迁移文件 |
| `backend/cli/create_admin.py` | 首位 admin 创建 / 升级 |
| `backend/main.py` | FastAPI 入口 + lifespan bootstrap + 静态目录 mount |
| `backend/services/model_management.py` | 默认 provider/slot bootstrap |
| `backend/services/image_storage.py` | local / oss 双后端 |
| `ops/backup.sh` | DB 备份脚本（详见 observability-backup.md §5） |

---

## 6. 已知短板与未来扩展

### P1（上线前必须确认）

- **LLM 单价默认 0**：`GAME_INPUT/OUTPUT_COST_CENTS_PER_MILLION_TOKENS` 默认 0，cost guardrail 永远 OK；上线前必须填（详见 `docs/modules/cost-rate-moderation.md §6` P1）
- **`moderation_slot` 没绑则走本地 5 条关键词规则**：本地规则极其粗，必须在模型后台绑廉价 tool-use 模型
- **uvicorn 单 worker**：生产 compose 当前跑单进程 uvicorn，扛量不行；要扩需要换 gunicorn + UvicornWorker 多 worker（注意 lifespan startup 的 bootstrap 会被多进程跑多次，需要加分布式锁或外部 init job）

### P2

- **secrets 管理**：当前 API key 都从 `.env` 读，生产应该走 vault / aws secrets manager / k8s secret，不该明文进容器
- **多环境 .env 模板**：当前只有 `.env.example`，可以加 `.env.production.example` / `.env.staging.example` 区分必填项
- **Alembic CI 校验**：自动跑 `alembic heads` 断言单 head + `alembic upgrade head --sql` 检查可执行
- **OSS 之外的对象存储后端**（S3 / R2 / 七牛）：参考 `image_storage.py` 抽象层加，不大但没需求暂不做

### P3

- **k8s helm chart**：当前只支持 docker-compose；上规模需要重写部署形态
- **配置热重载**：当前改 env 必须重启 service；用 admin 后台改 LLM 配置已经支持热更新（动态 slot 绑定），其他 env 字段（限流阈值、cost cap）需要类似机制
- **多区域部署**：DB / Redis 单点，多区域需要异地多活方案
- **Backend Dockerfile 优化**：当前 build context 整个 backend，可加 .dockerignore + 多阶段 build 减小镜像

---

## 7. 参考

- 配套：`docs/operations/observability-backup.md`（Sentry / 健康检查 / 日志脱敏 / 备份恢复）
- 配套：`docs/modules/cost-rate-moderation.md`（限流 / 成本 / 审核三件横切）
- 上层：`CLAUDE.md` 项目根，含技术栈与项目结构
