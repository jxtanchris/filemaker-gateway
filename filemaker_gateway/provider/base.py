"""LLM provider abstract base class and data types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallRequest:
    """A tool call requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider.

    Attributes:
        content: The assistant's text response (may be None if tool calls only).
        tool_calls: Tool calls requested by the model.
        finish_reason: Why the model stopped: "stop", "tool_calls", "length", "error".
        usage: Token usage dict with "prompt_tokens", "completion_tokens", "total_tokens".
        reasoning_content: Thinking/reasoning content (DeepSeek-R1, o1, etc.).
    """

    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """Abstract base for LLM backends.

    All providers implement a standard chat interface.
    Provider-specific initialization (API keys, base URLs)
    is handled by subclasses.
    """

    def __init__(self, api_key: str, api_base: str | None = None) -> None:
        self._api_key = api_key
        self._api_base = api_base

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a chat completion request to the LLM.

        Args:
            messages: List of {"role": "...", "content": "..."} dicts.
            model: Model identifier string.
            tools: Optional list of OpenAI function definitions.
            temperature: Sampling temperature (0.0-2.0).
            max_tokens: Maximum tokens in the response.

        Returns:
            Standardized LLMResponse.
        """
        ...

    @abstractmethod
    def get_default_model(self) -> str:
        """Return the default model for this provider."""
        ...
