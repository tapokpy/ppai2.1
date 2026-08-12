from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    prompt: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20))
    context_used: Mapped[bool] = mapped_column(Boolean, default=False)
    # Structured line items (from a calculator result) for DOCX/XLSX export.
    # NULL falls back to exporting the raw prompt/response as a single row.
    structured_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # RAG retrieval details (max_score, retrieved chunks) captured when source == "rag".
    rag_debug: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
