# 认证与 Admin 权限模块技术说明

> 状态截至 2026-05-08。覆盖 cookie session 认证 + 多登录方式映射（auth_identities）+ is_admin 列 + admin_audit_logs + create_admin CLI + 前端 adminFetch 403 重定向 + 已废弃 X-Admin-Key / X-Player-Id 全部下线后的形态。
>
> **2026-06-02 扩展（见 §1B）**：自助邮箱注册 + 邮箱验证（先验证才能用）+ 忘记/重置密码 + Google/LinuxDo OAuth + 按已验证邮箱自动合并账号。

认证与 Admin 模块负责"谁是这个请求的发起人 + 它能做什么"。统一走 HttpOnly cookie session（90 天 sliding TTL）；普通用户用 `get_current_user` 依赖，admin 写操作叠 `get_current_admin_user` + `record_admin_action` 落审计；本系统**不再**支持任何 header 形式的认证（`X-Player-Id` / `X-Admin-Key` 已彻底删除）。

它**不直接**做的事：
- ~~不做 OAuth 三方登录~~ → **2026-06-02 已落地 Google / LinuxDo OAuth + 自助注册（见 §1B）**；微信仍未做（需企业资质）
- 不做 admin UI（前端 `frontend/app/admin` 各页面）
- 不做 game session 所有权校验（在 `services/game_service.py::_get_owned_session`）

紧密耦合的上下游：
- 上：`api/auth.py`（登录/登出/me）+ `dependencies.py`（FastAPI 依赖注入）
- 下：所有 `api/*.py`（依赖 `get_current_user` / `get_current_admin_user`）+ `frontend/stores/auth.ts`（消费 isAdmin）

## 1. 能力矩阵

### A. 用户身份

| 能力 | 状态 | 实现 |
|---|---|---|
| User 表（id / status / is_admin / nickname / avatar_url） | ✅ | `models/user.py::User` |
| AuthIdentity 表（多登录方式映射，UNIQUE provider + provider_user_id） | ✅ | `models/user.py::AuthIdentity` |
| WebSession 表（HttpOnly cookie 对应行，含 expires_at / user_agent / ip_address） | ✅ | `models/user.py::WebSession` |
| 注册时 password identity 用 scrypt 哈希（N=2^14, r=8, p=1, 64 字节 key） | ✅ | `services/auth_service.py::hash_password` |
| `verify_password` 用 `hmac.compare_digest` 防 timing attack | ✅ | `services/auth_service.py:40-59` |
| AuthIdentity.provider 字段为 schema 扩展点（当前只用 `password`） | ✅ | `provider="password"` 写死在 service |
| `auth_identities.union_id` / `profile JSON` 为 OAuth 多账号合并预留 | 🟡 | schema 在；当前没有 provider 用 |
| User.status 阻断登录（非 active 一律 403） | ✅ | `auth_service.py:84` + `:113` |

### B. Cookie session 认证

| 能力 | 状态 | 实现 |
|---|---|---|
| HttpOnly + SameSite=Lax + secure（非 debug 环境） cookie | ✅ | `api/auth.py::_set_session_cookie` |
| Cookie 名 `inkwild_session`（`AUTH_COOKIE_NAME` env 可改） | ✅ | `config.py:25` |
| 90 天 max_age（`WEB_SESSION_DAYS=90`） | ✅ | `config.py:26` |
| Session 过期 sliding window（每次访问续期到 now+90d） | ✅ | `auth_service.py::get_user_by_session_id` line 110-111 |
| 过期 session 自动删除并返回 None | ✅ | `auth_service.py:104-107` |
| 登出删 WebSession + 清 cookie | ✅ | `api/auth.py::logout` + `auth_service.py::logout` |
| `get_current_user_optional` 给可登可不登的接口 | ✅ | `dependencies.py:17-25` |
| `get_current_user` 强制登录（401 AppError 40100） | ✅ | `dependencies.py:28-33` |
| Dev 后门 `/api/dev/login`（仅 `ENABLE_DEV_AUTH=true`） | ✅ | `api/auth.py::dev_login` |
| `/api/auth/me` 返回 CurrentUserDTO（含 is_admin + identities 列表） | ✅ | `api/auth.py:83-91` + `_serialize_current_user` |

