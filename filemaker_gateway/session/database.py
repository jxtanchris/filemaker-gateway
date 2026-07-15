"""SQLite database connection, engine, and async session factory."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from filemaker_gateway.session.models import Base

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_database(database_url: str, echo: bool = False) -> async_sessionmaker[AsyncSession]:
    """Initialize the database engine and session factory.

    Call once at application startup.
    """
    global _engine, _session_factory

    connect_args = {}
    if "sqlite" in database_url:
        connect_args["check_same_thread"] = False

    _engine = create_async_engine(database_url, echo=echo, connect_args=connect_args)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    return _session_factory


async def create_tables() -> None:
    """Create all tables if they don't exist. Call after init_database."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Get a new async database session. Yields via context manager pattern."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    async with _session_factory() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the session factory directly. Raises if not initialized."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _session_factory


async def close_database() -> None:
    """Dispose the engine. Call at application shutdown."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
