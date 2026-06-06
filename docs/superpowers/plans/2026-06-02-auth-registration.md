# 用户认证（邮箱注册 + 验证 + OAuth）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 InkWild 补齐自助邮箱注册（先验证才能用）、忘记密码、Google/LinuxDo 第三方登录，并按已验证邮箱自动合并账号。

**Architecture:** 扩展现有自建认证（`users`/`auth_identities`/`web_sessions` + session cookie）。新增薄模块：`email_service`（Resend，httpx）、`oauth_service`（authlib）。验证/重置/oauth-state 令牌全走 Redis（TTL+单次）。仅按已验证邮箱合并，`resolve_account_by_verified_email` 守"一个已验证邮箱一个 user"不变式。

**Tech Stack:** FastAPI / SQLAlchemy async / Alembic / Redis（`redis.asyncio`）/ authlib / httpx / Next.js（RHF+zod）/ pytest。

**Spec:** `docs/superpowers/specs/2026-06-02-auth-registration-design.md`

**前置说明（git）：** 本仓库目前 0 提交、个人身份、remote 已配。执行前与用户确认首次提交/分支策略；下面每个 Task 的 commit 步骤假设已有基线提交。

---

## Phase 1 — 基础设施

### Task 1: 依赖 + 配置项

**Files:**
- Modify: `backend/pyproject.toml`（dependencies 加 `authlib`）
- Modify: `backend/config.py:47` 附近（Settings 加字段）

- [ ] **Step 1: 加 authlib 依赖**

`backend/pyproject.toml` dependencies 数组加一行（紧邻 `"httpx>=0.28.0",`）：
```toml
    "authlib>=1.3.0",
```

- [ ] **Step 2: 加配置字段**

`backend/config.py` 的 `Settings` 类里（紧接 `oss_key_prefix` 之后）加：
```python
    # Email (transactional)
    email_backend: str = "console"  # console | resend
    resend_api_key: str = ""
    email_from: str = "InkWild <noreply@inkwild.app>"
    public_web_url: str = "http://localhost:3000"  # 拼验证/重置/回调链接
    # OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    linuxdo_client_id: str = ""
    linuxdo_client_secret: str = ""
    # token TTL（秒）
    email_verify_ttl_seconds: int = 24 * 3600
    password_reset_ttl_seconds: int = 3600
    oauth_state_ttl_seconds: int = 600
    # auth 限流
    auth_rate_limit_per_window: int = 5
    auth_rate_limit_window_seconds: int = 300
```

- [ ] **Step 3: 安装依赖并确认导入**

Run（容器内）：`docker exec talealive-backend-1 pip install -e ".[dev]" >/dev/null && docker exec talealive-backend-1 python -c "import authlib; print(authlib.__version__)"`
Expected: 打印 authlib 版本号

- [ ] **Step 4: Commit**
```bash
git add backend/pyproject.toml backend/config.py
git commit -m "chore(auth): add authlib + email/oauth config fields"
```

---

### Task 2: Alembic 迁移 — `auth_identities.verified_at`（含回填）

**Files:**
- Modify: `backend/models/user.py`（AuthIdentity 加字段）
- Create: `backend/migrations/versions/<rev>_add_verified_at.py`（用 `alembic revision` 生成）

- [ ] **Step 1: 模型加字段**

`backend/models/user.py` 的 `AuthIdentity`，在 `union_id` 后加：
```python
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

- [ ] **Step 2: 生成迁移**

Run: `docker exec talealive-backend-1 alembic revision -m "add auth_identities.verified_at"`
然后编辑生成的版本文件 `upgrade()` / `downgrade()`：
```python
def upgrade() -> None:
    op.add_column("auth_identities", sa.Column("verified_at", sa.DateTime(), nullable=True))
    # 回填：现有身份（seed/dev/已存在用户）视为已验证，避免上线后被登录闸门锁死
    op.execute("UPDATE auth_identities SET verified_at = created_at WHERE verified_at IS NULL")

def downgrade() -> None:
    op.drop_column("auth_identities", "verified_at")
```

- [ ] **Step 3: 应用迁移并校验回填**

Run: `docker exec talealive-backend-1 alembic upgrade head`
Run: `docker exec talealive-db-1 psql -U postgres -d inkwild -t -A -c "select count(*) filter (where verified_at is not null) as verified, count(*) as total from auth_identities;"`
Expected: verified == total（现有身份全部回填为已验证）

- [ ] **Step 4: Commit**
```bash
git add backend/models/user.py backend/migrations/versions/
git commit -m "feat(auth): add verified_at to auth_identities + backfill existing"
```

---

### Task 3: 令牌存储（Redis，TTL + 单次）

**Files:**
- Create: `backend/services/auth_tokens.py`
- Test: `backend/tests/test_auth_tokens.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_auth_tokens.py`：
```python
import pytest
from services.auth_tokens import create_token, consume_token

