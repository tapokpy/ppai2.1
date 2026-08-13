from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    """What Loki actually did, for the admin panel — distinct from
    ActivityLog (a per-message "user was active" summary, no module/
    decision/status fields) and RagTraceEvent (RAG-pipeline-internal steps
    tied 1:1 to a Message row). One row per meaningful action: the
    command/prompt that came in, which module handled it, what it decided
    to do, and whether that succeeded."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    command_text: Mapped[str] = mapped_column(String(2000))
    module: Mapped[str] = mapped_column(String(50), index=True)
    decision: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), index=True)  # 'success' | 'error'
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