### C. Admin 权限边界

| 能力 | 状态 | 实现 |
|---|---|---|
| User.is_admin 列（Boolean，default False，nullable False） | ✅ | `models/user.py:16` |
| `get_current_admin_user` 依赖（403 AppError 40300） | ✅ | `dependencies.py:36-41` |
| 全部 admin 路由通过 `dependencies=[Depends(get_current_admin_user)]` 或 per-route Depends | ✅ | `api/admin.py` / `api/admin_models.py` |
| 写操作必走 `record_admin_action`（admin 路由内显式调用，非中间件） | ✅ | `api/admin.py` 全部写路由 + `api/admin_models.py:111-358` |
| `admin_audit_logs` 表（admin_user_id / action / resource_type / resource_id / payload / ip / ua / created_at） | ✅ | `models/audit_log.py` |
| Admin 删除自己时 audit log admin_user_id 设 NULL（FK ON DELETE SET NULL） | ✅ | `models/audit_log.py:21` |
| 读操作不写 audit log（只 dashboard / list 等不留痕） | 🟡 | by design；写操作完整覆盖 |
| Admin 创建审计 log 后必显式 `await db.commit()` | ✅ | 路由内手动 commit（避免 record_admin_action 内部 commit 与业务 commit 冲突） |

### D. Admin 引导与运维

| 能力 | 状态 | 实现 |
|---|---|---|
| `python -m cli.create_admin <email>` CLI 创建/提升 admin | ✅ | `backend/cli/create_admin.py` |
| 已存在 password identity 直接 `is_admin=True`（提升） | ✅ | `cli/create_admin.py:33-40` |
| 不存在则创建 User + password identity（密码 prompt 或 `--password` 参数） | ✅ | `cli/create_admin.py:42-61` |
| 输出 `admin user ready: <id> <email>` 给 CI / 部署脚本捕获 | ✅ | `cli/create_admin.py:74` |
| Admin 普通登录复用 `/api/auth/password/login`（不区分 admin / 普通用户） | ✅ | 同一登录流程，is_admin 字段决定能不能进 admin 路由 |
| 没有 admin "降级" CLI（手动改 DB） | 🟡 | 需求低；用 `UPDATE users SET is_admin=false WHERE ...` 即可 |

### E. 前端 auth 集成

| 能力 | 状态 | 实现 |
|---|---|---|
| `useAuthStore.loadMe()`（启动时拉 `/api/auth/me`） | ✅ | `frontend/stores/auth.ts:31-63` |
| `loadMe` 单航班合并（loadMePromise 防并发重复 fetch） | ✅ | `auth.ts:32-34 + 19` |
| `CurrentUser.isAdmin` 字段（`normalizeCurrentUser` 把 snake_case `is_admin` 映 camelCase） | ✅ | `frontend/lib/types.ts:18-35` |
| `apiFetch` 默认 `credentials: "include"` 自动带 cookie | ✅ | `frontend/lib/api.ts` |
| `adminFetch` 同款 `credentials: "include"`，403 时 `redirectToAdminLogin()` | ✅ | `frontend/lib/admin-api.ts:77-111` |
| `AdminPermissionError`（403 自定义异常类） | ✅ | `admin-api.ts:7-15` |
| 重定向带 `from` 参数保留原路径 | ✅ | `admin-api.ts:30-38` |
| `streamAdminEvents` SSE 同样 `credentials: "include"`（admin SSE 必须带 cookie） | ✅ | `admin-api.ts:132-138` |
| `frontend/lib/auth-redirect.ts::buildLoginHref` 普通用户登录跳转 | ✅ | `auth-redirect.ts:19-22` |

### F. 已废弃