@pytest.mark.asyncio
async def test_create_and_consume_single_use(fake_redis):
    token = await create_token(fake_redis, "verify", {"user_id": "u1", "identity_id": "i1"}, ttl=60)
    assert isinstance(token, str) and len(token) > 20
    payload = await consume_token(fake_redis, "verify", token)
    assert payload == {"user_id": "u1", "identity_id": "i1"}
    # 第二次消费返回 None（单次）
    assert await consume_token(fake_redis, "verify", token) is None

@pytest.mark.asyncio
async def test_wrong_purpose_namespaced(fake_redis):
    token = await create_token(fake_redis, "verify", {"x": 1}, ttl=60)
    assert await consume_token(fake_redis, "reset", token) is None
```
`fake_redis` fixture：若 `tests/conftest.py` 没有，则加（用 `fakeredis.aioredis.FakeRedis(decode_responses=True)`，dev 依赖加 `fakeredis`）。

- [ ] **Step 2: 跑测试确认失败**

Run: `docker exec talealive-backend-1 python -m pytest tests/test_auth_tokens.py -v`
Expected: FAIL（ModuleNotFoundError: services.auth_tokens）

- [ ] **Step 3: 实现**

`backend/services/auth_tokens.py`：
```python
from __future__ import annotations

import json
import secrets

import redis.asyncio as redis


def _key(purpose: str, token: str) -> str:
    return f"auth:{purpose}:{token}"


async def create_token(r: redis.Redis, purpose: str, payload: dict, ttl: int) -> str:
    token = secrets.token_urlsafe(32)
    await r.set(_key(purpose, token), json.dumps(payload), ex=ttl)
    return token


async def consume_token(r: redis.Redis, purpose: str, token: str) -> dict | None:
    key = _key(purpose, token)
    raw = await r.get(key)
    if raw is None:
        return None
    await r.delete(key)  # 单次
    return json.loads(raw)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `docker exec talealive-backend-1 python -m pytest tests/test_auth_tokens.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add backend/services/auth_tokens.py backend/tests/test_auth_tokens.py backend/tests/conftest.py backend/pyproject.toml
git commit -m "feat(auth): redis-backed single-use token store"
```

---

### Task 4: 邮件服务（`email_service.py`）

**Files:**
- Create: `backend/services/email_service.py`
- Test: `backend/tests/test_email_service.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_email_service.py`：
```python
import pytest
from services.email_service import ConsoleEmailSender, build_verify_email, build_reset_email

@pytest.mark.asyncio
async def test_console_sender_records(capsys):
    sender = ConsoleEmailSender()
    await sender.send(to="a@b.com", subject="Hi", html="<b>x</b>", text="x")
    out = capsys.readouterr().out
    assert "a@b.com" in out

def test_build_verify_email_contains_link():
    subj, html, text = build_verify_email("https://inkwild.app/verify-email?token=abc")
    assert "verify-email?token=abc" in html
    assert "verify-email?token=abc" in text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `docker exec talealive-backend-1 python -m pytest tests/test_email_service.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`backend/services/email_service.py`：
```python
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx
import structlog

from config import settings

logger = structlog.get_logger()


class EmailSender(ABC):
    @abstractmethod
    async def send(self, *, to: str, subject: str, html: str, text: str) -> None: ...


class ConsoleEmailSender(EmailSender):
    """Dev backend — prints the email instead of sending."""

    async def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        print(f"[email:console] to={to} subject={subject}\n{text}")
        logger.info("email_console", to=to, subject=subject)


class ResendEmailSender(EmailSender):
    async def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={"from": settings.email_from, "to": [to], "subject": subject, "html": html, "text": text},
            )
            resp.raise_for_status()
        logger.info("email_sent_resend", to=to, subject=subject)


def get_email_sender() -> EmailSender:
    if settings.email_backend.lower().strip() == "resend":
        return ResendEmailSender()
    return ConsoleEmailSender()


def build_verify_email(link: str) -> tuple[str, str, str]:
    subject = "验证你的 InkWild 邮箱"
    text = f"点击链接完成验证（24 小时内有效）：\n{link}\n如非本人操作请忽略。"
    html = f'<p>欢迎来到 InkWild！点击下面链接完成邮箱验证（24 小时内有效）：</p><p><a href="{link}">{link}</a></p><p>如非本人操作请忽略。</p>'
    return subject, html, text


def build_reset_email(link: str) -> tuple[str, str, str]:
    subject = "重置你的 InkWild 密码"
    text = f"点击链接重置密码（1 小时内有效）：\n{link}\n如非本人操作请忽略。"
    html = f'<p>点击下面链接重置密码（1 小时内有效）：</p><p><a href="{link}">{link}</a></p><p>如非本人操作请忽略。</p>'
    return subject, html, text
```

