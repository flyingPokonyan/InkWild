# Provider 多 Key 轮询池（sticky + 冷却）

> 设计日期 2026-05-30。目标：单个 model key 容易达到并发上限，给每个 provider 配多个 key，
> 按会话粘连轮询分散负载，被限流的 key 自动冷却跳过。同时把 key 存储从"读环境变量名"
> 改为"直接存 AK"，加 key 只在 admin 改、不碰配置文件。

## 背景 / 现状

- `model_providers.api_key_env_name` 存的是**环境变量名**（如 `DEEPSEEK_API_KEY`），
  原始 key 不进 DB。`_configured_secret_value(env_name)` 运行时解析：
  `os.getenv` → `.env` 文件（按 mtime 缓存）→ `settings` 兜底映射（4 个已知名字）。
- provider / router **每次请求重建**：`resolve_slot_router` 在每个游戏回合开头
  （`api/game.py:103`）、每次工坊生成、每次审核调用时跑，不缓存。
- 底层 client 在构造时把 key 写死：`AsyncOpenAI(api_key=...)`，一个 provider 实例一个 key。
- `LLMRouter` 已有：跨 provider fallback、单 provider 内 transient retry（429 已归类
  transient）、全局并发信号量 `llm_global_concurrency`（默认 8，封顶所有在途 stream）。
- 已有 ambient contextvar `current_usage_context()`（计费归因），入口处压栈，
  带 `session_id` / `task_id` —— 直接当本方案的 affinity 源，无需新 contextvar。
- provider 类层级：`GeminiProvider` 继承 `OpenAICompatibleProvider`；`GrokProvider`、
  `DeepSeekProvider` 独立。`DeepSeekProvider` 只在 legacy fallback（无 slot 绑定）用，
  live 游戏路径 DeepSeek 走 `provider_type="openai_compatible"` → `OpenAICompatibleProvider`。

## 决策（已与用户确认）

1. **多 key 存哪**：直接在 DB 存原始 AK，逗号/数组形式，admin UI 管理，不再依赖 env 文件。
   （打破"DB 不存密钥"的旧约定，用户已拍板，换取运维便利；序列化全程打码。）
2. **轮询粒度**：按会话粘连 `hash(session)→key`。同一局恒定同 key（保住整局 prompt 缓存），
   跨会话散开。其余无 affinity 的场景 round-robin 兜底。
3. **限流处理**：被 429/限流命中的 key 进内存冷却，临时跳过。

## 架构

改动集中在 `services/model_management.py` + 新 `llm/key_pool.py` + 一个 Alembic 迁移
+ admin schema / UI。**`LLMRouter` 和三个 provider 类基本不动。**

### 1. 存储模型（DB）

- `model_providers` 新增列 **`api_keys: JSON`**（`list[str]`，默认 `[]`），存原始 key 明文。
- `api_key_env_name` 改为 **nullable**，保留做 back-compat / bootstrap。
- 新 helper `_provider_api_keys_list(provider) -> list[str]`，解析优先级：
  1. `provider.api_keys` 非空 → 直接用这组明文 key（**主路径**）。
  2. 否则 `api_key_env_name` 有值 → `_configured_secret_value()` 解析，**支持逗号分隔**
     （env 值 `k1,k2` 拆成 list，等于给 env 派的 provider 也白送多 key）。
  3. 都空 → `ModelManagementError`（沿用现有 `_provider_api_key` 的报错语义）。
- 迁移：Alembic 只加一列、把 `api_key_env_name` 改 nullable。既有 bootstrap 行不动
  （走 env 分支），**零数据迁移**。

### 2. 安全 / 序列化（masking）

- `serialize_provider` **永不**返回原始 key。
  - 移除/不新增任何回原始 key 的字段。
  - 新增 `api_key_count: int`；`api_key_previews: list[str]`（每项形如 `sk-…a1b2`，只露后 4 位，
    长度 <8 的整串打码）；保留 `api_key_available: bool`（= count>0 或 env 可解析）。
- Admin create/update 入参 `api_keys: list[str] | None`：
  - `None` → 不变（编辑时不传 = 保留原有）；
  - `[]` → 清空；
  - `[...]` → 整组替换。
  - 编辑表单**不回填明文**（拿不到，也不该拿）。提交空白 = 不动。
- `extra_config` 等回前端的字段不得夹带 key。

### 3. Key 选择 —— 新模块 `llm/key_pool.py`

- 指纹 `fp = sha256(key.encode())[:16]`；cooldown / 日志 / 内部 map **只认指纹**，
  原始 key 不在 key_pool 之外扩散。
- `select_key(provider_id: str, keys: list[str], affinity: str | None) -> tuple[str, str]`
  返回 `(key, fp)`：
  1. 过滤掉当前 cooldown 中的 fp；
  2. 若全部在冷却 → 取 `cooldown_until` **最早**那个（绝不硬失败，宁可用快恢复的）；
  3. 在 available 里：`affinity` 非空 → `available[hash(affinity) % len(available)]`
     （用稳定 hash，如 `hashlib` 而非内置 `hash()`，避免进程间 salt 抖动）；
     `affinity` 为空 → per-provider 原子 round-robin 计数器（`itertools.count` / 锁保护的 int）。
