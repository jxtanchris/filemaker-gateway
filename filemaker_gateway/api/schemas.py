"""Pydantic request/response models for the REST API."""

from datetime import datetime

from pydantic import BaseModel


# --- Request models ---


class ChatRequest(BaseModel):
    """Inbound chat message from FileMaker."""

    session: str
    message: str
    media: list[str] | None = None


# --- Response models ---


class ToolCallMeta(BaseModel):
    """Metadata about a tool call executed during the turn."""

    name: str
    arguments: dict
    result_summary: str | None = None


class ChatResponse(BaseModel):
    """Outbound chat response to FileMaker."""

    answer: str
    thinking: str | None = None
    tool_calls: list[ToolCallMeta] = []
    session: str
    stop_reason: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    provider: str
    model: str
    tools: list[str]


class SessionInfo(BaseModel):
    """Summary of a session for listing."""

    id: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    metadata: dict | None = None


class MessageInfo(BaseModel):
    """A single message in session history."""

    role: str
    content: str
    tool_name: str | None = None
    created_at: datetime


class SessionDetail(BaseModel):
    """Full session detail with message history."""

    id: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageInfo]
    metadata: dict | None = None


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