- [ ] **Step 4: 跑测试确认通过**

Run: `docker exec talealive-backend-1 python -m pytest tests/test_email_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add backend/services/email_service.py backend/tests/test_email_service.py
git commit -m "feat(auth): email sender abstraction (console+resend)"
```

---

## Phase 2 — 邮箱注册 + 验证 + 登录闸门

### Task 5: auth_service 注册/验证/合并核心逻辑

**Files:**
- Modify: `backend/services/auth_service.py`
- Test: `backend/tests/test_auth_registration.py`

新增方法（签名）：
```python
async def register_with_password(self, db, r, *, email, password, nickname=None) -> AuthIdentity
async def verify_email(self, db, r, token) -> WebSession   # 验证即登录
async def resend_verification(self, db, r, email) -> None
async def resolve_account_by_verified_email(self, db, email, identity) -> User  # 见 spec §D 不变式
```

- [ ] **Step 1: 写失败测试**（核心分支）

`backend/tests/test_auth_registration.py`：测 ①注册建未验证身份+不占已验证名额；②同邮箱未验证再注册=幂等更新不报错；③同邮箱已验证再注册=raise AppError(409)；④verify_email 置 verified_at 并发 session；⑤resolve 合并：邮箱已属已验证 user 时把新身份挂过去、清理孤儿。
（用 `client`/`db_session` fixture，参考现有 `tests/` 用法；redis 用 `fake_redis`。）

- [ ] **Step 2: 跑测试确认失败**

Run: `docker exec talealive-backend-1 python -m pytest tests/test_auth_registration.py -v`
Expected: FAIL

- [ ] **Step 3: 实现** （`services/auth_service.py` 追加）

```python
from services.auth_tokens import create_token, consume_token
from services.email_service import get_email_sender, build_verify_email
from middleware.error_handler import AppError

PASSWORD_MIN_LEN = 8

async def _find_password_identity(db, email):
    return (await db.execute(select(AuthIdentity).where(
        AuthIdentity.provider == "password",
        AuthIdentity.provider_user_id == normalize_email(email),
    ))).scalar_one_or_none()

class AuthService:
    # ... existing ...

    async def register_with_password(self, db, r, *, email, password, nickname=None):
        email_n = normalize_email(email)
        if len(password) < PASSWORD_MIN_LEN:
            raise AppError(40001, "密码至少 8 位", status_code=400)
        existing = await _find_password_identity(db, email_n)
        if existing and existing.verified_at is not None:
            raise AppError(40901, "该邮箱已注册，请登录或找回密码", status_code=409)
        if existing:  # 未验证 → 幂等再注册
            existing.credential_hash = hash_password(password)
            identity = existing
        else:
            user = User(status="active", nickname=nickname)
            db.add(user)
            await db.flush()
            identity = AuthIdentity(user_id=user.id, provider="password",
                                    provider_user_id=email_n, credential_hash=hash_password(password),
                                    email=email_n, verified_at=None)
            db.add(identity)
        await db.flush()
        token = await create_token(r, "verify", {"identity_id": identity.id}, ttl=settings.email_verify_ttl_seconds)
        await db.commit()
        link = f"{settings.public_web_url}/verify-email?token={token}"
        subject, html, text = build_verify_email(link)
        await get_email_sender().send(to=email_n, subject=subject, html=html, text=text)
        return identity

    async def verify_email(self, db, r, token, *, user_agent=None, ip_address=None):
        payload = await consume_token(r, "verify", token)
        if not payload:
            raise AppError(40010, "验证链接无效或已过期", status_code=400)
        identity = await db.get(AuthIdentity, payload["identity_id"])
        if not identity:
            raise AppError(40010, "验证链接无效或已过期", status_code=400)
        if identity.verified_at is None:
            identity.verified_at = utcnow()
        user = await self.resolve_account_by_verified_email(db, identity.email, identity)
        session = self._build_session(user_id=user.id, user_agent=user_agent, ip_address=ip_address)
        db.add(session)
        user.last_login_at = utcnow()
        await db.commit()
        await db.refresh(session)
        return session

    async def resend_verification(self, db, r, email):
        identity = await _find_password_identity(db, email)
        if not identity or identity.verified_at is not None:
            return  # 不泄漏状态
        token = await create_token(r, "verify", {"identity_id": identity.id}, ttl=settings.email_verify_ttl_seconds)
        link = f"{settings.public_web_url}/verify-email?token={token}"
        subject, html, text = build_verify_email(link)
        await get_email_sender().send(to=identity.email, subject=subject, html=html, text=text)

    async def resolve_account_by_verified_email(self, db, email, identity):
        """不变式：一个已验证邮箱只对应一个 user。"""
        if not email:
            return await db.get(User, identity.user_id)
        other = (await db.execute(select(AuthIdentity).where(
            AuthIdentity.email == normalize_email(email),
            AuthIdentity.verified_at.is_not(None),
            AuthIdentity.id != identity.id,
        ).order_by(AuthIdentity.created_at.asc()))).scalars().first()
        if other is None:
            return await db.get(User, identity.user_id)
        # 合并：把 current identity 挂到 other.user，清理可能的孤儿空 user
        orphan_user_id = identity.user_id
        identity.user_id = other.user_id
        await db.flush()
        if orphan_user_id != other.user_id:
            remaining = (await db.execute(select(AuthIdentity).where(
                AuthIdentity.user_id == orphan_user_id))).scalars().first()
            if remaining is None:
                orphan = await db.get(User, orphan_user_id)
                if orphan:
                    await db.delete(orphan)
        return await db.get(User, other.user_id)
```

