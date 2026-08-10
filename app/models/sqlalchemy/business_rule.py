import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RuleSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class BusinessRule(Base):
    __tablename__ = "business_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_text: Mapped[str] = mapped_column(Text)
    # Structured AND-conditions, e.g. [{"field": "pixel_pitch", "operator": "<", "value": 2.5}].
    # NULL means a legacy free-text rule, matched by substring against the calculation context.
    conditions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    severity: Mapped[RuleSeverity] = mapped_column(
        Enum(RuleSeverity, name="rule_severity"), default=RuleSeverity.WARNING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
