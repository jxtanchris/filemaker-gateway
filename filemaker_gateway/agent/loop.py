"""AgentLoop: turn orchestrator for the FileMaker Gateway.

Adapted from nanobot's agent/loop.py pattern.

The AgentLoop owns the channel-facing turn lifecycle:
1. RESOLVE — look up or create session, load history
2. BUILD   — construct messages from system prompt + history + user message
3. RUN     — delegate to AgentRunner
4. SAVE    — persist all messages to session
5. RESPOND — build the API response payload

The loop does NOT interact with providers or tools directly.
That's the runner's responsibility.
"""

import json
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from filemaker_gateway.agent.result import AgentRunResult
from filemaker_gateway.agent.runner import AgentRunner
from filemaker_gateway.agent.spec import AgentRunSpec
from filemaker_gateway.provider.base import LLMProvider
from filemaker_gateway.session.manager import SessionManager
from filemaker_gateway.tool.registry import ToolRegistry


class TurnState(Enum):
    """States in the turn processing state machine."""
    RESOLVE = auto()
    BUILD = auto()
    RUN = auto()
    SAVE = auto()
    RESPOND = auto()
    DONE = auto()


@dataclass
class TurnContext:
    """Mutable context that flows through the state machine."""
    session_key: str
    user_message: str
    media: list[str] = field(default_factory=list)

    # Populated during processing
    history: list[dict[str, Any]] = field(default_factory=list)
    initial_messages: list[dict[str, Any]] = field(default_factory=list)
    run_result: AgentRunResult | None = None

    # Final output
    answer: str = ""
    thinking: str | None = None
    tool_calls_meta: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = "completed"


@dataclass
class TurnResult:
    """Final output from a completed turn."""
    answer: str
    thinking: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    session: str = ""
    stop_reason: str = "completed"
    error: str | None = None