同时**改造 `login_with_password`**：取到 identity 后、发 session 前加：
```python
        if identity.verified_at is None:
            raise AppError(40302, "请先验证邮箱后再登录", status_code=403)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `docker exec talealive-backend-1 python -m pytest tests/test_auth_registration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add backend/services/auth_service.py backend/tests/test_auth_registration.py
git commit -m "feat(auth): password registration, email verification, account merge"
```

---

### Task 6: 注册/验证 API 端点 + 限流

**Files:**
- Modify: `backend/api/auth.py`
- Modify: `backend/schemas/auth.py`
- Test: `backend/tests/test_auth_api.py`

> ⚠️ 记忆坑：新路由的 db 依赖必须 `from dependencies import get_db`（conftest 只覆盖它），否则测试连真 Postgres。

- [ ] **Step 1: schemas**

`backend/schemas/auth.py` 加：
```python
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nickname: str | None = None

class VerifyEmailRequest(BaseModel):
    token: str

class ResendVerificationRequest(BaseModel):
    email: EmailStr

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
```
（`from pydantic import EmailStr`；确保 `email-validator` 在依赖里，pydantic[email]。没有则 pyproject 加 `"pydantic[email]"`。）

- [ ] **Step 2: 写失败测试**（API 层）

`backend/tests/test_auth_api.py`：注册→断言 200+pending_verification；未验证登录→403/40302；用 console 邮件，从 redis 直接取 token 调 verify→200+cookie；重复已验证注册→409。

- [ ] **Step 3: 实现端点**

`backend/api/auth.py` 加（复用 `_set_session_cookie`、`get_redis`、限流）：
```python
from dependencies import get_redis
from middleware.rate_limit import RedisTokenBucketRateLimiter
from schemas.auth import (RegisterRequest, VerifyEmailRequest, ResendVerificationRequest,
                          ForgotPasswordRequest, ResetPasswordRequest)

async def _rate_limit(redis, key: str):
    rl = RedisTokenBucketRateLimiter(redis)
    res = await rl.allow(f"auth:{key}", limit=settings.auth_rate_limit_per_window,
                         window_seconds=settings.auth_rate_limit_window_seconds)
    if not res.allowed:
        raise AppError(42900, "操作过于频繁，请稍后再试", status_code=429)

@router.post("/register")
async def register(req: RegisterRequest, request: Request, db=Depends(get_db), redis=Depends(get_redis)):
    await _rate_limit(redis, f"register:{_client_ip(request)}")
    await _auth_service().register_with_password(db, redis, email=req.email, password=req.password, nickname=req.nickname)
    return {"code": 0, "data": {"pending_verification": True, "email": normalize_email(req.email)}, "message": "ok"}

