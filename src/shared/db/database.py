"""Async database engine and session factory."""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./vela.db")

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQLALCHEMY_ECHO", "").lower() in ("1", "true"),
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    """Get a new async database session."""
    async with async_session_factory() as session:
        yield session


async def ensure_tables() -> None:
    """Create all tables if they don't exist (idempotent, async)."""
    from src.shared.db.base import Base
    import src.shared.db.models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def ensure_tables_sync() -> None:
    """Create all tables synchronously (for startup before event loop)."""
    from sqlalchemy import create_engine
    from src.shared.db.base import Base
    import src.shared.db.models  # noqa: F401

    sync_url = DATABASE_URL.replace("+aiosqlite", "").replace("+aiomysql", "+pymysql")
    sync_engine = create_engine(sync_url)
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()


async def check_db_health() -> bool:
    """Check database connectivity."""
    try:
        async with engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        return True
    except Exception:
        return False
