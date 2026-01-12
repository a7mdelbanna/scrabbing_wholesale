"""API dependencies for dependency injection."""
from typing import Generator

from sqlalchemy.orm import Session

from src.database.connection import get_sync_session_factory


def get_db() -> Generator[Session, None, None]:
    """Get database session dependency."""
    SessionLocal = get_sync_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