@router.post("/verify-email")
async def verify_email(req: VerifyEmailRequest, request: Request, response: Response, db=Depends(get_db), redis=Depends(get_redis)):
    ws = await _auth_service().verify_email(db, redis, req.token,
            user_agent=request.headers.get("user-agent"), ip_address=_client_ip(request))
    user = await db.get(User, ws.user_id)
    _set_session_cookie(response, ws.id)
    return {"code": 0, "data": await _serialize_current_user(db, user), "message": "ok"}

@router.post("/resend-verification")
async def resend_verification(req: ResendVerificationRequest, request: Request, db=Depends(get_db), redis=Depends(get_redis)):
    await _rate_limit(redis, f"resend:{req.email}")
    await _auth_service().resend_verification(db, redis, req.email)
    return {"code": 0, "message": "ok"}
```
（`normalize_email`、`AppError`、`settings` import 补齐。`password_login` 因 service 改造已自动加闸门，无需改端点。）

- [ ] **Step 4: 跑测试确认通过**

Run: `docker exec talealive-backend-1 python -m pytest tests/test_auth_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add backend/api/auth.py backend/schemas/auth.py backend/tests/test_auth_api.py backend/pyproject.toml
git commit -m "feat(auth): register/verify/resend endpoints + rate limit"
```

---

## Phase 3 — 重置密码

### Task 7: 忘记/重置密码（service + API）

**Files:**
- Modify: `backend/services/auth_service.py`, `backend/api/auth.py`
- Test: `backend/tests/test_password_reset.py`

- [ ] **Step 1: 写失败测试**

①forgot 对不存在邮箱也返回成功且不发信；②forgot 对已验证 password 身份发 reset；③reset 改密码后旧密码失效、新密码可登录、该用户旧 session 全失效。

- [ ] **Step 2: 跑测试确认失败** → `pytest tests/test_password_reset.py -v`（FAIL）

- [ ] **Step 3: service 实现**（auth_service 追加）
```python
from services.email_service import build_reset_email
from sqlalchemy import delete

    async def request_password_reset(self, db, r, email):
        identity = await _find_password_identity(db, email)
        if not identity or identity.verified_at is None:
            return  # 防枚举：静默
        token = await create_token(r, "reset", {"identity_id": identity.id}, ttl=settings.password_reset_ttl_seconds)
        link = f"{settings.public_web_url}/reset-password?token={token}"
        subject, html, text = build_reset_email(link)
        await get_email_sender().send(to=identity.email, subject=subject, html=html, text=text)

    async def reset_password(self, db, r, token, new_password):
        if len(new_password) < PASSWORD_MIN_LEN:
            raise AppError(40001, "密码至少 8 位", status_code=400)
        payload = await consume_token(r, "reset", token)
        if not payload:
            raise AppError(40010, "重置链接无效或已过期", status_code=400)
        identity = await db.get(AuthIdentity, payload["identity_id"])
        if not identity:
            raise AppError(40010, "重置链接无效或已过期", status_code=400)
        identity.credential_hash = hash_password(new_password)
        await db.execute(delete(WebSession).where(WebSession.user_id == identity.user_id))  # 强制重登
        await db.commit()
```

- [ ] **Step 4: API 端点**（api/auth.py）
```python
@router.post("/password/forgot")
async def forgot_password(req: ForgotPasswordRequest, request: Request, db=Depends(get_db), redis=Depends(get_redis)):
    await _rate_limit(redis, f"forgot:{req.email}")
    await _auth_service().request_password_reset(db, redis, req.email)
    return {"code": 0, "message": "ok"}  # 总是成功

@router.post("/password/reset")
async def reset_password(req: ResetPasswordRequest, db=Depends(get_db), redis=Depends(get_redis)):
    await _auth_service().reset_password(db, redis, req.token, req.new_password)
    return {"code": 0, "message": "ok"}
