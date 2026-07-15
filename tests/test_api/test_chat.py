"""Integration tests for the REST API.

Tests use FastAPI TestClient-like patterns, manually triggering
the lifespan startup since ASGITransport doesn't call it automatically.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from filemaker_gateway.api.deps import get_config, get_loop, get_session_manager, get_tool_registry
from filemaker_gateway.main import create_app


@pytest.mark.asyncio
async def test_health_check(app):
    """Health endpoint should return status without auth."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "provider" in data


@pytest.mark.asyncio
async def test_chat_requires_auth(app):
    """Chat endpoint should reject requests without API key."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat",
            json={"session": "test", "message": "hello"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_with_auth(app, app_config):
    """Chat endpoint should accept authenticated requests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat",
            json={"session": "test-chat", "message": "hello"},
            headers={"X-API-Key": app_config.gateway.api_key},
        )
    # Won't be 401 (auth passed), may be 500 because no real LLM key
    assert response.status_code != 401


@pytest.mark.asyncio
async def test_list_sessions_empty(app, app_config):
    """Should return list of sessions."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/sessions",
            headers={"X-API-Key": app_config.gateway.api_key},
        )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_session_not_found(app, app_config):
    """Should return 404 for nonexistent session."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/sessions/nonexistent",
            headers={"X-API-Key": app_config.gateway.api_key},
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_deps_wired(app):
    """Verify that all dependencies are properly wired."""
    loop = get_loop()
    assert loop is not None

    mgr = get_session_manager()
    assert mgr is not None

    tools = get_tool_registry()
    assert tools is not None
    assert len(tools) >= 1

    config = get_config()
    assert config is not None
    assert config.gateway.api_key == "test-api-key"