class AgentLoop:
    """Turn orchestrator.

    Resolves sessions, builds context, delegates to the runner,
    persists results, and builds the API response.

    Usage:
        loop = AgentLoop(session_manager, tool_registry, provider, runner)
        result = await loop.process_turn("session-1", "Hello!")
    """

    def __init__(
        self,
        session_manager: SessionManager,
        tool_registry: ToolRegistry,
        provider: LLMProvider,
        runner: AgentRunner,
        system_prompt: str | None = None,
        model: str = "deepseek-chat",
        max_tool_result_chars: int = 8000,
        max_iterations: int = 10,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> None:
        self._session_manager = session_manager
        self._tool_registry = tool_registry
        self._provider = provider
        self._runner = runner
        self._system_prompt = system_prompt or ""
        self._model = model
        self._max_tool_result_chars = max_tool_result_chars
        self._max_iterations = max_iterations
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def process_turn(
        self,
        db: AsyncSession,
        session_key: str,
        user_message: str,
        media: list[str] | None = None,
    ) -> TurnResult:
        """Process a single chat turn from start to finish.

        Args:
            db: Active database session.
            session_key: Session identifier.
            user_message: The user's message text.
            media: Optional list of media URLs/attachments.

        Returns:
            TurnResult with answer, thinking, tool_calls metadata.
        """
        ctx = TurnContext(
            session_key=session_key,
            user_message=user_message,
            media=media or [],
        )

        state = TurnState.RESOLVE
        while state != TurnState.DONE:
            logger.debug("AgentLoop state: {}", state.name)
            state = await self._step(state, ctx, db)

        return TurnResult(
            answer=ctx.answer,
            thinking=ctx.thinking,
            tool_calls=ctx.tool_calls_meta,
            session=ctx.session_key,
            stop_reason=ctx.stop_reason,
            error=ctx.run_result.error if ctx.run_result else None,
        )

    async def _step(
        self,
        state: TurnState,
        ctx: TurnContext,
        db: AsyncSession,
    ) -> TurnState:
        """Execute one state transition."""
        match state:
            case TurnState.RESOLVE:
                return await self._resolve(ctx, db)
            case TurnState.BUILD:
                return await self._build(ctx)
            case TurnState.RUN:
                return await self._run(ctx)
            case TurnState.SAVE:
                return await self._save(ctx, db)
            case TurnState.RESPOND:
                return self._respond(ctx)
            case _:
                return TurnState.DONE

    # --- State handlers ---

    async def _resolve(self, ctx: TurnContext, db: AsyncSession) -> TurnState:
        """Resolve or create session, load message history."""
        session = await self._session_manager.get_or_create_session(
            db, ctx.session_key
        )
        ctx.history = await self._session_manager.get_history_for_context(
            db, ctx.session_key
        )
        logger.info(
            "Session '{}' resolved: {} history messages",
            ctx.session_key,
            len(ctx.history),
        )
        return TurnState.BUILD

    async def _build(self, ctx: TurnContext) -> TurnState:
        """Build the initial_messages list for the runner.

        Supports vision format: when ctx.media contains data:image URLs,
        constructs a content list with text + image_url blocks.
        Non-image media URLs are appended as text references.
        """
        messages: list[dict[str, Any]] = []

        # System prompt
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})

        # History (previous turns)
        messages.extend(ctx.history)

        # Current user message — support vision format when images are attached
        image_media = [m for m in ctx.media if m.startswith("data:image")]
        other_media = [m for m in ctx.media if not m.startswith("data:image")]

        if image_media:
            # Build vision-compatible content list
            content: list[dict[str, Any]] = [
                {"type": "text", "text": ctx.user_message}
            ]
            for url in image_media:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": url},
                })
            # Non-image URLs are included as text references
            if other_media:
                refs = "\n".join(f"[media: {url}]" for url in other_media)
                content.append({"type": "text", "text": refs})

            messages.append({"role": "user", "content": content})
        else:
            # Plain text format (backward compatible)
            user_content = ctx.user_message
            if other_media:
                media_str = "\n".join(f"[media: {url}]" for url in other_media)
                user_content = f"{media_str}\n{user_content}"
            messages.append({"role": "user", "content": user_content})

        ctx.initial_messages = messages
        logger.debug("Built {} initial messages", len(messages))
        return TurnState.RUN

    async def _run(self, ctx: TurnContext) -> TurnState:
        """Delegate to AgentRunner."""
        spec = AgentRunSpec(
            initial_messages=ctx.initial_messages,
            tools=self._tool_registry,
            provider=self._provider,
            model=self._model,
            max_iterations=self._max_iterations,
            max_tool_result_chars=self._max_tool_result_chars,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            session_key=ctx.session_key,
        )

        ctx.run_result = await self._runner.run(spec)
        logger.info(
            "Runner completed: stop_reason={}, tools_used={}",
            ctx.run_result.stop_reason,
            ctx.run_result.tools_used,
        )
        return TurnState.SAVE

    async def _save(self, ctx: TurnContext, db: AsyncSession) -> TurnState:
        """Persist all messages from this turn to the database."""
        if ctx.run_result is None:
            return TurnState.RESPOND

        final_content = ctx.run_result.final_content or ""

        # Separate tool messages from the runner messages
        tool_messages = _extract_tool_messages(ctx.run_result.messages)

        await self._session_manager.save_turn_messages(
            db,
            ctx.session_key,
            user_message=ctx.user_message,
            assistant_content=final_content,
            tool_messages=tool_messages,
        )
        logger.debug("Turn messages saved to session '{}'", ctx.session_key)
        return TurnState.RESPOND

    def _respond(self, ctx: TurnContext) -> TurnState:
        """Build the final TurnResult payload."""
        if ctx.run_result is None:
            ctx.answer = ""
            ctx.stop_reason = "error"
            return TurnState.DONE

        ctx.answer = ctx.run_result.final_content or ""
        ctx.stop_reason = ctx.run_result.stop_reason

        # Extract thinking from messages (if model provides reasoning)
        ctx.thinking = _extract_thinking(ctx.run_result.messages)

        # Build tool_calls metadata for the response
        ctx.tool_calls_meta = _extract_tool_calls_meta(ctx.run_result)

        return TurnState.DONE


def _extract_tool_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract tool call and tool result messages from the runner output."""
    result: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "")
        if role in ("tool",):
            result.append({
                "role": role,
                "content": str(msg.get("content", "")),
                "tool_name": msg.get("name"),
                "tool_call_id": msg.get("tool_call_id"),
            })
        elif role == "assistant" and msg.get("tool_calls"):
            # This is a tool_call message (assistant requesting tools)
            for tc in msg["tool_calls"]:
                result.append({
                    "role": "assistant",
                    "content": json.dumps(tc, ensure_ascii=False),
                    "tool_name": tc.get("function", {}).get("name"),
                    "tool_call_id": tc.get("id"),
                })
    return result


def _extract_thinking(messages: list[dict[str, Any]]) -> str | None:
    """Try to extract reasoning/thinking content from messages.

    Some providers (DeepSeek-R1, o1) include reasoning_content.
    For now, we check the first assistant message for reasoning hints.
    """
    # Future: extract from provider's reasoning_content field
    return None


def _extract_tool_calls_meta(result: AgentRunResult) -> list[dict[str, Any]]:
    """Build a summary of tool calls for the API response."""
    meta: list[dict[str, Any]] = []
    seen = set()
    for msg in result.messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                name = tc.get("function", {}).get("name", "unknown")
                args_str = tc.get("function", {}).get("arguments", "{}")
                try:
                    arguments = json.loads(args_str) if isinstance(args_str, str) else args_str
                except (json.JSONDecodeError, TypeError):
                    arguments = {}

                # Avoid duplicates
                key = f"{name}:{str(arguments)}"
                if key not in seen:
                    seen.add(key)
                    meta.append({
                        "name": name,
                        "arguments": arguments,
                        "result_summary": None,
                    })
    return meta
