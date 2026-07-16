"""Tests for AgentLoop vision support in _build()."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from filemaker_gateway.agent.loop import AgentLoop, TurnContext
from filemaker_gateway.agent.runner import AgentRunner
from filemaker_gateway.session.manager import SessionManager
from filemaker_gateway.tool.registry import ToolRegistry
from filemaker_gateway.tool.stubs.echo import EchoTool


class TestAgentLoopVision:

    @pytest.fixture
    def mock_runner(self):
        runner = MagicMock(spec=AgentRunner)
        runner.run = AsyncMock()
        return runner

    @pytest.fixture
    def mock_provider(self):
        from filemaker_gateway.provider.base import LLMProvider
        return MagicMock(spec=LLMProvider)

    @pytest.fixture
    def tool_registry(self):
        r = ToolRegistry()
        r.register(EchoTool())
        return r

    @pytest.fixture
    def mock_session_manager(self):
        sm = MagicMock(spec=SessionManager)
        sm.get_or_create_session = AsyncMock()
        sm.get_history_for_context = AsyncMock(return_value=[])
        sm.save_turn_messages = AsyncMock()
        return sm

    @pytest.mark.asyncio
    async def test_build_without_media_uses_string_content(
        self, mock_session_manager, tool_registry, mock_provider, mock_runner
    ):
        """Without media, _build should create a plain string content message."""
        loop = AgentLoop(
            session_manager=mock_session_manager,
            tool_registry=tool_registry,
            provider=mock_provider,
            runner=mock_runner,
            system_prompt="Test prompt",
        )
        ctx = TurnContext(session_key="s1", user_message="Hello", media=[])
        from sqlalchemy.ext.asyncio import AsyncSession
        mock_db = MagicMock(spec=AsyncSession)

        await loop._resolve(ctx, mock_db)
        await loop._build(ctx)

        user_msg = ctx.initial_messages[-1]
        assert user_msg["role"] == "user"
        assert isinstance(user_msg["content"], str)
        assert user_msg["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_build_with_image_media_uses_vision_format(
        self, mock_session_manager, tool_registry, mock_provider, mock_runner
    ):
        """With base64 image media, _build should use vision content list."""
        mock_provider.supports_vision = True
        loop = AgentLoop(
            session_manager=mock_session_manager,
            tool_registry=tool_registry,
            provider=mock_provider,
            runner=mock_runner,
            system_prompt="Test prompt",
        )
        ctx = TurnContext(
            session_key="s1",
            user_message="What's in this image?",
            media=["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="],
        )
        from sqlalchemy.ext.asyncio import AsyncSession
        mock_db = MagicMock(spec=AsyncSession)

        await loop._resolve(ctx, mock_db)
        await loop._build(ctx)

        user_msg = ctx.initial_messages[-1]
        assert user_msg["role"] == "user"
        assert isinstance(user_msg["content"], list)
        # First part should be the text
        assert user_msg["content"][0] == {"type": "text", "text": "What's in this image?"}
        # Second part should be the image
        assert user_msg["content"][1]["type"] == "image_url"
        assert "base64" in user_msg["content"][1]["image_url"]["url"]

    @pytest.mark.asyncio
    async def test_build_with_non_image_media_uses_text_format(
        self, mock_session_manager, tool_registry, mock_provider, mock_runner
    ):
        """Non-data-URI media URLs should be appended as text references."""
        loop = AgentLoop(
            session_manager=mock_session_manager,
            tool_registry=tool_registry,
            provider=mock_provider,
            runner=mock_runner,
            system_prompt="Test prompt",
        )
        ctx = TurnContext(
            session_key="s1",
            user_message="Analyze this",
            media=["https://example.com/document.pdf"],
        )
        from sqlalchemy.ext.asyncio import AsyncSession
        mock_db = MagicMock(spec=AsyncSession)

        await loop._resolve(ctx, mock_db)
        await loop._build(ctx)

        user_msg = ctx.initial_messages[-1]
        # Non-image URLs are appended as text markers (backward compatible)
        assert "https://example.com/document.pdf" in str(user_msg["content"])

    @pytest.mark.asyncio
    async def test_build_with_mixed_media(
        self, mock_session_manager, tool_registry, mock_provider, mock_runner
    ):
        """Mix of image and non-image media should use vision format for images."""
        mock_provider.supports_vision = True
        loop = AgentLoop(
            session_manager=mock_session_manager,
            tool_registry=tool_registry,
            provider=mock_provider,
            runner=mock_runner,
            system_prompt="Test prompt",
        )
        ctx = TurnContext(
            session_key="s1",
            user_message="Check these",
            media=[
                "data:image/jpeg;base64,/9j/4AAQ==",
                "https://example.com/file.pdf",
            ],
        )
        from sqlalchemy.ext.asyncio import AsyncSession
        mock_db = MagicMock(spec=AsyncSession)

        await loop._resolve(ctx, mock_db)
        await loop._build(ctx)

        user_msg = ctx.initial_messages[-1]
        # Should use vision list format because at least one image is present
        assert isinstance(user_msg["content"], list)
        # First: text
        assert user_msg["content"][0]["type"] == "text"
        # Second: image
        assert user_msg["content"][1]["type"] == "image_url"
        # Third: text reference for non-image URL
        assert user_msg["content"][2]["type"] == "text"
        assert "file.pdf" in user_msg["content"][2]["text"]
