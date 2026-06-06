# 用户认证：邮箱注册 + 验证 + OAuth（Google / LinuxDo）设计

- 日期：2026-06-02
- 状态：设计已确认，待写实现计划
- 范围：正式上线前补齐自助注册与第三方登录

## 背景

当前 `auth` 只有「邮箱+密码登录」「me」「logout」三个端点（`api/auth.py`）+ 一个 dev 登录。**没有任何注册路径**，账号只能靠 seed/手动建。前端 `LoginModal` 有个 LinuxDo 按钮，但调的 `/api/auth/oauth/linuxdo/start` 后端不存在，是**死链**。无发信能力、无重置密码。

数据模型早为多身份设计：`users` + `auth_identities`(provider / provider_user_id / credential_hash / email / phone / union_id / profile) + `web_sessions`（session cookie 认证）。注册会触发已就位的 500 积分 `signup_grant`（钱包惰性创建时发放）。密码哈希用 `hashlib.scrypt`（`services/auth_service.py`，格式 `scrypt$N$r$p$salt$key`），复用。

## 目标 / 成功标准

- 用户能用「邮箱+密码」自助注册，**先点验证邮件链接、验证后才能登录使用**。
- 支持「忘记密码 → 邮件重置」。
- 支持 Google、LinuxDo 第三方登录；前端死链按钮接通。
- 同一已验证邮箱跨方式**自动合并为一个账号**。
- 上线后国内外用户都可用（服务器在东京，国内外直连；发信走 inkwild.app 自有域名保送达）。

## 关键决策（已确认）

1. **验证策略**：先验证才能用。注册后不发 session；点邮件链接验证后方可登录。
2. **重置密码**：v1 一起做。
3. **账号合并**：按已验证邮箱自动合并（一人一号、多登录方式）。
4. **方案选型**：扩展现有自建认证（A），不引第三方认证框架。
5. **OAuth 实现**：用 **authlib**（成熟专用库，正确处理 token 交换 / OIDC / id_token JWKS 校验 / state），不手写。理由=认证安全正确性，符合"引库需理由"例外。
6. **邮件服务**：**Resend**（免费 3000/月，送达好），httpx 直发其 REST API，不引 SDK。抽象成 `EmailSender` 接口以便日后换 Brevo/SES。

## 架构总览

```
前端 (Next, inkwild.app)
  注册页 / 去验证提示页 / 验证结果页 / 忘记密码页 / 重置密码页
  登录入口 + Google 按钮 + LinuxDo 按钮
        │  (REST + 302 OAuth 跳转)
        ▼
后端 (FastAPI, api/inkwild.app 或同源)
  api/auth.py          ← 扩展：register / verify-email / resend-verification
                          forgot / reset / oauth.{start,callback}
  services/auth_service.py   ← 注册、验证、合并、重置逻辑
  services/email_service.py  ← 新：EmailSender 抽象 + ResendEmailSender
  services/oauth_service.py  ← 新：authlib 封装 Google / LinuxDo
  middleware/rate_limit.py   ← 复用 RedisTokenBucketRateLimiter
  Redis                      ← verify/reset token（TTL+单次）、oauth state
  Postgres                   ← users / auth_identities(+verified_at) / web_sessions
```

## 数据模型变更（最小）

- `auth_identities` 新增 `verified_at: datetime | None`（该身份邮箱是否已验证；Alembic 迁移）。
- `provider` 取值约定：`password` / `google` / `linuxdo`。
- `provider_user_id`：password = 归一化邮箱（`normalize_email`）；google = OIDC `sub`；linuxdo = LinuxDo user id。
- `email` 存邮箱；`profile` 存 OAuth 原始资料（name/avatar 等）；`union_id` 暂不用。
- 不新建 token 表。

## 令牌策略（Redis，TTL + 单次）

| 用途 | key | value | TTL |
|---|---|---|---|
| 邮箱验证 | `auth:verify:<token>` | `{user_id, identity_id}` | 24h |
| 密码重置 | `auth:reset:<token>` | `{user_id, identity_id}` | 1h |
| OAuth state | `auth:oauth:state:<state>` | `{provider, next}` | 10min |

