from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Project(Base):
    """A workspace grouping data around one customer object — what
    LOKI_WAREHOUSE_ECOSYSTEM_SPEC_v6.md calls "кабинет проекта". Named
    Project (not Cabinet) in code and in bot-facing text on purpose: "кабинет"
    already means the physical LED panel unit in this domain (see
    ARCHITECTURE.md's diagnostic-helper section) — reusing it here for a
    project workspace would collide.

    bom_data holds the most recently calculated LedBomResult (Phase 3) for
    this project's screen — one BOM per project, recalculated in place
    rather than versioned, since "умный ревизор"/"автосборка" always want
    the latest design, not history."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    customer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bom_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
