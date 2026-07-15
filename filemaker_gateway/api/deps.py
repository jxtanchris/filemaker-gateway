"""FastAPI dependency injection.

Wires shared components (AgentLoop, SessionManager, etc.) as route dependencies.
"""

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from filemaker_gateway.agent.loop import AgentLoop
from filemaker_gateway.agent.runner import AgentRunner
from filemaker_gateway.config.schema import AppConfig
from filemaker_gateway.provider.base import LLMProvider
from filemaker_gateway.session.database import get_session_factory
from filemaker_gateway.session.manager import SessionManager
from filemaker_gateway.tool.registry import ToolRegistry

# Singletons — initialized once at app startup
_agent_loop: AgentLoop | None = None
_session_manager: SessionManager | None = None
_tool_registry: ToolRegistry | None = None
_provider: LLMProvider | None = None
_app_config: AppConfig | None = None


def init_dependencies(
    config: AppConfig,
    tool_registry: ToolRegistry,
    provider: LLMProvider,
) -> None:
    """Initialize all shared dependencies. Called once at startup."""
    global _agent_loop, _session_manager, _tool_registry, _provider, _app_config

    _app_config = config
    _tool_registry = tool_registry
    _provider = provider
    _session_manager = SessionManager()

    runner = AgentRunner()
    _agent_loop = AgentLoop(
        session_manager=_session_manager,
        tool_registry=tool_registry,
        provider=provider,
        runner=runner,
        system_prompt=config.system_prompt,
        model=config.gateway.provider.model or provider.get_default_model(),
        max_iterations=config.max_iterations,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )


async def get_db() -> AsyncSession:
    """Yield an async database session. Commits on success, rolls back on error."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_loop() -> AgentLoop:
    """Get the singleton AgentLoop."""
    if _agent_loop is None:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies() first.")
    return _agent_loop


def get_session_manager() -> SessionManager:
    """Get the singleton SessionManager."""
    if _session_manager is None:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies() first.")
    return _session_manager


def get_tool_registry() -> ToolRegistry:
    """Get the singleton ToolRegistry."""
    if _tool_registry is None:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies() first.")
    return _tool_registry


def get_config() -> AppConfig:
    """Get the application configuration."""
    if _app_config is None:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies() first.")
    return _app_config
