"""SQLAlchemy repository for session and message CRUD operations."""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from filemaker_gateway.session.models import MessageModel, SessionModel


class SessionRepository:
    """Data access layer for sessions and messages."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # --- Session operations ---

    async def get(self, session_id: str) -> SessionModel | None:
        """Get a session by ID."""
        result = await self._db.execute(
            select(SessionModel).where(SessionModel.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_with_messages(self, session_id: str) -> SessionModel | None:
        """Get a session with all messages eagerly loaded."""
        result = await self._db.execute(
            select(SessionModel)
            .where(SessionModel.id == session_id)
            .options(selectinload(SessionModel.messages))
        )
        return result.scalar_one_or_none()

    async def create(self, session_id: str, metadata: dict | None = None) -> SessionModel:
        """Create a new session."""
        session = SessionModel(id=session_id, metadata_json=metadata)
        self._db.add(session)
        await self._db.flush()
        return session

    async def get_or_create(self, session_id: str) -> SessionModel:
        """Get an existing session or create a new one."""
        session = await self.get(session_id)
        if session is None:
            session = await self.create(session_id)
        return session

    async def touch(self, session_id: str) -> None:
        """Update the updated_at timestamp on a session."""
        await self._db.execute(
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(updated_at=datetime.now(timezone.utc))
        )

    async def list_all(
        self, limit: int = 50, offset: int = 0
    ) -> list[SessionModel]:
        """List sessions ordered by most recent first."""
        result = await self._db.execute(
            select(SessionModel)
            .options(selectinload(SessionModel.messages))
            .order_by(SessionModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete(self, session_id: str) -> bool:
        """Delete a session and its messages. Returns True if deleted."""
        session = await self.get(session_id)
        if session is None:
            return False
        await self._db.delete(session)
        await self._db.flush()
        return True

    # --- Message operations ---

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
    ) -> MessageModel:
        """Add a message to a session. Auto-increments sequence number."""
        # Get current max sequence
        result = await self._db.execute(
            select(MessageModel.sequence)
            .where(MessageModel.session_id == session_id)
            .order_by(MessageModel.sequence.desc())
            .limit(1)
        )
        max_seq = result.scalar_one_or_none()
        next_seq = (max_seq or 0) + 1

        msg = MessageModel(
            session_id=session_id,
            sequence=next_seq,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )
        self._db.add(msg)
        await self._db.flush()
        return msg

    async def get_history(
        self, session_id: str, limit: int | None = None
    ) -> list[MessageModel]:
        """Get message history for a session, most recent last."""
        stmt = (
            select(MessageModel)
            .where(MessageModel.session_id == session_id)
            .order_by(MessageModel.sequence.asc())
        )
        if limit is not None:
            # Get the last N messages
            subq = (
                select(MessageModel.id)
                .where(MessageModel.session_id == session_id)
                .order_by(MessageModel.sequence.desc())
                .limit(limit)
                .subquery()
            )
            stmt = (
                select(MessageModel)
                .where(MessageModel.id.in_(select(subq.c.id)))
                .order_by(MessageModel.sequence.asc())
            )

        result = await self._db.execute(stmt)
        return list(result.scalars().all())