token = `secrets.token_urlsafe(32)`。用后即 `DEL`（单次有效）。

## 邮件服务（`services/email_service.py`）

- `class EmailSender(ABC)`: `async send(to, subject, html, text) -> None`。
- `ResendEmailSender`: httpx POST `https://api.resend.com/emails`，`from = EMAIL_FROM`(`noreply@inkwild.app`)，Bearer `RESEND_API_KEY`。
- `get_email_sender()` 工厂（仿 `image_storage.get_image_storage`），按 `EMAIL_BACKEND` 切（resend / 未来 brevo/ses / dev-console）。dev 下可用 console backend 把邮件打日志不真发。
- 模板：验证邮件、重置邮件。先中文，预留 i18n（按用户语言）。
- 上线依赖：inkwild.app DNS 配 Resend 的 SPF / DKIM / return-path（否则进垃圾箱）。

## 流程

### A. 邮箱注册 + 验证

1. `POST /api/auth/register {email, password, nickname?}`
   - 校验邮箱格式、密码强度（≥8 位等）。
   - 邮箱占用判定（避开 `(provider, provider_user_id)` 唯一约束冲突）：
     - 已存在该邮箱的**已验证** password 身份 → 拒绝 `409`「该邮箱已注册，请登录/找回密码」。
     - 已存在该邮箱的**未验证** password 身份（上次注册没验证）→ **幂等再注册**：更新其 `credential_hash` + 重发验证邮件，不新建 user、不报错。
     - 否则建 `User(status=active)` + `AuthIdentity(provider=password, provider_user_id=邮箱, credential_hash, email, verified_at=NULL)`。
   - 生成 verify token 入 Redis，发验证邮件。
   - **不发 session**。返回 `{code:0, data:{pending_verification:true, email}}`。
2. 验证：邮件链接 → 前端页 `/verify-email?token=<t>` → 前端调 `POST /api/auth/verify-email {token}`。
   - 后端校验 token → `identity.verified_at = now()` → `DEL` token。
   - **验证即登录**：后端直接建 session（cookie 落前端同域，体验顺）→ 前端展示"验证成功"。
   - token 失效/过期 → `400` 明确错误 + 重发入口。
3. `POST /api/auth/resend-verification {email}`：限流，重发（仅当存在未验证 password 身份）。
4. 改造 `POST /api/auth/password/login`：登录前检查 password 身份 `verified_at` 非空，否则 `403 {code:40302}`「请先验证邮箱」+ 提示可重发。

### B. 忘记 / 重置密码

1. `POST /api/auth/password/forgot {email}`：**无论邮箱是否存在都返回成功**（防账号枚举）；存在 password 身份才生成 reset token 发邮件。
2. `POST /api/auth/password/reset {token, new_password}`：校验 token → 更新 `credential_hash` → `DEL` token → **失效该用户全部 web_session**（强制重新登录）。

### C. OAuth（Google / LinuxDo，authlib）

1. `GET /api/auth/oauth/{provider}/start?next=<path>`：authlib 生成授权 URL（带 state，state 入 Redis）→ 302 跳转。
   - Google scope：`openid email profile`。
   - LinuxDo：`connect.linux.do` 授权端点。
2. `GET /api/auth/oauth/{provider}/callback?code&state`：
   - 校验 state（Redis 取出并删）。
   - authlib 用 code 换 token；Google 走 OIDC 拿 `userinfo`（authlib 校验 id_token），LinuxDo 调其 user 接口。
   - 得 `{provider, provider_user_id, email(已验证), name, avatar}` → 进合并逻辑（D）→ 建 session → 302 回 `next`（白名单校验，防开放重定向）。

### D. 账号解析与合并（按已验证邮箱，全局唯一）

**不变式：一个已验证邮箱只对应一个 user。** 任何身份从「未验证 → 已验证」的写入点（邮箱验证成功、OAuth 回调）都统一走同一个 helper：

