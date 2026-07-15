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

        Returns the most recent N messages as a list of dicts.
        Tool messages include tool_call_id and name for API compatibility.
        """
        repo = SessionRepository(db)
        messages = await repo.get_history(session_key, limit=self._max_history_messages)
        result: list[dict] = []
        for m in messages:
            msg: dict = {"role": m.role, "content": m.content}
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            if m.tool_name:
                msg["name"] = m.tool_name
            result.append(msg)
        return result

    async def save_turn_messages(
        self,
        db: AsyncSession,
        session_key: str,
        user_message: str,
        assistant_content: str,
        tool_messages: list[dict] | None = None,
    ) -> None:
        """Persist all messages from a completed turn.

        Args:
            db: Database session.
            session_key: Session identifier.
            user_message: The user's input text.
            assistant_content: The assistant's final text response.
            tool_messages: Optional list of {"role", "content", "tool_name",
                "tool_call_id"} dicts for tool call/result pairs.
        """
        repo = SessionRepository(db)

        # Save user message
        await repo.add_message(session_key, "user", user_message)

        # Save tool call/result pairs if any
        if tool_messages:
            for tm in tool_messages:
                await repo.add_message(
                    session_key,
                    role=tm["role"],
                    content=tm["content"],
                    tool_name=tm.get("tool_name"),
                    tool_call_id=tm.get("tool_call_id"),
                )

        # Save final assistant response
        await repo.add_message(session_key, "assistant", assistant_content)

        # Update session timestamp
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
