from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlalchemy.audit_log import AuditLog


async def log_action(
    session: AsyncSession,
    user_id: int,
    command_text: str,
    module: str,
    decision: str,
    status: str = "success",
    detail: dict[str, Any] | None = None,
) -> None:
    """Best-effort audit write — callers should not let a logging failure
    break the actual feature, so failures are caught and logged here rather
    than left for every call site to remember to guard against (several
    didn't, before this). Commits its own transaction (small, isolated)
    rather than assuming the caller's session/transaction is still open at
    the point this is called, since it's often invoked right after the
    caller already committed its own work."""
    try:
        session.add(
            AuditLog(
                user_id=user_id,
                command_text=command_text[:2000],
                module=module,
                decision=decision,
                status=status,
                detail=detail,
            )
        )
        await session.commit()
    except Exception as exc:
        logger.warning(f"Audit log write failed (module={module}, decision={decision}): {exc}")
