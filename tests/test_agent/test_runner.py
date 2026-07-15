"""Tests for AgentRunner."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from filemaker_gateway.agent.runner import AgentRunner
from filemaker_gateway.agent.spec import AgentRunSpec
from filemaker_gateway.provider.base import LLMResponse, ToolCallRequest
from filemaker_gateway.tool.registry import ToolRegistry
from filemaker_gateway.tool.stubs.echo import EchoTool


@pytest.fixture
def runner() -> AgentRunner:
    return AgentRunner()


@pytest.mark.asyncio
async def test_simple_chat_no_tools(runner, mock_provider, tool_registry):
    """Runner should return the provider's response directly when no tool calls."""
    spec = AgentRunSpec(
        initial_messages=[{"role": "user", "content": "Hi"}],
        tools=tool_registry,
        provider=mock_provider,
        model="test",
    )
    result = await runner.run(spec)
    assert result.final_content == "Hello from mock provider!"
    assert result.stop_reason == "completed"
    assert result.tools_used == []


@pytest.mark.asyncio
async def test_chat_with_tool_calls(runner):
    """Runner should detect tool calls, execute tools, and continue."""
    registry = ToolRegistry()
    registry.register(EchoTool())

    provider = MagicMock()
    provider.chat = AsyncMock(side_effect=[
        # First call: model requests echo tool
        LLMResponse(
            content=None,
            tool_calls=[ToolCallRequest(id="1", name="echo", arguments={"message": "test"})],
            finish_reason="tool_calls",
            usage={"total_tokens": 10},
        ),
        # Second call: model returns final answer after tool result
        LLMResponse(
            content="The echo tool worked!",
            finish_reason="stop",
            usage={"total_tokens": 15},
        ),
    ])
    provider.get_default_model.return_value = "test"

    spec = AgentRunSpec(
        initial_messages=[{"role": "user", "content": "echo test"}],
        tools=registry,
        provider=provider,
        model="test",
    )

    result = await runner.run(spec)
    assert result.final_content == "The echo tool worked!"
    assert "echo" in result.tools_used
    assert result.stop_reason == "completed"
    assert len(result.messages) == 4  # user + assistant(tc) + tool + assistant(final)


@pytest.mark.asyncio
async def test_max_iterations_exceeded(runner, tool_registry):
    """Runner should stop when max_iterations is reached."""
    provider = MagicMock()
    # Always return tool calls — this will loop forever
    provider.chat = AsyncMock(return_value=LLMResponse(
        content=None,
        tool_calls=[ToolCallRequest(id="1", name="echo", arguments={"message": "loop"})],
        finish_reason="tool_calls",
        usage={"total_tokens": 10},
    ))
    provider.get_default_model.return_value = "test"

    spec = AgentRunSpec(
        initial_messages=[{"role": "user", "content": "loop"}],
        tools=tool_registry,
        provider=provider,
        model="test",
        max_iterations=3,
    )

    result = await runner.run(spec)
    assert result.stop_reason == "max_iterations"
    assert result.tools_used == ["echo"]


@pytest.mark.asyncio
async def test_provider_error(runner, tool_registry):
    """Runner should handle provider errors gracefully."""
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=LLMResponse(
        content=None,
        finish_reason="error",
    ))
    provider.get_default_model.return_value = "test"

    spec = AgentRunSpec(
        initial_messages=[{"role": "user", "content": "Hi"}],
        tools=tool_registry,
        provider=provider,
        model="test",
    )

    result = await runner.run(spec)
    assert result.stop_reason == "error"
    assert result.error is not None
