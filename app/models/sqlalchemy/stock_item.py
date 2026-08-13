from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StockItem(Base):
    """One line of stock in one Cell. No batch/serial/reservation
    fields per v6 spec 2.1 — just a running quantity per (cell, item_name).
    item_type is a free-form category string ('module'/'psu'/'card'/'other')
    used by the BOM-reconciliation engine (Phase 3) to match against
    LedBomResult line items, not an enum — new equipment categories
    shouldn't need a migration."""

    __tablename__ = "stock_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    cell_id: Mapped[int] = mapped_column(ForeignKey("cells.id"))
    item_name: Mapped[str] = mapped_column(String(255))
    item_type: Mapped[str] = mapped_column(String(30), default="other")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit: Mapped[str] = mapped_column(String(20), default="шт")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
