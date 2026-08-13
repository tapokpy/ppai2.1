from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ShowroomMedia(Base):
    """One downloaded media file in the local showroom library
    (D:/Pappai_Media on the host, mounted into the bot container at
    settings.MEDIA_STORAGE_PATH). last_used drives LRU cleanup when the
    disk quota (settings.MEDIA_STORAGE_QUOTA_GB) is exceeded; is_pinned
    exempts a file from that cleanup."""

    __tablename__ = "showroom_media"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(1024))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    last_used: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