| 能力 | 状态 | 备注 |
|---|---|---|
| `X-Player-Id` 匿名 header 认证 | ❌ 已删除 | backend 代码全无引用；只 `tests/test_world_api.py` 残留作为防回归（验证 header 被忽略） |
| `X-Admin-Key` 共享密钥 admin 认证 | ❌ 已删除 | backend 代码全无引用；现役 admin 路由全走 cookie + is_admin |
| 匿名 player_id 自动 upsert User 行 | ❌ 已删除 | 必须显式登录；guest 玩法暂不开放 |

## 1B. 自助注册 + 邮箱验证 + 重置 + OAuth（2026-06-02 扩展）

把"账号只能 seed/CLI 建"补成完整自助认证。spec/plan：`docs/superpowers/specs/2026-06-02-auth-registration-design.md` + `docs/superpowers/plans/2026-06-02-auth-registration.md`。

### 能力矩阵

| 能力 | 状态 | 实现 |
|---|---|---|
| 邮箱+密码注册（先验证才能用，注册不发 session） | ✅ | `auth_service.register_with_password` + `POST /api/auth/register` |
| 邮箱验证（点链接→置 verified_at→验证即登录） | ✅ | `auth_service.verify_email` + `POST /api/auth/verify-email` |
| 登录闸门：未验证 password 身份拒登（403 code 40302） | ✅ | `login_with_password` 加 verified_at 判空 |
| 重发验证邮件（限流，不泄漏邮箱状态） | ✅ | `resend_verification` + `POST /api/auth/resend-verification` |
| 忘记密码（防枚举，总返回成功） | ✅ | `request_password_reset` + `POST /api/auth/password/forgot` |
| 重置密码（改 hash + 失效该用户全部 session） | ✅ | `reset_password` + `POST /api/auth/password/reset` |
| Google OAuth（OIDC 授权码流） | ✅ | `oauth_service` + `/api/auth/oauth/google/{start,callback}` |
| LinuxDo OAuth（connect.linux.do） | ✅ | 同上，provider=linuxdo（live 验证通过） |
| 账号合并：按已验证邮箱（一个已验证邮箱一个 user） | ✅ | `resolve_account_by_verified_email`（verify + oauth 共用） |
| `auth_identities.verified_at` 字段 | ✅ | migration 757e92842328 + 回填老身份=created_at |
| 令牌 Redis TTL+单次（verify 24h / reset 1h / oauth state 10min） | ✅ | `services/auth_tokens.py` |
| 邮件服务抽象（console dev / Resend prod） | ✅ | `services/email_service.py` |
| 端点限流（IP+邮箱滑窗，复用 token-bucket） | ✅ | `api/auth.py::_rate_limit` |

### 关键实现要点

- **先验证才能用**：注册建 `User(active)` + `password identity(verified_at=NULL)`，**不发 session**；点邮件链接 `verify_email` 才置 `verified_at` 并发 session（验证即登录）。`login_with_password` 对 `verified_at IS NULL` 直接 403 code 40302。迁移把存量身份回填 `verified_at=created_at`，避免老用户被闸门锁死。
- **账号合并不变式**：`resolve_account_by_verified_email(email, identity)` —— 任何身份从"未验证→已验证"的写入点（邮箱验证成功、OAuth 回调）统一调用：若该邮箱已属另一 user 的已验证身份，把当前身份改挂过去并清理孤儿空 user，保证"一个已验证邮箱只对应一个 user"。仅按**已验证**邮箱匹配。
  - ⚠️ LinuxDo 常返回**私密转发邮箱**（`@privaterelay.linux.do`），与真实邮箱对不上 → LinuxDo 账号不会自动合并到邮箱/Google 账号（隐私设计，可接受）。
- **OAuth 用 authlib + SessionMiddleware**：state/nonce 走 authlib 官方的 starlette `SessionMiddleware`（签名 cookie，比自管 Redis state 更不易随版本翻车）；token 交换 / OIDC id_token 校验交给 authlib。回调 `normalize_profile` 统一各家 userinfo → `{provider_user_id, email, email_verified, name, avatar}`；`next` 走站内白名单防开放重定向。
- **令牌全 Redis**：`auth:{verify|reset|oauth_state}:<token>`，TTL 过期 + 用后即删，不建 token 表。
- **防枚举**：`forgot` 不论邮箱是否存在都返回成功；`resend` 对不存在/已验证静默。

