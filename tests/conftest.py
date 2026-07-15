"""Shared test fixtures.

IMPORTANT: The FastAPI lifespan is NOT triggered via context manager
because it shuts down immediately. Instead, startup code runs inline.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from filemaker_gateway.api.deps import init_dependencies
from filemaker_gateway.config.schema import AppConfig, DatabaseConfig, GatewayConfig, ProviderConfig
from filemaker_gateway.main import create_app
from filemaker_gateway.provider.base import LLMProvider, LLMResponse
from filemaker_gateway.session.database import (
    close_database,
    create_tables,
    get_session_factory,
    init_database,
)
from filemaker_gateway.tool.loader import ToolLoader
from filemaker_gateway.tool.registry import ToolRegistry
from filemaker_gateway.tool.stubs.echo import EchoTool


@pytest.fixture
def app_config() -> AppConfig:
    """Minimal app config for testing."""
    return AppConfig(
        gateway=GatewayConfig(
            host="127.0.0.1",
            port=8080,
            api_key="test-api-key",
            provider=ProviderConfig(
                name="deepseek",
                api_key="test-key",
                model="test-model",
            ),
        ),
        database=DatabaseConfig(url="sqlite+aiosqlite:///./data/test.db"),
        system_prompt="You are a test assistant.",
    )


@pytest.fixture
def tool_registry() -> ToolRegistry:
    """Registry with an echo tool for testing."""
    registry = ToolRegistry()
    registry.register(EchoTool())
    return registry


@pytest.fixture
def mock_provider() -> MagicMock:
    """Mock LLM provider that returns a simple text response."""
    provider = MagicMock(spec=LLMProvider)
    provider.chat = AsyncMock(return_value=LLMResponse(
        content="Hello from mock provider!",
        finish_reason="stop",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    ))
    provider.get_default_model.return_value = "test-model"
    return provider


@pytest.fixture
async def app(app_config):
    """Create a fully wired FastAPI test app.

    Runs startup inline (no lifespan context manager) so dependencies
    stay alive throughout the test.
    """
    # Init database
    init_database(app_config.database.url)
    await create_tables()

    # Load tools
    tool_registry = ToolRegistry()
    loader = ToolLoader()
    loader.load(tool_registry)

    # Mock provider
    mock_prov = MagicMock()
    mock_prov.chat = AsyncMock(return_value=LLMResponse(
        content="Test response",
        finish_reason="stop",
        usage={"total_tokens": 10},
    ))
    mock_prov.get_default_model.return_value = app_config.gateway.provider.model or "test"

    # Wire dependencies (replaces what the lifespan would do)
    init_dependencies(app_config, tool_registry, mock_prov)

    # Create the app (its lifespan also tries to init, but deps already set)
    app_instance = create_app(app_config)

    yield app_instance

    await close_database()
