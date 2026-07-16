"""OpenAI-compatible provider implementation.

Handles all providers that use the OpenAI chat completions API format:
DeepSeek, OpenAI, GLM, Gemini (via OpenAI compat endpoint), Ollama, vLLM, etc.
"""

from typing import Any

from loguru import logger
from openai import AsyncOpenAI

from filemaker_gateway.provider.base import LLMProvider, LLMResponse, ToolCallRequest


class OpenAICompatProvider(LLMProvider):
    """Provider for any OpenAI-compatible chat completions API."""

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        default_model: str = "gpt-4o",
        timeout: float = 120.0,
        supports_vision: bool = False,
    ) -> None:
        super().__init__(api_key, api_base, supports_vision=supports_vision)
        self._default_model = default_model

        # AsyncOpenAI client — works with any OpenAI-compatible endpoint
        client_kwargs: dict[str, Any] = {
            "api_key": api_key or "not-needed",  # Some local servers don't need a key
            "timeout": timeout,
            "max_retries": 2,
        }
        if api_base:
            client_kwargs["base_url"] = api_base

        self._client = AsyncOpenAI(**client_kwargs)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a chat completion request using the OpenAI format."""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = tools

        try:
            logger.debug(
                "Provider call: model={}, messages={}, tools={}",
                model,
                len(messages),
                len(tools) if tools else 0,
            )
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error("Provider call failed: {}", e)
            return LLMResponse(
                content=None,
                finish_reason="error",
                usage={},
            )

        choice = response.choices[0]
        finish_reason = choice.finish_reason or "stop"
        message = choice.message

        # Extract tool calls if present
        tool_calls: list[ToolCallRequest] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                # Parse arguments: may be a JSON string or already a dict
                args = tc.function.arguments
                if isinstance(args, str):
                    import json

                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                tool_calls.append(
                    ToolCallRequest(
                        id=tc.id or "",
                        name=tc.function.name,
                        arguments=args if isinstance(args, dict) else {},
                    )
                )

        # Extract reasoning/thinking content if available
        reasoning_content: str | None = None
        if hasattr(message, "reasoning_content") and message.reasoning_content:
            reasoning_content = message.reasoning_content

        # Extract usage
        usage: dict[str, int] = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
                "total_tokens": response.usage.total_tokens or 0,
            }

        return LLMResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            reasoning_content=reasoning_content,
        )

    def get_default_model(self) -> str:
        return self._default_model
