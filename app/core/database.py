from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _get_session_local() -> sessionmaker:
    global _engine, _SessionLocal
    if _SessionLocal is None:
        settings = get_settings()
        _engine = create_engine(
            settings.get_database_url(),
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=3600,
            pool_pre_ping=False,
        )
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI Depends 用"""
    db = _get_session_local()()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Iterator[Session]:
    """サービス層用コンテキストマネージャ"""
    db = _get_session_local()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
