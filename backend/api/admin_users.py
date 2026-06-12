from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_admin_user, get_db
from models.draft import ScriptDraft, WorldDraft
from models.game import GameSession, TokenUsage
from models.script import Script
from models.user import AuthIdentity, User
from models.world import World
from services.audit_service import record_admin_action
from utils import serialize_utc_datetime

router = APIRouter(
    prefix="/api/admin/users",
    tags=["admin-users"],
)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _serialize_user_list_item(
    u: User,
    identities: list[AuthIdentity],
    drafts: int,
    pub_worlds: int,
    pub_scripts: int,
) -> dict:
    verified_at_values = [
        ident.verified_at for ident in identities if ident.verified_at is not None
    ]
    first_verified_at = min(verified_at_values) if verified_at_values else None
    return {
        "id": u.id,
        "nickname": u.nickname,
        "avatar_url": u.avatar_url,
        "status": u.status,
        "is_admin": u.is_admin,
        "can_create": u.can_create,
        "is_verified": first_verified_at is not None,
        "verified_at": serialize_utc_datetime(first_verified_at),
        "created_at": serialize_utc_datetime(u.created_at),
        "last_login_at": serialize_utc_datetime(u.last_login_at),
        "identities": [
            {
                "provider": ident.provider,
                "email": ident.email,
                "phone": ident.phone,
                "verified_at": serialize_utc_datetime(ident.verified_at),
            }
            for ident in identities
        ],
        "drafts_count": drafts,
        "published_worlds_count": pub_worlds,
        "published_scripts_count": pub_scripts,
    }


# ────────────── GET /list ──────────────
@router.get("")
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    q: str | None = Query(None, description="搜索 nickname / id / email"),
    permission: str = Query("all", description="all|admin|can_create|no_perm"),
    status: str = Query("all", description="all|active|banned"),
    verified: str = Query("all", description="all|verified|unverified"),
    order_by: str = Query(
        "created_at", description="created_at|last_login_at"
    ),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    filters = []
    if q:
        like = f"%{q.strip()}%"
        identity_match = select(AuthIdentity.user_id).where(
            AuthIdentity.email.ilike(like)
        )
        filters.append(
            or_(
                User.nickname.ilike(like),
                User.id == q.strip(),
                User.id.in_(identity_match),
            )
        )
    if permission == "admin":
        filters.append(User.is_admin.is_(True))
    elif permission == "can_create":
        filters.append(User.can_create.is_(True))
    elif permission == "no_perm":
        filters.append(User.is_admin.is_(False))
        filters.append(User.can_create.is_(False))
    if status != "all":
        filters.append(User.status == status)
    verified_user_ids = (
        select(AuthIdentity.user_id)
        .where(AuthIdentity.verified_at.is_not(None))
        .distinct()
    )
    if verified == "verified":
        filters.append(User.id.in_(verified_user_ids))
    elif verified == "unverified":
        filters.append(User.id.not_in(verified_user_ids))

    order_col = (
        User.last_login_at if order_by == "last_login_at" else User.created_at
    )

    count_stmt = select(func.count()).select_from(User)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = int((await db.execute(count_stmt)).scalar_one())

    list_stmt = select(User)
    if filters:
        list_stmt = list_stmt.where(*filters)
    list_stmt = (
        list_stmt.order_by(desc(order_col))
        .offset((page - 1) * limit)
        .limit(limit)
    )
    users = (await db.execute(list_stmt)).scalars().all()
    user_ids = [u.id for u in users]

    identities_map: dict[str, list[AuthIdentity]] = {}
    drafts_count: dict[str, int] = {}
    pub_worlds_count: dict[str, int] = {}
    pub_scripts_count: dict[str, int] = {}

    if user_ids:
        idents = (
            await db.execute(
                select(AuthIdentity).where(AuthIdentity.user_id.in_(user_ids))
            )
        ).scalars().all()
        for ident in idents:
            identities_map.setdefault(ident.user_id, []).append(ident)

        # 草稿 = world_drafts + script_drafts (合并计数)
        wd_rows = (
            await db.execute(
                select(WorldDraft.created_by_user_id, func.count())
                .where(WorldDraft.created_by_user_id.in_(user_ids))
                .group_by(WorldDraft.created_by_user_id)
            )
        ).all()
        sd_rows = (
            await db.execute(
                select(ScriptDraft.created_by_user_id, func.count())
                .where(ScriptDraft.created_by_user_id.in_(user_ids))
                .group_by(ScriptDraft.created_by_user_id)
            )
        ).all()
        for uid, c in wd_rows:
            drafts_count[uid] = drafts_count.get(uid, 0) + int(c)
        for uid, c in sd_rows:
            drafts_count[uid] = drafts_count.get(uid, 0) + int(c)

        wrows = (
            await db.execute(
                select(World.created_by_user_id, func.count())
                .where(
                    World.created_by_user_id.in_(user_ids),
                    World.status == "published",
                )
                .group_by(World.created_by_user_id)
            )
        ).all()
        for uid, c in wrows:
            pub_worlds_count[uid] = int(c)

        srows = (
            await db.execute(
                select(Script.created_by_user_id, func.count())
                .where(
                    Script.created_by_user_id.in_(user_ids),
                    Script.is_published.is_(True),
                )
                .group_by(Script.created_by_user_id)
            )
        ).all()
        for uid, c in srows:
            pub_scripts_count[uid] = int(c)

    items = [
        _serialize_user_list_item(
            u,
            identities_map.get(u.id, []),
            drafts_count.get(u.id, 0),
            pub_worlds_count.get(u.id, 0),
            pub_scripts_count.get(u.id, 0),
        )
        for u in users
    ]

    verified_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(User)
                .where(User.id.in_(verified_user_ids))
            )
        ).scalar_one()
    )
    unverified_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(User)
                .where(User.id.not_in(verified_user_ids))
            )
        ).scalar_one()
    )

    # Top-level summary counts (global, not just this page)
    summary = {
        "total": total,
        "verified_count": verified_count,
        "unverified_count": unverified_count,
        "admin_count": int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(User)
                    .where(User.is_admin.is_(True))
                )
            ).scalar_one()
        ),
        "can_create_count": int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(User)
                    .where(User.can_create.is_(True))
                )
            ).scalar_one()
        ),
        "banned_count": int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(User)
                    .where(User.status == "banned")
                )
            ).scalar_one()
        ),
    }

    return {
        "code": 0,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
            "summary": summary,
        },
        "message": "ok",
    }


