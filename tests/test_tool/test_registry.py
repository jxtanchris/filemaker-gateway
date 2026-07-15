"""Tests for ToolRegistry and Tool system."""

import pytest

from filemaker_gateway.tool.base import ToolResult
from filemaker_gateway.tool.loader import ToolLoader
from filemaker_gateway.tool.registry import ToolRegistry
from filemaker_gateway.tool.stubs.echo import EchoTool


@pytest.fixture
def registry() -> ToolRegistry:
    r = ToolRegistry()
    r.register(EchoTool())
    return r


def test_register_and_get(registry):
    """Should register and retrieve tools by name."""
    assert registry.has("echo")
    tool = registry.get("echo")
    assert tool is not None
    assert tool.name == "echo"


def test_get_definitions(registry):
    """Should return OpenAI function schemas."""
    defs = registry.get_definitions()
    assert len(defs) == 1
    assert defs[0]["type"] == "function"
    assert defs[0]["function"]["name"] == "echo"


@pytest.mark.asyncio
async def test_execute_tool(registry):
    """Should execute a registered tool."""
    result = await registry.execute("echo", {"message": "hello"})
    assert "Echo: hello" in result


@pytest.mark.asyncio
async def test_execute_unknown_tool(registry):
    """Should return error for unknown tools."""
    result = await registry.execute("nonexistent", {})
    assert "Unknown tool" in result


@pytest.mark.asyncio
async def test_execute_validation_error(registry):
    """Should validate required parameters."""
    result = await registry.execute("echo", {})  # missing required 'message'
    assert "Missing required parameter" in result


def test_tool_result():
    """ToolResult should carry is_error flag."""
    ok = ToolResult("success")
    assert str(ok) == "success"
    assert not ok.is_error

    err = ToolResult.error("failed")
    assert str(err) == "failed"
    assert err.is_error


def test_tool_auto_discovery():
    """ToolLoader should discover all tool classes in the tool package."""
    registry = ToolRegistry()
    loader = ToolLoader()
    names = loader.load(registry)
    # Should find: echo, filemaker_query, filemaker_record, filemaker_script,
    # filemaker_layout, ocr, sql_query
    assert len(names) >= 6
    assert "echo" in names
    assert "filemaker_query" in names
    assert "ocr" in names
    assert "sql_query" in names


def test_tool_schema_format():
    """Tool.to_schema() should produce valid OpenAI function schema."""
    tool = EchoTool()
    schema = tool.to_schema()
    assert schema["type"] == "function"
    func = schema["function"]
    assert func["name"] == "echo"
    assert "description" in func
    assert "parameters" in func
    assert func["parameters"]["type"] == "object"


def test_loader_with_kwargs_injection():
    """ToolLoader.load() should pass matching kwargs to Tool constructors."""
    registry = ToolRegistry()
    loader = ToolLoader()

    # EchoTool.__init__ only takes self — extra kwargs should be ignored
    names = loader.load(registry, fm_client="fake_client", provider="fake_provider")
    assert "echo" in names

    # EchoTool should still work normally
    tool = registry.get("echo")
    assert tool is not None


def test_loader_ignores_unmatched_kwargs():
    """Should not fail when passing kwargs that no tool accepts."""
    registry = ToolRegistry()
    loader = ToolLoader()
    # All current tools only accept self — these kwargs should be silently ignored
    names = loader.load(registry, unknown_kwarg=42, another_one="test")
    assert len(names) >= 6
