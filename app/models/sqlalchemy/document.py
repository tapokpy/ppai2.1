from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Document(Base):
    """Provenance record for one ingested document (project doc, uploaded
    PDF, or a harvested knowledge-base entry). Chunk text/embeddings stay in
    Chroma only — this table is just the index that backs the "Document"
    admin screen and lets the frontend list/filter without touching Chroma
    for every listing."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(30), index=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding_model: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="ingested")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