```

- [ ] **Step 5: 跑测试确认通过** → `pytest tests/test_password_reset.py -v`（PASS）

- [ ] **Step 6: Commit**
```bash
git add backend/services/auth_service.py backend/api/auth.py backend/tests/test_password_reset.py
git commit -m "feat(auth): forgot/reset password with session invalidation"
```

---

## Phase 4 — OAuth（Google + LinuxDo）

### Task 8: oauth_service（authlib）

**Files:**
- Create: `backend/services/oauth_service.py`
- Test: `backend/tests/test_oauth_service.py`

- [ ] **Step 1: 写失败测试**

mock provider userinfo（不打外网），测 `upsert_oauth_identity`：①已有(provider,sub)→返回原 user；②邮箱命中已验证身份→合并；③全新→建 user+身份(verified_at)+set nickname/avatar。

- [ ] **Step 2: 跑测试确认失败** → `pytest tests/test_oauth_service.py -v`（FAIL）

- [ ] **Step 3: 实现**

`backend/services/oauth_service.py`：
```python
from __future__ import annotations
from authlib.integrations.starlette_client import OAuth
from config import settings
from models.user import AuthIdentity, User
from services.auth_service import AuthService, utcnow
from sqlalchemy import select

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
oauth.register(
    name="linuxdo",
    client_id=settings.linuxdo_client_id,
    client_secret=settings.linuxdo_client_secret,
    authorize_url="https://connect.linux.do/oauth2/authorize",
    access_token_url="https://connect.linux.do/oauth2/token",
    userinfo_endpoint="https://connect.linux.do/api/user",
    client_kwargs={"scope": "read"},
)

def normalize_profile(provider: str, info: dict) -> dict:
    """统一各家 userinfo → {provider_user_id, email, email_verified, name, avatar}"""
    if provider == "google":
        return {"provider_user_id": info["sub"], "email": info.get("email"),
                "email_verified": bool(info.get("email_verified")),
                "name": info.get("name"), "avatar": info.get("picture")}
    # linuxdo
    return {"provider_user_id": str(info["id"]), "email": info.get("email"),
            "email_verified": bool(info.get("email_verified", info.get("active", False))),
            "name": info.get("name") or info.get("username"), "avatar": info.get("avatar_url")}

async def upsert_oauth_identity(db, provider: str, profile: dict) -> User:
    svc = AuthService()
    existing = (await db.execute(select(AuthIdentity).where(
        AuthIdentity.provider == provider,
        AuthIdentity.provider_user_id == profile["provider_user_id"],
    ))).scalar_one_or_none()
    if existing:
        user = await db.get(User, existing.user_id)
        user.last_login_at = utcnow()
        await db.commit()
        return user
    verified = profile["email_verified"]
    user = User(status="active", nickname=profile.get("name"), avatar_url=profile.get("avatar"))
    db.add(user)
    await db.flush()
    identity = AuthIdentity(user_id=user.id, provider=provider,
                            provider_user_id=profile["provider_user_id"], email=profile.get("email"),
                            verified_at=utcnow() if verified else None,
                            profile=profile)
    db.add(identity)
    await db.flush()
    if verified and profile.get("email"):
        user = await svc.resolve_account_by_verified_email(db, profile["email"], identity)
    user.last_login_at = utcnow()
    await db.commit()
    return user
```

- [ ] **Step 4: 跑测试确认通过** → `pytest tests/test_oauth_service.py -v`（PASS）

- [ ] **Step 5: Commit**
```bash
git add backend/services/oauth_service.py backend/tests/test_oauth_service.py
git commit -m "feat(auth): oauth identity upsert + merge (google/linuxdo)"
```

---

### Task 9: OAuth start/callback 端点

**Files:**
- Modify: `backend/api/auth.py`, `backend/main.py`（authlib 需 SessionMiddleware 存 state，或用 Redis state 自管）

**实现选择：** 用 Redis 自管 state（不引 starlette SessionMiddleware，避免额外 cookie），authlib 仅用其 client 做 token 交换。

- [ ] **Step 1: 端点实现**（api/auth.py）
```python
import secrets as _secrets
from services.oauth_service import oauth, normalize_profile, upsert_oauth_identity
from services.auth_tokens import create_token, consume_token

_ALLOWED_NEXT_PREFIX = "/"  # 防开放重定向：只允许站内路径

@router.get("/oauth/{provider}/start")
async def oauth_start(provider: str, request: Request, next: str = "/", redis=Depends(get_redis)):
    if provider not in ("google", "linuxdo"):
        raise AppError(40004, "不支持的登录方式", status_code=404)
    state = _secrets.token_urlsafe(24)
    safe_next = next if next.startswith(_ALLOWED_NEXT_PREFIX) else "/"
    await create_token(redis, "oauth_state", {"provider": provider, "next": safe_next}, ttl=settings.oauth_state_ttl_seconds)  # key by state
    # 注：create_token 生成自己的 token；这里改用固定 state → 用 r.set 直接存（见下方实现注解）
    client = oauth.create_client(provider)
    redirect_uri = f"{settings.public_web_url.replace(':3000', ':8000')}/api/auth/oauth/{provider}/callback"
    return await client.authorize_redirect(request, redirect_uri, state=state)

