"""REST API routes.

Routes:
    GET  /              - Chat console (Web UI)
    POST /chat          - Send a message, get AI response
    GET  /health        - Health check
    GET  /sessions      - List sessions
    GET  /sessions/{id} - Session detail with message history
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from filemaker_gateway.agent.loop import AgentLoop
from filemaker_gateway.api.deps import (
    get_config,
    get_db,
    get_loop,
    get_session_manager,
)
from filemaker_gateway.api.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    SessionDetail,
    SessionInfo,
)
from filemaker_gateway.config.schema import AppConfig
from filemaker_gateway.session.manager import SessionManager


def create_router(config: AppConfig) -> APIRouter:
    """Create and wire the API router.

    Args:
        config: Application configuration (used for health endpoint
            before full dependency injection is set up).
    """
    router = APIRouter()

    # --- Console (Web UI) ---

    # Load the chat console HTML once at module load time
    _console_path = Path(__file__).parent / "console.html"
    _CONSOLE_HTML = _console_path.read_text(encoding="utf-8") if _console_path.exists() else "<h1>console.html not found</h1>"

    @router.get("/", response_class=HTMLResponse)
    async def console() -> HTMLResponse:
        """Serve the chat console (Web UI for testing)."""
        return HTMLResponse(_CONSOLE_HTML)

    # --- Health ---

    @router.get("/health", response_model=HealthResponse)
    async def health(
        cfg: AppConfig = Depends(get_config),
    ) -> HealthResponse:
        """Health check endpoint. No auth required."""
        from filemaker_gateway.api.deps import get_tool_registry
        tools = get_tool_registry()
        return HealthResponse(
            status="ok",
            version="0.1.0",
            provider=cfg.gateway.provider.name,
            model=cfg.gateway.provider.model or "default",
            tools=tools.tool_names if tools else [],
        )

    # --- Chat ---

    @router.post(
        "/chat",
        response_model=ChatResponse,
        responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    async def chat(
        request: ChatRequest,
        db: AsyncSession = Depends(get_db),
        loop: AgentLoop = Depends(get_loop),
    ) -> ChatResponse:
        """Send a message to the AI agent.

        The gateway translates the FileMaker message into an agent turn,
        executes the tool-using LLM loop, and returns the result.
        """
        result = await loop.process_turn(
            db=db,
            session_key=request.session,
            user_message=request.message,
            media=request.media,
        )

        if result.error:
            raise HTTPException(status_code=500, detail=result.error)

        return ChatResponse(
            answer=result.answer,
            thinking=result.thinking,
            tool_calls=[
                {
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                    "result_summary": tc.get("result_summary"),
                }
                for tc in result.tool_calls
            ],
            session=result.session,
            stop_reason=result.stop_reason,
        )

    # --- Sessions ---

    @router.get("/sessions", response_model=list[SessionInfo])
    async def list_sessions(
        limit: int = 50,
        offset: int = 0,
        db: AsyncSession = Depends(get_db),
        mgr: SessionManager = Depends(get_session_manager),
    ) -> list[SessionInfo]:
        """List all sessions, ordered by most recent activity."""
        sessions = await mgr.list_sessions(db, limit=limit, offset=offset)
        return [
            SessionInfo(
                id=s.id,
                created_at=s.created_at,
                updated_at=s.updated_at,
                message_count=s.message_count,
                metadata=s.metadata,
            )
            for s in sessions
        ]

    @router.get(
        "/sessions/{session_id}",
        response_model=SessionDetail,
        responses={404: {"model": ErrorResponse}},
    )
    async def get_session(
        session_id: str,
        db: AsyncSession = Depends(get_db),
        mgr: SessionManager = Depends(get_session_manager),
    ) -> SessionDetail:
        """Get a session's full detail with message history."""
        detail = await mgr.get_session_detail(db, session_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Session not found")

        return SessionDetail(
            id=detail["id"],
            created_at=detail["created_at"],
            updated_at=detail["updated_at"],
            messages=[
                {
                    "role": m["role"],
                    "content": m["content"],
                    "tool_name": m.get("tool_name"),
                    "created_at": m["created_at"],
                }
                for m in detail["messages"]
            ],
            metadata=detail.get("metadata"),
        )

    return router