### 端点 + 错误码

| 端点 | 关键码 |
|---|---|
| `POST /api/auth/register` | `40901` 邮箱已注册 · `40001` 密码太短 · `422` 邮箱格式 |
| `POST /api/auth/verify-email` | `40010` 链接失效/过期 |
| `POST /api/auth/password/login`（既有，新增闸门） | `40302` 请先验证邮箱 |
| `POST /api/auth/password/{forgot,reset}` | reset `40010` |
| `GET /api/auth/oauth/{google,linuxdo}/{start,callback}` | `40004` 不支持 · `40011` state 校验失败 |

### 配置 / 上线

新增 env 见 `backend/.env.example` 的"用户认证"段。上线还需：inkwild.app DNS 配 Resend SPF/DKIM；Google/LinuxDo OAuth app 登记回调 `{PUBLIC_API_URL}/api/auth/oauth/{provider}/callback`；prod 设 `EMAIL_BACKEND=resend` + `SESSION_COOKIE_DOMAIN=.inkwild.app` + 随机 `SESSION_SECRET_KEY`；prod DB 跑 `alembic upgrade head`。

### 测试

`tests/test_auth_tokens.py` · `test_email_service.py` · `test_auth_registration.py` · `test_auth_api.py` · `test_password_reset.py` · `test_oauth_service.py` · `test_oauth_api.py`，共 29 测试。

## 2. 关键能力实现要点

### 2.1 三表分离的用户体系（users / auth_identities / web_sessions）

**问题**：早期实现把"邮箱 / 密码 / 手机号"等都堆在 `users` 表里，将来想加 OAuth（微信/Google）要么再加列要么搞个 sparse 表，多账号合并（同一人通过不同 provider 登录）也很难干净表达。

**解决**：按"身份 / 凭证 / 会话"三个生命周期拆三张表：
- `users` —"这个人"，业务实体只引用 user_id；含 `is_admin` 之类的人格属性
- `auth_identities` —"这个人提供的某种登录方式"，UNIQUE (provider, provider_user_id)；同一 user 可有多行（多种方式登录到同一账号）；`union_id` 字段为多 provider 同源合并保留
- `web_sessions` —"这个人当前的某次浏览器登录"，cookie 值就是 session.id；多设备登录就是多行

**实现**：
- `models/user.py` 三个 `Base` 子类
- 登录路径：`AuthService.login_with_password` 先 lookup AuthIdentity → 验密 → 拿 User → 建 WebSession
- `/api/auth/me`：通过 cookie 拿 WebSession → User，再回查 AuthIdentity 列表展示给前端（`identities[]` 让用户看到自己绑了哪些登录方式）

**取舍**：拒绝了"users 一张大表带 email + password_hash + wechat_open_id + ..."—— sparse 列、加新 provider 必动 schema、且无法表达"同一邮箱同时绑了密码和 OAuth"。三表略复杂但拓展面打开。

### 2.2 Cookie session sliding TTL

**问题**：90 天硬过期对长期不登录的用户太短（每隔 90 天逼登录一次），而每次访问都重置 90 天又有"无限期"风险。需要平衡。

**解决**：sliding window —— 每次成功 `get_user_by_session_id`，把 `expires_at` 推到 `now + 90d`；同时更新 `last_seen_at`。用户每天用就永远不到期；停用 90 天才被清。

**实现**：`services/auth_service.py:108-117`：

```python
now = utcnow()
web_session.last_seen_at = now
web_session.expires_at = now + timedelta(days=settings.web_session_days)
```

`get_user_by_session_id` 在每次依赖解析时跑（即每次 API 调用）。

