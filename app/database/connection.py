"""SQLAlchemy engine, sessions, and declarative model base."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url.get_secret_value(),
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class inherited by all SQLAlchemy database models."""


def get_db() -> Generator[Session, None, None]:
    """Provide one database session and always close it afterward."""
    database_session = SessionLocal()
    try:
        yield database_session
    finally:
        database_session.close()
