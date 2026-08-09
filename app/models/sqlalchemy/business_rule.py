import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Text, func
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
    severity: Mapped[RuleSeverity] = mapped_column(
        Enum(RuleSeverity, name="rule_severity"), default=RuleSeverity.WARNING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
