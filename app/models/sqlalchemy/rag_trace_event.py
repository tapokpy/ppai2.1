from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RagTraceEvent(Base):
    """One step of a query's retrieval/generation pipeline (query_embedded,
    retrieval_started, retrieval_results, chunks_selected, context_built,
    llm_called, answer_generated) — ordered by `seq` within a `trace_id`.
    Powers the "Финальный ответ" trace timeline screen; the actual chunk
    text referenced in `payload` snippets is never duplicated here."""

    __tablename__ = "rag_trace_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    event_name: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
