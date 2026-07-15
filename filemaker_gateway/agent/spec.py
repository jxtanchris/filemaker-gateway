"""AgentRunSpec: parameters for an agent run."""

from dataclasses import dataclass, field
from typing import Any

from filemaker_gateway.provider.base import LLMProvider
from filemaker_gateway.tool.registry import ToolRegistry


@dataclass
class AgentRunSpec:
    """Immutable specification for a single agent run.

    Created by AgentLoop, consumed by AgentRunner.
    """

    initial_messages: list[dict[str, Any]]
    tools: ToolRegistry
    provider: LLMProvider
    model: str
    max_iterations: int = 10
    max_tool_result_chars: int = 8000
    temperature: float = 0.7
    max_tokens: int = 4096
    session_key: str | None = None
