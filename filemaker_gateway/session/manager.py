"""SessionManager: business logic for session and message management."""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from filemaker_gateway.session.models import MessageModel, SessionModel
from filemaker_gateway.session.repository import SessionRepository


@dataclass
class SessionInfo:
    """Lightweight session summary returned by the manager."""

    id: str
    created_at: str
    updated_at: str
    message_count: int
    metadata: dict | None = None


class SessionManager:
    """Manages conversation sessions and message history.

    Wraps SessionRepository with business logic like
    history truncation, token budgeting, and session listing.
    Provides a clean interface for AgentLoop and API layer.
    """

    def __init__(self, max_history_messages: int = 100) -> None:
        self._max_history_messages = max_history_messages

    async def get_or_create_session(
        self, db: AsyncSession, session_key: str
    ) -> SessionModel:
        """Resolve or create a session by key."""
        repo = SessionRepository(db)
        return await repo.get_or_create(session_key)

    async def get_history_for_context(
        self, db: AsyncSession, session_key: str
    ) -> list[dict]:
        """Get message history formatted for LLM context.

        Returns the most recent N messages as simple role/content dicts.
        Tool calls are transient and not stored in history.
        """
        repo = SessionRepository(db)
        messages = await repo.get_history(session_key, limit=self._max_history_messages)
        return [{"role": m.role, "content": m.content} for m in messages]

    async def save_turn_messages(
        self,
        db: AsyncSession,
        session_key: str,
        user_message: str,
        assistant_content: str,
    ) -> None:
        """Persist user message and assistant response for a completed turn.

        Only stores the user/assistant conversation pair.
        Intermediate tool calls are transient and not persisted.
        """
        repo = SessionRepository(db)

        await repo.add_message(session_key, "user", user_message)
        await repo.add_message(session_key, "assistant", assistant_content)
        await repo.touch(session_key)

    async def list_sessions(
        self,
        db: AsyncSession,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SessionInfo]:
        """List sessions ordered by most recent activity."""
        repo = SessionRepository(db)
        sessions = await repo.list_all(limit=limit, offset=offset)
        return [
            SessionInfo(
                id=s.id,
                created_at=s.created_at.isoformat(),
                updated_at=s.updated_at.isoformat(),
                message_count=s.message_count,
                metadata=s.metadata_json,
            )
            for s in sessions
        ]

    async def get_session_detail(
        self, db: AsyncSession, session_key: str
    ) -> dict | None:
        """Get full session detail with message history."""
        repo = SessionRepository(db)
        session = await repo.get_with_messages(session_key)
        if session is None:
            return None

        messages = [
            {
                "role": m.role,
                "content": m.content,
                "tool_name": m.tool_name,
                "created_at": m.created_at.isoformat(),
            }
            for m in (session.messages or [])
        ]

        return {
            "id": session.id,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "messages": messages,
            "metadata": session.metadata_json,
        }

    async def delete_session(
        self, db: AsyncSession, session_key: str
    ) -> bool:
        """Delete a session and all its messages."""
        repo = SessionRepository(db)
        return await repo.delete(session_key)
