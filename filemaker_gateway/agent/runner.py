"""AgentRunner: the core tool-using LLM loop.

Adapted from nanobot's agent/runner.py pattern.

The runner owns the model-facing loop:
1. Send messages to the provider
2. If the model returns tool calls, execute them
3. Feed tool results back to the model
4. Repeat until a final answer or limit is hit

The runner is provider-agnostic and tool-agnostic.
It knows nothing about sessions, REST, or channels.
"""

import json
from copy import deepcopy
from typing import Any

from loguru import logger

from filemaker_gateway.agent.result import AgentRunResult
from filemaker_gateway.agent.spec import AgentRunSpec
from filemaker_gateway.provider.base import ToolCallRequest
from filemaker_gateway.tool.base import ToolResult


class AgentRunner:
    """Execute a tool-capable LLM conversation loop.

    Usage:
        runner = AgentRunner()
        result = await runner.run(spec)
    """

    def __init__(self) -> None:
        pass

    async def run(self, spec: AgentRunSpec) -> AgentRunResult:
        """Execute the agent loop.

        Args:
            spec: Immutable run specification with messages, tools,
                  provider, model, and iteration limits.

        Returns:
            AgentRunResult with final content, all messages, and metadata.
        """
        messages = deepcopy(spec.initial_messages)
        total_usage: dict[str, int] = {}
        tools_used: list[str] = []
        stop_reason = "completed"
        error: str | None = None

        try:
            for iteration in range(spec.max_iterations):
                logger.debug("Runner iteration {}/{}", iteration + 1, spec.max_iterations)

                # Get tool definitions for this turn
                tool_defs = spec.tools.get_definitions() if spec.tools else None

                # Call provider
                response = await spec.provider.chat(
                    messages=messages,
                    model=spec.model,
                    tools=tool_defs,
                    temperature=spec.temperature,
                    max_tokens=spec.max_tokens,
                )

                # Accumulate usage
                for k, v in response.usage.items():
                    total_usage[k] = total_usage.get(k, 0) + v

                # Handle errors
                if response.finish_reason == "error":
                    stop_reason = "error"
                    error = "Provider returned an error"
                    # If we have partial content, use it
                    if response.content:
                        assistant_msg = _make_assistant_message(response.content)
                        messages.append(assistant_msg)
                    break

                # No tool calls — this is the final answer
                if not response.has_tool_calls:
                    content = response.content or ""
                    assistant_msg = _make_assistant_message(content)
                    messages.append(assistant_msg)
                    return AgentRunResult(
                        final_content=content,
                        messages=messages,
                        tools_used=tools_used,
                        usage=total_usage,
                        stop_reason="completed",
                    )

                # Process tool calls
                assistant_msg = _make_tool_call_message(response.tool_calls)
                messages.append(assistant_msg)

                for tc in response.tool_calls:
                    logger.info("Tool call: {} ({})", tc.name, tc.id)

                    # Execute the tool
                    raw_result = await spec.tools.execute(tc.name, tc.arguments)
                    result_str = str(raw_result) if raw_result is not None else ""

                    # Truncate long results
                    if len(result_str) > spec.max_tool_result_chars:
                        result_str = (
                            result_str[: spec.max_tool_result_chars]
                            + f"\n... [truncated, total {len(result_str)} chars]"
                        )

                    # Add tool result message
                    tool_msg = _make_tool_result_message(tc.id, tc.name, result_str)
                    messages.append(tool_msg)

                    if tc.name not in tools_used:
                        tools_used.append(tc.name)

            # Max iterations reached
            else:
                stop_reason = "max_iterations"
                logger.warning(
                    "Max iterations ({}) reached without final answer",
                    spec.max_iterations,
                )
                # Try to get a final response from the last content
                return AgentRunResult(
                    final_content=messages[-1].get("content", "") if messages else None,
                    messages=messages,
                    tools_used=tools_used,
                    usage=total_usage,
                    stop_reason="max_iterations",
                )

        except Exception as e:
            logger.exception("Runner failed with exception")
            stop_reason = "error"
            error = str(e)

        return AgentRunResult(
            final_content=None,
            messages=messages,
            tools_used=tools_used,
            usage=total_usage,
            stop_reason=stop_reason,
            error=error,
        )


def _make_assistant_message(content: str) -> dict[str, Any]:
    return {"role": "assistant", "content": content}


def _make_tool_call_message(tool_calls: list[ToolCallRequest]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            }
            for tc in tool_calls
        ],
    }


def _make_tool_result_message(
    tool_call_id: str, tool_name: str, content: str
) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": content,
    }