- **affinity 源** = `current_usage_context()` 的 `session_id or task_id`。
  - 校验点：`_build_*` 跑时 UsageContext 必须已压栈。若发现 `resolve_slot_router`
    早于 usage_context 入口，则把 affinity 显式传进 `resolve_slot_router` 或前移压栈点。
    缺失时回落 round-robin，功能不破，只少了 stickiness。
- `_build_llm_provider` / `_build_image_provider` / `_build_web_searcher` 改为：
  `keys = _provider_api_keys_list(provider)` → `key, fp = select_key(provider.id, keys, affinity)`
  → 用 `key` 建底层 provider。

### 4. 429 冷却 —— 薄 wrapper

- 新 `KeyCooldownProvider(inner: LLMProvider, provider_id: str, fp: str)`：
  - `stream_with_tools` / `stream_json` 透传 `inner`，外层 `try/except`；
  - 捕获限流类异常（`RateLimitError` 或 `status_code == 429`，复用 router 里
    `_is_transient` 的判定思路）→ `key_pool.report_rate_limited(provider_id, fp)`
    设 `cooldown_until = now + COOLDOWN_S` → **照样 re-raise**，交给 router 现有 retry / fallback。
  - 注意：异常可能在首个 event 之前或迭代中抛出，两处都要覆盖。
- `_build_llm_provider` 返回 `KeyCooldownProvider(真 provider, …)`。
  **只改 `_build_*`，不动三个 provider 类、不动 router。**
- 图像 / web search：同样可 wrap（best-effort）。图像走 `generate_image`（非流式），
  用对应的 cooldown 包装；web search 同理。本期至少覆盖文本流式 + 图像。
- `COOLDOWN_S` 走 settings（默认 45s）。
- cooldown 状态 = 进程内存 dict。多 worker 各自一份（软优化，可接受）。
  跨进程一致性后续可换 Redis（项目已有 Redis），留 TODO，不在本期。

### 5. 与全局并发闸的关系（提示，本期不改逻辑）

- `llm_global_concurrency`（默认 8）封顶所有在途 stream。多 key 想真正提**总**并发，
  需把它调高，否则 8 路再散到 N 个 key、每个都 < 8/N，根本碰不到单 key 限流。
- 本期：在 `docs/operations/deploy-and-config.md` / 本文件点明这个旋钮，
  建议按 `key 数 × 单 key 预算` 设，不写死、不引入 per-key 信号量。

### 6. Admin UI（admin-frontend）

- Provider 编辑表单：单 key 输入 → 多行 / 标签输入（一行一个 key）。
- provider 列表 / 详情：展示 `api_key_count` + masked previews。每 key cooldown 状态可选（nice-to-have）。
- healthcheck 逐 key 探活：本期可只探"第一个可用 key"，逐 key 留后续。

## 已知取舍（写在前面，避免日后惊讶）

- **sticky 的代价**：同一回合内并行的多个 NPC 调用仍共用该局的 key。这通常是小爆发、
  且受全局闸限制；主要痛点是"多会话打满单 key"，sticky 正好治这个。若日后发现回合内
  并发才是瓶颈，再加回合内 sub-key 分散（本期不做）。
- **冷却是进程内**：多 worker 不共享，属软优化。

## 影响面清单

| 文件 | 改动 |
|---|---|
| `backend/models/model_management.py` | `ModelProvider` 加 `api_keys` 列；`api_key_env_name` 改 nullable |
| `backend/migrations/versions/*` | 新 Alembic 迁移（加列 + nullable） |
| `backend/llm/key_pool.py` | **新**：指纹、`select_key`、`report_rate_limited`、cooldown map、`KeyCooldownProvider` |
| `backend/services/model_management.py` | `_provider_api_keys_list`；`_build_llm/image/web_searcher` 接 key_pool；`serialize_provider` masking；create/update 收 `api_keys` |
| `backend/schemas/*` | provider create/update schema 加 `api_keys: list[str] | None`；响应加 `api_key_count` / `api_key_previews` |
| `backend/api/admin_models.py`（或对应路由） | 透传 `api_keys` |
| `backend/config.py` | `key_cooldown_seconds`（默认 45） |
| `admin-frontend/*` | provider 表单多 key 输入 + 列表 masked 展示 |
| `backend/tests/*` | 见下 |

## 测试（轻量）

- `test_key_pool.py`：
  - 同 affinity 命中同 key；不同 affinity 大致散开；
  - cooldown 过滤、全冷却取最早到期；
  - affinity 空走 round-robin。
- `_provider_api_keys_list`：直存优先 / env 逗号回退 / 空报错。
- 序列化 masking 不泄漏原始 key。
- `KeyCooldownProvider`：429 触发 `report_rate_limited` 且异常照常上抛；非限流异常不触发冷却。

## 不在本期范围

- cooldown 跨进程（Redis）。
- per-key 信号量 / per-key 实时并发计数。
- 逐 key healthcheck 全量。
- 回合内 sub-key 分散。