# ────────────── GET /:id ──────────────
@router.get("/{user_id}")
async def get_user_detail(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    identities = (
        (
            await db.execute(
                select(AuthIdentity)
                .where(AuthIdentity.user_id == user_id)
                .order_by(AuthIdentity.created_at.asc())
            )
        ).scalars().all()
    )

    drafts_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(WorldDraft)
                .where(WorldDraft.created_by_user_id == user_id)
            )
        ).scalar_one()
    ) + int(
        (
            await db.execute(
                select(func.count())
                .select_from(ScriptDraft)
                .where(ScriptDraft.created_by_user_id == user_id)
            )
        ).scalar_one()
    )
    pub_worlds = int(
        (
            await db.execute(
                select(func.count())
                .select_from(World)
                .where(
                    World.created_by_user_id == user_id,
                    World.status == "published",
                )
            )
        ).scalar_one()
    )
    pub_scripts = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Script)
                .where(
                    Script.created_by_user_id == user_id,
                    Script.is_published.is_(True),
                )
            )
        ).scalar_one()
    )

    # 最近 5 个 session + 总成本
    session_cost = func.coalesce(func.sum(TokenUsage.cost_cents), 0).label(
        "cost"
    )
    session_rows = (
        await db.execute(
            select(
                GameSession.id,
                GameSession.world_id,
                GameSession.rounds_played,
                GameSession.last_played_at,
                GameSession.status,
                World.name.label("world_name"),
                session_cost,
            )
            .join(World, World.id == GameSession.world_id, isouter=True)
            .join(
                TokenUsage,
                TokenUsage.session_id == GameSession.id,
                isouter=True,
            )
            .where(GameSession.user_id == user_id)
            .group_by(
                GameSession.id,
                GameSession.world_id,
                GameSession.rounds_played,
                GameSession.last_played_at,
                GameSession.status,
                World.name,
            )
            .order_by(desc(GameSession.last_played_at))
            .limit(5)
        )
    ).all()

    # Lifetime token cost
    lifetime_cost = int(
        (
            await db.execute(
                select(func.coalesce(func.sum(TokenUsage.cost_cents), 0))
                .join(
                    GameSession, GameSession.id == TokenUsage.session_id
                )
                .where(GameSession.user_id == user_id)
            )
        ).scalar_one()
    )

    return {
        "code": 0,
        "data": {
            **_serialize_user_list_item(
                user, identities, drafts_count, pub_worlds, pub_scripts
            ),
            "lifetime_cost_cents": lifetime_cost,
            "recent_sessions": [
                {
                    "id": r.id,
                    "world_id": r.world_id,
                    "world_name": r.world_name,
                    "rounds_played": int(r.rounds_played or 0),
                    "status": r.status,
                    "last_played_at": serialize_utc_datetime(r.last_played_at),
                    "cost_cents": int(r.cost),
                }
                for r in session_rows
            ],
        },
        "message": "ok",
    }


# ────────────── PATCH /:id ──────────────
class UpdateUserRequest(BaseModel):
    is_admin: bool | None = None
    can_create: bool | None = None
    status: str | None = None  # "active" | "banned"


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    changes: dict[str, dict] = {}

    if payload.is_admin is not None and payload.is_admin != user.is_admin:
        if admin.id == user.id and payload.is_admin is False:
            raise HTTPException(
                status_code=400, detail="不能撤销自己的 admin 权限"
            )
        changes["is_admin"] = {"from": user.is_admin, "to": payload.is_admin}
        user.is_admin = payload.is_admin

    if (
        payload.can_create is not None
        and payload.can_create != user.can_create
    ):
        changes["can_create"] = {
            "from": user.can_create,
            "to": payload.can_create,
        }
        user.can_create = payload.can_create

    if payload.status is not None and payload.status != user.status:
        if payload.status not in {"active", "banned"}:
            raise HTTPException(
                status_code=400, detail="status 必须是 active 或 banned"
            )
        if admin.id == user.id and payload.status == "banned":
            raise HTTPException(status_code=400, detail="不能封禁自己")
        changes["status"] = {"from": user.status, "to": payload.status}
        user.status = payload.status

    if not changes:
        return {
            "code": 0,
            "data": {"id": user.id, "changes": {}},
            "message": "无变更",
        }

    await record_admin_action(
        db,
        admin_user=admin,
        action="user.update",
        resource_type="user",
        resource_id=user.id,
        payload={"changes": changes},
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    await db.commit()

    return {
        "code": 0,
        "data": {"id": user.id, "changes": changes},
        "message": "ok",
    }
