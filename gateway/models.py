"""
Single SQLAlchemy model that mirrors the old `browser_sessions` table.
Additional columns?  Add them here once and they’ll migrate automatically on
next start (for simple additions; for complex DDL use Alembic later).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped

from db import Base


class BrowserSession(Base):
    __tablename__ = "browser_sessions"

    session_id: Mapped[uuid.UUID] = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[str | None] = Column(Text, nullable=True)
    worker_id: Mapped[str] = Column(Text, nullable=False)

    created_at: Mapped[datetime] = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        nullable=False,
    )
    last_active_at: Mapped[datetime] = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = Column(DateTime(timezone=True))
    status: Mapped[str] = Column(Text, default="active", nullable=False)
