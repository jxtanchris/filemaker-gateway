"""AgentRunResult: output from an agent run."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentRunResult:
    """Result of an AgentRunner run.

    Contains the final message content, all intermediate messages,
    tool usage summary, and stop reason.
    """

    final_content: str | None
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    stop_reason: str = "completed"
    error: str | None = None