**取舍**：写操作放在 GET-style 调用里有点违和（理论上读操作不该写 DB），但开销 = 每次请求一次 UPDATE web_sessions，PostgreSQL 用 b-tree 主键索引这是亚毫秒事；换来"用户体验上 cookie 永不掉"非常划算。也拒绝了"前端定期 ping refresh"——多一个网络往返，且前端忘了 ping 就掉线。

### 2.3 Admin 三层权限闸（cookie → is_admin → audit）

**问题**：admin 写操作既要"挡住非 admin"又要"留下证据"。前者是 401/403，后者是 audit log。两件事必须都做且不能漏。

**解决**：三层防线：
1. **Cookie 解析**：`get_current_user_optional` 通过 cookie 拿 User，没有 → 401
2. **is_admin 校验**：`get_current_admin_user` 在 user 上叠一层，`not user.is_admin` → 403
3. **审计落库**：每个写操作在路由内显式 `await record_admin_action(...)`；read-only 不打

`api/admin_models.py` 演示了"路由级 dependency 兜底 + 路由内显式校验"的组合：`router = APIRouter(..., dependencies=[Depends(get_current_admin_user)])` 防止某个端点忘了加；同时各 POST/PUT/DELETE 内再 `admin_user: User = Depends(get_current_admin_user)` 拿到 user 对象传给 `record_admin_action`。

**实现**：
- 依赖：`backend/dependencies.py:36-41`
- 审计：`services/audit_service.py::record_admin_action`
- audit log 字段：`action`（如 `model_provider.create` / `world_draft.publish`）+ `resource_type` + `resource_id` + `payload`（JSON，写参数副本）+ `ip_address` + `user_agent`

**取舍**：拒绝了"中间件统一打 audit"——audit 需要语义化的 `action` 字符串和 `resource_id`，泛中间件只能拿 method+path 这种粗粒度信息，无法支撑 admin 排查"谁改了这个世界的 cover_image"。显式调用换来精度。

### 2.4 `python -m cli.create_admin` 引导第一位 admin

**问题**：fresh DB 没有 admin 用户；admin 路由全部 403；admin UI 进不去；`/api/admin/users/{id}/promote` 这种自启动路由也得 admin 才能调——鸡生蛋问题。

**解决**：纯 CLI 工具，绕过 HTTP 层直接连 DB。给定 email，已存在 password identity 就提升 is_admin，否则建 User + identity。运维部署后第一步跑：

```bash
python -m cli.create_admin admin@example.com --password '...'
```

**实现**：
- `backend/cli/create_admin.py`
- 利用 `create_or_promote_admin` async 函数 + `asyncio.run` 包装；连 DB 走 `database.async_session()` 复用
- `getpass.getpass` 交互式输入密码（无 `--password` 时）
- 用 `services/auth_service.py::hash_password` / `normalize_email` 保证跟登录路径完全一致

**取舍**：拒绝了"环境变量 INITIAL_ADMIN_EMAIL=... 启动时自动建"——环境变量 leak 到日志风险大；CLI 显式 + 一次性更安全。也拒绝了"`/api/admin/bootstrap` 公开端点"——一旦忘删就是后门。

### 2.5 前端 adminFetch 403 重定向

**问题**：admin 用户 cookie 过期（或被 admin 自降权）后访问 admin 页面时，FE 收到 403 不应该卡死或显示一堆错误——应该平滑跳到登录页并保留原路径。

**解决**：`adminFetch` 把 403 单独处理：调 `redirectToAdminLogin()` 把 `window.location.href` 改成 `/login?reason=admin_required&from=<encodeURIComponent(原路径)>`，同时抛 `AdminPermissionError` 让 React tree 里的 try/catch 知道这是一次重定向（而不是普通错误显示 toast）。

**实现**：
- `frontend/lib/admin-api.ts:30-38`（构造 redirect URL）
- `admin-api.ts:94-97`（403 时触发）
- 普通 `apiFetch` 不做这个 —— 普通用户登录态过期由各页面自行处理（通常是 onAuth 回调或全局 layout）

