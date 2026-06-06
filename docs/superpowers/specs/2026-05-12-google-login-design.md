# Google 登录接入设计（V1）

**日期**：2026-05-12
**作者**：brainstorming session
**状态**：draft → 待 review

## 目标

为现有用户系统接入"使用 Google 登录"作为第二种 provider，作为 web 正式上线前的第一个第三方登录入口。沿用现有 cookie session 体系，不引入新框架。

## 范围

### V1 做

- 新用户点 "Continue with Google" → Google 验证 → 自动建账号 → 登录
- 老 Google 用户点 "Continue with Google" → 找到 identity → 登录
- 新建账号时，自动用 Google 的 `name` 填 `nickname`，用 `picture` 填 `avatar_url`
- 严格隔离：同 email 已被其他 provider 占用时，拒绝并提示用户

### V1 不做（明确砍掉）

- 已登录用户在账号设置里绑定 Google
- 解绑 Google
- 同 email 冲突时的"登录到现有账号"引导页
- One Tap（GIS 自动浮卡）
- Refresh token / 调用 Google API 的能力（仅做登录，不要任何额外 scope）
- 头像镜像到自己 storage

后续 PR 单独做。

## 技术路线

采用 **Google Identity Services (GIS) ID Token flow**，不走 server-side OAuth Authorization Code Flow。

理由：
- 我们只需要"可信用户身份"，不需要拉 Gmail/Drive
- GIS 不需要 redirect_uri / state / code exchange / refresh token
- 后端只多一个验签接口，复杂度最低

## 架构

```
[前端 LoginModal]
    "Continue with Google" 按钮（GIS SDK 渲染）
            │ 用户点击
            ▼
    GIS 弹窗登录 → 回调返回 credential（ID Token）
            │
            ▼
    POST /api/auth/google/login  { id_token }
            │
            ▼
[后端 /api/auth/google/login]
    1. google-auth 验签（iss/aud/exp/signature）
    2. 拒绝 email_verified=false
    3. 查 AuthIdentity(provider="google", provider_user_id=sub)
       ├─ 命中 → 取 user
       └─ 未命中:
          ├─ 同 email 已有其他 provider → 报错 40103
          └─ 创建 User + AuthIdentity
    4. 复用 _build_session() → 发 inkwild_session cookie
            │
            ▼
    前端调 loadMe() 刷新用户态，关 modal，跳转 nextPath
```

## 数据模型

**不需要迁移**。`auth_identities` 表已经是多 provider 设计：

| 字段 | Google 登录时的值 |
|---|---|
| `provider` | `"google"` |
| `provider_user_id` | Google `sub`（用户的稳定 Google ID） |
| `credential_hash` | `NULL` |
| `email` | normalized email（lowercase） |
| `phone` | `NULL` |
| `union_id` | `NULL` |
| `profile` | `{"name": "...", "picture": "https://lh3.googleusercontent.com/..."}` |

`(provider, provider_user_id)` 已有 unique 约束，天然防止同一个 Google 账号注册两次。

## 后端改动

| 文件 | 改动 |
|---|---|
| `pyproject.toml` | 加依赖 `google-auth>=2.0` |
| `config.py` | 加 `google_client_id: str = ""` |
| `schemas/auth.py` | 加 `GoogleLoginRequest { id_token: str }` |
| `services/auth_service.py` | 加 `login_with_google_id_token(db, id_token, user_agent, ip_address)` |
| `api/auth.py` | 加路由 `POST /api/auth/google/login` |

### 核心方法骨架

