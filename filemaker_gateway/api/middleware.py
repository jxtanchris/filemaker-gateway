"""FastAPI middleware: authentication and request logging."""

import time

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from filemaker_gateway.security.auth import validate_api_key


class AuthMiddleware(BaseHTTPMiddleware):
    """Validate X-API-Key header on protected routes.

    Skips /health endpoint.
    Uses constant-time comparison to prevent timing attacks.
    """

    def __init__(self, app, api_key: str) -> None:
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip auth for health check and console
        if request.url.path in ("/health", "/"):
            return await call_next(request)

        # Validate API key
        if not self._api_key:
            # No API key configured — allow all requests (dev mode)
            return await call_next(request)

        provided = request.headers.get("X-API-Key", "")
        if not validate_api_key(provided, self._api_key):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )

        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status, and duration."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000

        logger.info(
            "{method} {path} → {status} ({duration:.0f}ms)",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration=duration_ms,
        )
        return response