**取舍**：拒绝了"全局 fetch 拦截器一刀切处理 401/403"——admin 跟普通用户的"未登录"语义不同：普通用户可能是 guest 浏览页面，被强行跳登录会很烦；admin 路径的 403 一定意味着权限问题需要重登。分两套 fetcher 干净。

## 3. 信息隔离 / 权限边界

### ✅ 路由侧授权检查（必须有的）

| 边界 | 检查点 | 失败行为 |
|---|---|---|
| 任何认证路由 | `Depends(get_current_user)` | 401 AppError 40100 "请先登录" |
| Admin 路由 | `Depends(get_current_admin_user)` | 403 AppError 40300 "需要管理员权限" |
| Game session 所有权 | `service._get_owned_session(db, sid, user_id)` | 404 AppError 40003（隐藏存在性） |
| World 所有权 / 公开性 | 各 world 路由内 `world.created_by` / `is_public` 校验 | 404 |

### ❌ 不能做的

| 行为 | 原因 |
|---|---|
| 通过 header `X-Player-Id`/`X-Admin-Key` 认证 | 已废弃；任何重新引入 = 直接绕过 cookie 安全模型 |
| Admin 路由跳过 `record_admin_action` 写入 | 失审计 = 失合规；admin 写必须留痕 |
| 普通用户访问别人的 game session | `_get_owned_session` 强制 user_id 匹配，不要绕 |
| 在路由 handler 里直接读 `request.cookies[settings.auth_cookie_name]` | 必须走 `Depends(get_current_user)`，否则过期/无效 cookie 会被忽略 |

### 🟡 灰色区域

| 行为 | 当前处理 | 备注 |
|---|---|---|
| Admin read-only 操作不打 audit | by design | 减噪音；但"谁看了什么"无追溯 |
| Dev `/api/dev/login` 不要密码 | `ENABLE_DEV_AUTH=true` 时才注册 dev_router | 生产必须保持 `false` |
| Admin 创建的 World/Script 是否归属 admin user_id | 是（`created_by`）— admin 离职删号会留 NULL | `users` 删除策略需注意 |

## 4. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/api/auth.py` | login / logout / me / dev_login 路由 |
| `backend/dependencies.py` | `get_db` / `get_current_user[_optional]` / `get_current_admin_user` / `get_redis` |
| `backend/services/auth_service.py` | 密码哈希 / 校验 / login / session 获取 / sliding TTL |
| `backend/services/audit_service.py` | `record_admin_action` 单一写入函数 |
| `backend/cli/create_admin.py` | 首位 admin 引导 CLI |
| `backend/models/user.py` | User / AuthIdentity / WebSession 三表 |
| `backend/models/audit_log.py` | AdminAuditLog 表 |
| `backend/api/admin.py` | 创作工坊 / 世界管理 / 草稿发布等 admin 路由（一堆 record_admin_action 调用） |
| `backend/api/admin_models.py` | 模型管理 admin 路由（router-level 依赖示例） |
| `backend/schemas/auth.py` | CurrentUserDTO / IdentitySummaryDTO / PasswordLoginRequest |
| `frontend/stores/auth.ts` | `useAuthStore` Zustand store（loadMe / login / logout） |
| `frontend/lib/types.ts` | CurrentUserDTO / `normalizeCurrentUser`（暴露 `isAdmin` camelCase） |
| `frontend/lib/admin-api.ts` | `adminFetch` 403 重定向 + `streamAdminEvents` cookie 转发 |
| `frontend/lib/auth-redirect.ts` | 普通登录跳转构造 |

## 5. 配置项

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `AUTH_COOKIE_NAME` | `inkwild_session` | cookie 名 |
| `WEB_SESSION_DAYS` | `90` | session 过期天数（sliding） |
| `ENABLE_DEV_AUTH` | `false` | 是否注册 `/api/dev/login` 后门 |
| `DEV_USER_EMAIL` | `pokonyan1666@gmail.com` | dev login 默认账号 |
| `DEV_USER_PASSWORD_HASH` | scrypt 串 | dev 账号密码 hash（密码变了改这串） |
| `DEBUG` | `false` | False 时 cookie `secure=True`（HTTPS only） |

