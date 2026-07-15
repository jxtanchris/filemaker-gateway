"""FastAPI application factory and startup wiring."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from filemaker_gateway.api.deps import init_dependencies
from filemaker_gateway.api.middleware import AuthMiddleware, RequestLoggingMiddleware
from filemaker_gateway.api.router import create_router
from filemaker_gateway.config.schema import AppConfig
from filemaker_gateway.fm.client import FMDataClient
from filemaker_gateway.fm.client_odata import FMODataClient
from filemaker_gateway.provider.factory import make_provider
from filemaker_gateway.session.database import close_database, create_tables, init_database
from filemaker_gateway.tool.loader import ToolLoader
from filemaker_gateway.tool.registry import ToolRegistry


def create_app(config: AppConfig) -> FastAPI:
    """Create and wire the FastAPI application.

    Assembly order:
    1. Database → 2. Tools → 3. Provider → 4. AgentLoop → 5. API
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Startup and shutdown lifecycle."""
        # --- Startup ---
        # Also write logs to a fixed file for easy tailing
        logger.add(
            "logs/gateway.log",
            rotation="10 MB",
            retention=3,
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        )
        logger.info("Starting FileMaker AI Gateway v0.1.0")

        # 1. Database
        init_database(config.database.url)
        await create_tables()
        logger.info("Database initialized: {}", config.database.url)

        # 2. Provider
        provider = make_provider(config.gateway.provider)
        logger.info("Provider ready: {}", config.gateway.provider.name)

        # 3. FM client — OData first, then Data API, else stub
        fm_client: FMDataClient | FMODataClient | None = None
        if config.fm_odata.enabled:
            fm_client = FMODataClient(config.fm_odata)
            logger.info(
                "FM OData client created: {}://{}/{}",
                config.fm_odata.protocol,
                config.fm_odata.host,
                config.fm_odata.database,
            )
        elif config.fm_data_api.enabled:
            fm_client = FMDataClient(config.fm_data_api)
            logger.info(
                "FM Data API client created: {}://{}/{}",
                config.fm_data_api.protocol,
                config.fm_data_api.host,
                config.fm_data_api.database,
            )
        else:
            logger.info("FM API disabled — FM Tools will return stub errors")

        # 4. Tools (with dependency injection)
        tool_registry = ToolRegistry()
        loader = ToolLoader()
        tool_kwargs: dict = {}
        if fm_client is not None:
            tool_kwargs["fm_client"] = fm_client
        tool_kwargs["provider"] = provider  # for OCRTool
        names = loader.load(tool_registry, **tool_kwargs)
        logger.info("Loaded {} tools: {}", len(names), names)

        # 5. Wire dependencies for API
        init_dependencies(config, tool_registry, provider)
        logger.info("Dependencies wired")

        yield

        # --- Shutdown ---
        if fm_client is not None:
            await fm_client.close()
            logger.info("FM client closed")
        await close_database()
        logger.info("Gateway shut down")

    app = FastAPI(
        title="FileMaker AI Gateway",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(RequestLoggingMiddleware)
    if config.gateway.api_key:
        app.add_middleware(AuthMiddleware, api_key=config.gateway.api_key)

    # Routes
    router = create_router(config)
    app.include_router(router)

    return app
