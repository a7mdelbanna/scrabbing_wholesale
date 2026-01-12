"""Database connection and session management."""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from src.config.settings import settings
from src.models.database import Base

logger = logging.getLogger(__name__)

# Global engine instance
_engine: AsyncEngine = None
_async_session_factory: async_sessionmaker = None

# Synchronous engine and session for API
_sync_engine = None
SessionLocal: sessionmaker = None


def get_sync_engine():
    """Get or create the synchronous database engine."""
    global _sync_engine
    if _sync_engine is None:
        # Convert async URL to sync URL
        sync_url = settings.database_url.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")
        _sync_engine = create_engine(
            sync_url,
            echo=settings.log_level == "DEBUG",
            pool_pre_ping=True,
        )
        logger.info("Synchronous database engine created")
    return _sync_engine


def get_sync_session_factory() -> sessionmaker:
    """Get or create the synchronous session factory."""
    global SessionLocal
    if SessionLocal is None:
        engine = get_sync_engine()
        SessionLocal = sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
        )
        logger.info("Synchronous session factory created")
    return SessionLocal


def get_engine() -> AsyncEngine:
    """Get or create the database engine.

    Returns:
        AsyncEngine instance.
    """
    global _engine

    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.log_level == "DEBUG",
            poolclass=NullPool,  # Recommended for async
        )
        logger.info("Database engine created")

    return _engine


def get_session_factory() -> async_sessionmaker:
    """Get or create the session factory.

    Returns:
        async_sessionmaker instance.
    """
    global _async_session_factory

    if _async_session_factory is None:
        engine = get_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        logger.info("Session factory created")

    return _async_session_factory


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session.

    Yields:
        AsyncSession instance.

    Example:
        async with get_async_session() as session:
            result = await session.execute(query)
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize the database schema.

    Creates all tables defined in the models.
    """
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables created")


async def close_db() -> None:
    """Close database connections."""
    global _engine, _async_session_factory

    if _engine:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("Database connections closed")