@router.get("/oauth/{provider}/callback")
async def oauth_callback(provider: str, request: Request, response: Response, state: str = "", db=Depends(get_db), redis=Depends(get_redis)):
    meta = await consume_token(redis, "oauth_state", state)
    if not meta or meta["provider"] != provider:
        raise AppError(40011, "登录态校验失败，请重试", status_code=400)
    client = oauth.create_client(provider)
    token = await client.authorize_access_token(request)
    info = token.get("userinfo") or (await client.userinfo(token=token))
    profile = normalize_profile(provider, dict(info))
    user = await upsert_oauth_identity(db, provider, profile)
    ws = AuthService()._build_session(user_id=user.id, user_agent=request.headers.get("user-agent"), ip_address=_client_ip(request))
    db.add(ws); await db.commit()
    _set_session_cookie(response, ws.id)
    redirect = RedirectResponse(url=f"{settings.public_web_url}{meta['next']}", status_code=302)
    _set_session_cookie(redirect, ws.id)
    return redirect
```
> 实现注解：state 需用 state 字符串本身做 key。把 oauth_state 存取改成 `redis.set(f"auth:oauth_state:{state}", json, ex=ttl)` / `redis.get`+`delete`，或给 `auth_tokens` 加 `set_token(r, purpose, key, payload, ttl)` 变体。执行时择一，保持单次。
> authlib 的 `authorize_redirect/authorize_access_token` 默认依赖 starlette session 存 state/nonce。用 Redis 自管时改用 `client.create_authorization_url` + `client.fetch_token`（显式传 state/redirect_uri），不依赖 session。执行时按 authlib 1.3 API 落地，测试用 mock 覆盖。

- [ ] **Step 2: 接通路由**：确认 `dev_router`/`router` 已在 main.py include；新端点同属 `router`，无需额外注册。`from fastapi.responses import RedirectResponse` 补 import。

- [ ] **Step 3: 手动冒烟（dev，console 邮件 + 占位 oauth）**：跑通编译与路由表
Run: `docker exec talealive-backend-1 python -c "from api.auth import router; print([r.path for r in router.routes])"`
Expected: 列表含 `/api/auth/oauth/{provider}/start` 与 `/callback`

- [ ] **Step 4: Commit**
```bash
git add backend/api/auth.py backend/main.py
git commit -m "feat(auth): google/linuxdo oauth start+callback (redis state)"
```

---

## Phase 5 — 前端

### Task 10: 前端注册/验证/重置页 + 登录入口

**Files:**
- Modify: `frontend/stores/auth.ts`（加 register/verifyEmail/forgot/reset/resend actions）
- Modify: `frontend/lib/api.ts` 或就近（调用封装）
- Create: `frontend/app/register/page.tsx`, `frontend/app/verify-email/page.tsx`, `frontend/app/forgot-password/page.tsx`, `frontend/app/reset-password/page.tsx`
- Modify: `frontend/components/auth/LoginModal.tsx`, `frontend/app/login/page.tsx`（加注册入口 + Google 按钮 + 未验证 403 文案 + 重发）
- Modify: `frontend/i18n/zh.json`, `frontend/i18n/en.json`

> 模式参考：完全复用现有登录页/`LoginModal` 的 RHF+zod+视觉与 `lib/api` 封装；不引新库。按钮触摸目标 ≥44px，375px 优先（AGENTS.md）。

- [ ] **Step 1: store actions**（`stores/auth.ts` 仿现有 `login`）
```ts
register: async (email, password, nickname) => apiPost('/api/auth/register', { email, password, nickname }),
verifyEmail: async (token) => { const data = await apiPost('/api/auth/verify-email', { token }); set({ user: data }); },
resendVerification: async (email) => apiPost('/api/auth/resend-verification', { email }),
forgotPassword: async (email) => apiPost('/api/auth/password/forgot', { email }),
resetPassword: async (token, newPassword) => apiPost('/api/auth/password/reset', { token, new_password: newPassword }),
```
（`apiPost` = 现有 `apiFetch` 的 POST 封装；按 `lib/api.ts` 实际命名落地。）

- [ ] **Step 2: 页面**
  - `/register`：邮箱+密码+昵称表单 → 调 register → 成功跳"去邮箱验证"提示（显示邮箱 + 重发按钮）。
  - `/verify-email`：读 `?token=` → useEffect/Query 调 verifyEmail → 成功落 user 并跳首页/发现；失败显示"链接失效"+ 重发入口。
  - `/forgot-password`：邮箱 → 调 forgot → 统一显示"若该邮箱存在，重置邮件已发出"。
  - `/reset-password`：读 `?token=` + 新密码 → 调 reset → 成功跳登录。
  - 全部用 `.lv-t-*` 字号、`var(--lv-*)` 颜色、复用登录页表单样式。

- [ ] **Step 3: 登录入口改造**
  - `LoginModal`/`login`：表单下加"还没账号？去注册"链接；LinuxDo 按钮旁加 Google 按钮 `window.location.href = apiURL('/api/auth/oauth/google/start?next=' + next)`；LinuxDo 按钮 href 改指向真实后端（已存在，现在后端通了）。
  - 登录失败码 `40302` → 显示"请先验证邮箱"+重发按钮（调 resendVerification）。

- [ ] **Step 4: i18n**：`zh.json`/`en.json` auth 段补 register/verify/forgot/reset/resend/unverified 文案键。

- [ ] **Step 5: 构建校验**
Run: `cd frontend && npm run build`
Expected: 构建通过，无类型错误

- [ ] **Step 6: Commit**
```bash
git add frontend/app/register frontend/app/verify-email frontend/app/forgot-password frontend/app/reset-password frontend/components/auth frontend/app/login frontend/stores/auth.ts frontend/lib frontend/i18n
git commit -m "feat(auth): register/verify/reset pages + google button + i18n"
```

---

## Phase 6 — 配置与人工验收

### Task 11: 配置清单 + 端到端人工冒烟

**Files:**
- Modify: `backend/.env`（dev 值）、`backend/.env.example`、`frontend/.env.example`
- Modify: `docs/modules/auth-and-admin.md`（补认证流程文档）

- [ ] **Step 1: dev .env**：`EMAIL_BACKEND=console`、`PUBLIC_WEB_URL=http://localhost:3000`，OAuth 留空（dev 不强测真 OAuth）。`.env.example` 补全所有新键 + 注释。
- [ ] **Step 2: 重建后端容器**（让 env_file 生效，见 image-storage 记忆坑）
Run: `docker compose -p talealive -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate --no-deps backend`
- [ ] **Step 3: 人工冒烟脚本**（console 邮件，token 从后端日志取）
  1. POST /api/auth/register → 200 pending；后端日志见 `[email:console]` + 链接
  2. 未验证 POST /api/auth/password/login → 403 40302
  3. POST /api/auth/verify-email{token} → 200 + set-cookie；GET /api/auth/me → 用户
  4. POST /api/auth/password/forgot → 200；日志见 reset 链接；reset → 200；旧 session 失效、新密码登录成功