`resolve_account_by_verified_email(email, current_identity) -> user`
1. 若该 `email` 已属某 user 的**已验证**身份 → 把 `current_identity` 改挂到那个 user（合并），并清理同邮箱遗留的**未验证**孤儿身份及空 user。
2. 否则 `current_identity` 留在自己 user 上。

**OAuth 回调** 拿到 `(provider, provider_user_id, verified_email, name, avatar)`：
1. 已存在 `(provider, provider_user_id)` 身份 → 直接登录其 user，更新 `last_login_at`。
2. 否则新建本 provider 身份（`verified_at=now`）→ 走 `resolve_account_by_verified_email`。
3. 若最终落到**全新** user：set `nickname`/`avatar_url` from profile；signup grant 由现有惰性钱包机制发放（注册不额外处理）。

**邮箱验证成功**（流程 A 第 2 步）置 `verified_at` 后同样走 `resolve_account_by_verified_email`：罕见情况（先注册没验证、期间又用 OAuth 登了同邮箱）会被合并到既有 user，丢弃孤儿，杜绝"同邮箱两个已验证 user"。

> 安全前提：仅按**已验证**邮箱合并；未验证 password 身份不参与匹配，但会在对方验证/OAuth 时被作为孤儿清理。

## Session / Cookie（复用现有）

- 沿用 `web_sessions` + httponly cookie（`_set_session_cookie`）。
- 上线 prod env：`SESSION_COOKIE_DOMAIN=.inkwild.app`、`secure=true`（debug=false 自动）、`samesite=lax`。
- OAuth 回调落点必须能写该 cookie 的域（前后端同源或 api 子域 + 顶级域 cookie）。

## 防滥用（复用 `RedisTokenBucketRateLimiter`）

- 限流维度 **IP + 邮箱**：`register` / `password/login` / `forgot` / `resend-verification`。
- 所有 token：Redis TTL + 单次删除。
- 密码：复用 `hash_password`（scrypt）。
- 重置成功失效全部 session。
- v1 **不上图形验证码 / 2FA**（被刷再加）。

## 前端

- 新增页面：`/register`、验证提示页（"验证邮件已发往 x@y"）、验证结果页（成功/失效）、`/forgot-password`、`/reset-password?token=`。均 RHF + zod，复用现有登录页视觉与 `lib/api`。
- 改造：登录页 / `LoginModal` 加"注册"入口、Google 按钮、接通 LinuxDo 按钮；未验证 403 文案 + 重发按钮。
- i18n：zh / en 文案补齐（`i18n/*.json`）。

## 配置 / 上线清单

| 项 | 内容 |
|---|---|
| DNS | inkwild.app 配 Resend SPF / DKIM / return-path |
| Google | Google Cloud 建 OAuth client，登记授权回调 URI（prod + dev） |
| LinuxDo | 申请 OAuth app，登记回调 |
| env | `RESEND_API_KEY` `EMAIL_FROM=noreply@inkwild.app` `EMAIL_BACKEND=resend` `GOOGLE_CLIENT_ID/SECRET` `LINUXDO_CLIENT_ID/SECRET` `SESSION_COOKIE_DOMAIN=.inkwild.app` `PUBLIC_WEB_URL`(拼邮件/回调链接) |
| 依赖 | 新增 `authlib`（pyproject）；httpx 已有 |

## 范围外（YAGNI，明确不做）

微信登录（需企业营业执照，后做）、手机号 / 短信、2FA、图形验证码、账号设置页手动绑定 / 解绑身份、邮件 i18n 之外的多模板。

## 测试（轻量，按项目原则）

- 单元：scrypt 复用不动；注册/验证/合并的核心分支（邮箱占用、未验证拦截、按邮箱合并三分支、token 过期）。
- 邮件/OAuth 用假 sender / 假 provider mock，不打外网。
- 不为边角 case 堆测试。

## 待确认 / 风险

- LinuxDo OAuth 是否返回**已验证**邮箱：需在实现时确认其 userinfo 字段；若不保证已验证，则 LinuxDo 不参与"按邮箱合并"，仅按 `(provider, provider_user_id)` 独立成号。
- Resend 国内收件箱（qq/163）送达需 DKIM 对齐，上线前实测。
