from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProjectFile(Base):
    """A non-CAD file attached to a Project — equipment config/preset
    files per v6 spec 2.2. CAD drawings are NOT stored here: they stay in
    EngineeringDoc (which gained a nullable project_id in this same
    migration) since they already have their own extracted_data/rendering
    pipeline that this table doesn't need to duplicate."""

    __tablename__ = "project_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    file_path: Mapped[str] = mapped_column(String(1024))
    file_name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20), default="config")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
