"""SQLAlchemy ORM models for sessions and messages."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class SessionModel(Base):
    """A conversation session identified by a session key."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    messages: Mapped[list["MessageModel"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="MessageModel.sequence",
    )

    @property
    def message_count(self) -> int:
        """Return the number of loaded messages, or 0 if not loaded.

        In async SQLAlchemy, lazy loading of relationships fails.
        This property only reports count from eagerly-loaded messages.
        Use SessionRepository.get_with_messages() to get a fully-loaded session.
        """
        try:
            from sqlalchemy import inspect as sa_inspect
            state = sa_inspect(self)
            # Check if the 'messages' relationship is loaded
            if not state.attrs.messages.loaded_value:
                return 0
            return len(state.attrs.messages.loaded_value)
        except Exception:
            return 0


class MessageModel(Base):
    """A single message within a session."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str] = mapped_column(String(32), default="user")
    content: Mapped[str] = mapped_column(Text, default="")
    tool_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    session: Mapped["SessionModel"] = relationship(back_populates="messages")