- [ ] **Step 4: 文档**：`docs/modules/auth-and-admin.md` 增"注册/验证/重置/OAuth 流程 + 合并不变式 + 配置项"小节。
- [ ] **Step 5: 全量回归**
Run: `docker exec talealive-backend-1 python -m pytest tests/test_auth_tokens.py tests/test_email_service.py tests/test_auth_registration.py tests/test_auth_api.py tests/test_password_reset.py tests/test_oauth_service.py -v`
Expected: 全 PASS
- [ ] **Step 6: Commit**
```bash
git add backend/.env.example frontend/.env.example docs/modules/auth-and-admin.md
git commit -m "docs(auth): config checklist + auth module doc; dev env defaults"
```

---

## 上线前（非本计划执行项，部署时做）
- inkwild.app DNS 配 Resend SPF/DKIM/return-path；prod `EMAIL_BACKEND=resend` + `RESEND_API_KEY`。
- Google Cloud OAuth client + 回调 `https://<api域>/api/auth/oauth/google/callback`；LinuxDo OAuth app 同理。
- prod env：`SESSION_COOKIE_DOMAIN=.inkwild.app`、`PUBLIC_WEB_URL=https://inkwild.app`、各 OAuth client id/secret。
- prod DB 跑 `alembic upgrade head`（verified_at 迁移 + 回填）。

## 风险 / 待实现时确认
- **authlib 1.3 的 state 自管**：Task 9 注解的两点（Redis state key、不依赖 starlette session）在实现时按 authlib 实际 API 落地，测试用 mock 覆盖 callback。
- **LinuxDo 是否返已验证邮箱**：实现 Task 8 `normalize_profile` 时确认其 `/api/user` 字段；若邮箱非已验证，则 LinuxDo 不参与按邮箱合并（仅 (provider,sub) 独立成号）——代码已用 `email_verified` 控制，无需改结构。