```python
from google.oauth2 import id_token as id_token_lib
from google.auth.transport import requests as google_requests

class AuthService:
    async def login_with_google_id_token(
        self,
        db: AsyncSession,
        id_token: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> WebSession:
        if not settings.google_client_id:
            raise AppError(50012, "Google 登录未配置", status_code=503)

        # 1. 验签
        try:
            info = id_token_lib.verify_oauth2_token(
                id_token,
                google_requests.Request(),
                settings.google_client_id,
            )
        except ValueError:
            raise AppError(40104, "Google 登录验证失败", status_code=401)

        if not info.get("email_verified"):
            raise AppError(40105, "Google 邮箱未验证", status_code=403)

        sub = info["sub"]
        email = normalize_email(info["email"])
        name: str | None = info.get("name")
        picture: str | None = info.get("picture")

        # 2. 查 google identity
        identity = (
            await db.execute(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "google",
                    AuthIdentity.provider_user_id == sub,
                )
            )
        ).scalar_one_or_none()

        if identity:
            user = await db.get(User, identity.user_id)
            if not user or user.status != "active":
                raise AppError(40102, "账号不可用", status_code=403)
        else:
            # 3. 严格隔离：检查 email 冲突
            conflict = (
                await db.execute(
                    select(AuthIdentity).where(AuthIdentity.email == email)
                )
            ).scalar_one_or_none()
            if conflict:
                raise AppError(
                    40103,
                    "该邮箱已被其他登录方式占用，请用原登录方式登录",
                    status_code=409,
                )

            # 4. 新建 user + identity
            user = User(
                nickname=name[:50] if name else None,
                avatar_url=picture,
            )
            db.add(user)
            await db.flush()  # 拿到 user.id
            identity = AuthIdentity(
                user_id=user.id,
                provider="google",
                provider_user_id=sub,
                email=email,
                profile={"name": name, "picture": picture},
            )
            db.add(identity)

        # 5. 发 session
        now = utcnow()
        user.last_login_at = now
        identity.last_login_at = now
        session = self._build_session(
            user_id=user.id,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session
```

### 路由

```python
@router.post("/google/login")
async def google_login(
    req: GoogleLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    service = _auth_service()
    web_session = await service.login_with_google_id_token(
        db,
        req.id_token,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    user = await db.get(User, web_session.user_id)
    _set_session_cookie(response, web_session.id)
    return {"code": 0, "data": await _serialize_current_user(db, user), "message": "ok"}
```

## 前端改动

| 文件 | 改动 |
|---|---|
| `app/layout.tsx` | `<head>` 加 GIS SDK：`<Script src="https://accounts.google.com/gsi/client" strategy="afterInteractive" />` |
| `stores/auth.ts` | 加 `loginWithGoogle(idToken: string)` 方法，POST `/api/auth/google/login` 后 set user |
| LoginModal 组件 | 加 "Continue with Google" 按钮，初始化 GIS、注册 callback |
| `.env.local` + `.env.example` | `NEXT_PUBLIC_GOOGLE_CLIENT_ID=...` |
| `lib/types.ts` | 不需要改 — `CurrentUserDTO.identities` 已支持任意 provider |

### GIS 按钮形态

V1 用 **Google 官方渲染**（`google.accounts.id.renderButton`），不用自绘按钮。Demo 出来后再决定是否替换为自绘版本（如果替换需评估 Google 品牌指南合规性）。

### stores/auth.ts 新增方法

```ts
loginWithGoogle: async (idToken) => {
  set({ isLoading: true, error: null });
  try {
    const userDTO = await apiFetch<CurrentUserDTO>("/api/auth/google/login", {
      method: "POST",
      body: JSON.stringify({ id_token: idToken }),
    });
    const user = normalizeCurrentUser(userDTO);
    set({ user, error: null, isLoading: false, hasLoaded: true });
    return user;
  } catch (error) {
    set({ error: getErrorMessage(error), isLoading: false, hasLoaded: true });
    throw error;
  }
},
```

### LoginModal 集成（伪代码）

