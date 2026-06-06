from sqlalchemy.ext.asyncio import AsyncSession

from models.audit_log import AdminAuditLog
from models.user import User


async def record_admin_action(
    db: AsyncSession,
    *,
    admin_user: User,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    payload: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AdminAuditLog:
    log = AdminAuditLog(
        admin_user_id=admin_user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=payload or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log)
    return log
