from contextlib import contextmanager
from typing import Generator, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config.settings import settings
from app.utils.logging import logger

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def normalize_database_url(url: str) -> str:
    """
    Normalizes PostgreSQL connection URI schemes to ensure compatibility with psycopg 3.
    Converts 'postgres://' or 'postgresql://' to 'postgresql+psycopg://'.
    """
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def get_database_engine(database_url: Optional[str] = None) -> Engine:
    """
    Returns the singleton SQLAlchemy Engine instance configured with production connection pooling.
    """
    global _engine
    if _engine is not None and database_url is None:
        return _engine

    raw_url = database_url or settings.database_url
    if not raw_url:
        raise ValueError(
            "DATABASE_URL is not configured. Please define DATABASE_URL in environment or .env file."
        )

    clean_url = normalize_database_url(raw_url)

    engine_kwargs = {
        "pool_pre_ping": True,
    }

    # SQLite does not support standard pooling parameters
    if clean_url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool
        engine_kwargs.update({
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        })
    else:
        engine_kwargs.update({
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_timeout": settings.db_pool_timeout,
        })

    _engine = create_engine(clean_url, **engine_kwargs)
    logger.info("Initialized SQLAlchemy database engine.")
    return _engine


def get_session_factory(engine: Optional[Engine] = None) -> sessionmaker:
    """Returns or initializes the thread-safe sessionmaker factory."""
    global _session_factory
    if _session_factory is not None and engine is None:
        return _session_factory

    active_engine = engine or get_database_engine()
    _session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=active_engine,
        expire_on_commit=False,
    )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a managed database session.
    Guarantees session closure after request handling.
    """
    session_factory = get_session_factory()
    session: Session = session_factory()
    try:
        yield session
    except Exception as e:
        session.rollback()
        logger.error(f"Database session rolled back due to error: {e}")
        raise
    finally:
        session.close()


@contextmanager
def session_scope(session_factory: Optional[sessionmaker] = None) -> Generator[Session, None, None]:
    """
    Context manager for transactional database operations outside FastAPI requests.
    Automatically commits on normal completion or rolls back on exception.
    """
    factory = session_factory or get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Transaction failed and was rolled back: {e}")
        raise
    finally:
        session.close()


def check_database_health(engine: Optional[Engine] = None) -> bool:
    """
    Executes a lightweight query (SELECT 1) to verify database connectivity.
    """
    try:
        active_engine = engine or get_database_engine()
        with active_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return False