```tsx
useEffect(() => {
  if (!window.google || !buttonRef.current) return;
  window.google.accounts.id.initialize({
    client_id: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID,
    callback: async (resp) => {
      try {
        await loginWithGoogle(resp.credential);
        closeLoginModal();
        if (nextPath) router.replace(nextPath);
      } catch (e) {
        // 渲染错误提示，区分 40103 / 40104 / 40105
      }
    },
  });
  window.google.accounts.id.renderButton(buttonRef.current, {
    theme: "outline",
    size: "large",
    width: "100%",
    text: "continue_with",
  });
}, [...]);
```

## 错误码

| Code | 含义 | HTTP | 前端提示 |
|---|---|---|---|
| `40103` | Google email 已被其他 provider 占用 | 409 | "该邮箱已注册，请用密码登录" |
| `40104` | Google ID token 验签失败 | 401 | "Google 登录失败，请重试" |
| `40105` | Google email 未验证 | 403 | "Google 邮箱未验证，无法登录" |
| `50012` | 后端未配置 `google_client_id` | 503 | "Google 登录暂不可用" |

## 安全清单

- ID token 走 `google-auth` 官方库验签，不自己解 JWT
- `verify_oauth2_token(audience=...)` 必传 `google_client_id`，防止其他 app 的 token 被复用
- 拒绝 `email_verified=false`（防止有人在 Google 端绑定未验证邮箱后伪造身份）
- `nickname` 截断到 50（`User.nickname` schema 限制）
- `avatar_url` 长度受 `String(500)` 限制；存原始 Google URL，不主动拉远端图片（避免 SSRF）
- Client Secret 在 GIS ID Token flow 中**不需要**，仅存 `client_id` 即可
- 沿用现有 `samesite=lax` cookie，正式上线时 `secure=True`（`debug=False` 时自动开启）

## 测试

按项目原则（轻量、核心路径），写 4 个 unit test，全部 mock 掉 `id_token_lib.verify_oauth2_token`：

| 场景 | 期望 |
|---|---|
| 新用户首次 Google 登录 | 建 1 个 User + 1 个 AuthIdentity + 1 个 WebSession，cookie 设置成功 |
| 老 Google 用户再次登录 | 不新建 User/Identity，last_login_at 更新，发新 session |
| 同 email 已有 password identity | 抛 `AppError(40103)`，HTTP 409 |
| `email_verified=false` | 抛 `AppError(40105)`，HTTP 403 |

不写：
- GIS 前端 SDK 的集成测试
- 真实网络验签调用
- 浏览器 e2e

## 部署 / 上线 checklist

**Google Cloud Console**（人工操作）：
1. 创建 / 选择 Google Cloud project
2. 配置 OAuth consent screen（External，scope: `openid`、`email`、`profile`）
3. 创建 OAuth 2.0 Client ID（Web application）
   - Authorized JavaScript origins：`http://localhost:3000` + 正式域名
   - Authorized redirect URIs：可空（GIS ID Token 不走 redirect）
4. 拿 Client ID
5. 上线前提交 OAuth verification（基础 scope 一般几天通过）

**环境变量**：
- 后端 `.env`：`GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com`
- 前端 `.env.local`：`NEXT_PUBLIC_GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com`（值相同）

**已知坑预防**：
- Cookie 跨域：现有 `samesite=lax` 配合 Next.js 同源/代理即可
- 移动端 Safari：GIS 按钮支持 OK，One Tap 才有兼容性问题（V1 不做）
- Verification 状态：未审核期间 Google 限制 100 test users，本地开发不受限

## 不变量

实现完成后，以下不变量必须成立：

1. `auth_identities` 表新增 `provider="google"` 的行，不破坏 `(provider, provider_user_id)` 唯一约束
2. Google 登录走的 session 和密码登录走的 session 在 `web_sessions` 表中无差异
3. `/api/auth/me` 返回的 `identities` 数组里能看到 `provider: "google"` 项
4. `/api/auth/logout` 对 Google session 同样有效（不需要任何修改）
5. 不引入新的认证 token、不引入新的 cookie、不引入新的 header
