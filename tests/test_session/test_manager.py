"""Tests for SessionManager."""

import os

import pytest

from filemaker_gateway.session.database import (
    close_database,
    create_tables,
    get_session_factory,
    init_database,
)
from filemaker_gateway.session.manager import SessionManager


TEST_DB = "sqlite+aiosqlite:///./data/test_session.db"


@pytest.fixture(autouse=True)
async def setup_db():
    """Set up a clean test database before each test."""
    # Remove old database file for clean state
    db_path = "./data/test_session.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    init_database(TEST_DB)
    await create_tables()
    yield
    await close_database()
    # Clean up
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def session_manager() -> SessionManager:
    return SessionManager()


@pytest.mark.asyncio
async def test_get_or_create_new(session_manager):
    """Should create a new session when one doesn't exist."""
    factory = get_session_factory()
    async with factory() as db:
        s = await session_manager.get_or_create_session(db, "new-session")
        assert s is not None
        assert s.id == "new-session"
        await db.commit()


@pytest.mark.asyncio
async def test_get_or_create_existing(session_manager):
    """Should return existing session."""
    factory = get_session_factory()
    async with factory() as db:
        s1 = await session_manager.get_or_create_session(db, "existing")
        s2 = await session_manager.get_or_create_session(db, "existing")
        assert s1.id == s2.id
        await db.commit()


@pytest.mark.asyncio
async def test_save_and_retrieve_history(session_manager):
    """Should persist messages and retrieve them as context."""
    factory = get_session_factory()
    async with factory() as db:
        await session_manager.save_turn_messages(
            db, "hist-test",
            user_message="Hello",
            assistant_content="Hi there!",
        )
        await db.commit()

        history = await session_manager.get_history_for_context(db, "hist-test")
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Hi there!"


@pytest.mark.asyncio
async def test_save_turn_with_tools(session_manager):
    """Should persist tool messages correctly."""
    factory = get_session_factory()
    async with factory() as db:
        # Session must exist before saving messages
        await session_manager.get_or_create_session(db, "tool-test")
        await db.commit()

        await session_manager.save_turn_messages(
            db, "tool-test",
            user_message="Echo please",
            assistant_content="Done!",
            tool_messages=[
                {"role": "assistant", "content": "...", "tool_name": "echo", "tool_call_id": "1"},
                {"role": "tool", "content": "Echo: test", "tool_name": "echo", "tool_call_id": "1"},
            ],
        )
        await db.commit()

        detail = await session_manager.get_session_detail(db, "tool-test")
        assert detail is not None
        assert len(detail["messages"]) == 4


@pytest.mark.asyncio
async def test_list_sessions(session_manager):
    """Should list sessions ordered by most recent."""
    factory = get_session_factory()
    async with factory() as db:
        await session_manager.get_or_create_session(db, "s1")
        await session_manager.get_or_create_session(db, "s2")
        await db.commit()

        sessions = await session_manager.list_sessions(db)
        assert len(sessions) >= 2


@pytest.mark.asyncio
async def test_delete_session(session_manager):
    """Should delete a session and its messages."""
    factory = get_session_factory()
    async with factory() as db:
        await session_manager.get_or_create_session(db, "to-delete")
        await db.commit()

        deleted = await session_manager.delete_session(db, "to-delete")
        await db.commit()
        assert deleted is True

        detail = await session_manager.get_session_detail(db, "to-delete")
        assert detail is None