## 6. 数据库 schema

```sql
users (
  id UUID PK,
  status,                      -- active / disabled
  is_admin BOOLEAN NOT NULL DEFAULT FALSE,
  nickname, avatar_url,
  created_at, updated_at, last_login_at
)

auth_identities (
  id UUID PK,
  user_id FK → users.id,
  provider,                    -- 当前只用 "password"，预留 OAuth 扩展
  provider_user_id,            -- password 时 = 邮箱小写
  credential_hash,             -- scrypt 串（仅 password provider）
  email, phone,
  union_id,                    -- 多 provider 同源合并预留
  verified_at,                 -- 该身份邮箱是否已验证（2026-06-02；NULL=未验证，登录闸门据此拦 password）
  profile JSON,
  created_at, last_login_at
)
UNIQUE (provider, provider_user_id)
INDEX (user_id)
INDEX (union_id)

web_sessions (
  id UUID PK,                  -- cookie value
  user_id FK,
  expires_at NOT NULL,
  created_at, last_seen_at,
  user_agent, ip_address
)
INDEX (user_id)
INDEX (expires_at)             -- 清理过期 session

admin_audit_logs (
  id UUID PK,
  admin_user_id FK → users.id ON DELETE SET NULL,  -- admin 删号后保留日志
  action,                      -- 如 model_provider.create / world_draft.publish
  resource_type, resource_id,
  payload JSON,                -- 写参数副本
  ip_address, user_agent,
  created_at
)
INDEX (admin_user_id, created_at)
INDEX (resource_type, resource_id)
```

## 7. 测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_auth_service.py` | 密码哈希 + 校验 + login + session sliding TTL + dev_login |
| `tests/test_auth_api.py` | login/logout/me 路由 + cookie 设置 + 401/403 |
| `tests/test_admin_audit.py` | record_admin_action 写入 + 字段完整性 |
| `tests/test_admin_api.py` | admin 路由 403 兜底 + 写操作落 audit |
| `tests/test_dependencies.py` | get_current_user[_optional] / get_current_admin_user 各路径 |
| `tests/test_world_api.py` | 残留 X-Player-Id header 测试（验证已被忽略，不再走匿名 upsert） |

## 8. 已知短板与未来扩展

### P1

- **Audit log 没分页 / 检索 UI**：admin 后台目前没看 audit log 的页面；要查"谁改了 model_slot=npc_agent" 必须 SQL。规模上来后会成痛点。

### P2

- ~~**OAuth 三方登录**~~ → **2026-06-02 已落地 Google + LinuxDo**（见 §1B，按已验证邮箱合并而非 union_id）。**微信仍未做**：网站扫码登录需企业营业执照 + 微信开放平台认证，个人主体接不了，等有公司主体再上。
- **Admin 操作前 reauth**：高风险操作（删世界、改 model slot）当前只检查 cookie；可加"30 分钟内重输密码才能继续"，敏感写操作另算。
- **多设备 session 管理 UI**：用户看不到自己有几个 session、不能远程登出某设备。schema 有 `user_agent` / `ip_address` 字段就缺界面。
- **Admin role 分级**：现在只有 is_admin 一个 boolean —— 创作工坊运营 / 模型后台 / 用户管理三件事权限平铺。规模化后需要 `roles` 多对多。

### P3

- **JWT / 无状态 session**：当前每次请求查 web_sessions 表；引流量大可换 stateless JWT，但 revocation 复杂、且 sliding TTL 难做（要存 refresh token），权衡后保持 stateful。
- **cookie 跨子域共享**：当前不跨域；如果做 admin.inkwild.app 单独子域要扩 `domain=.inkwild.app`。
- **是否登出所有 session**：用户改密码后只删当前 cookie，其他设备仍能用旧 session 直到自然过期。可以加"删 user_id 所有 web_sessions"动作。
