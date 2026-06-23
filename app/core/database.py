import json
import time
from contextlib import contextmanager
from typing import Iterator

import boto3
import psycopg2
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


class _RotatingCredentials:
    """RDS シークレットの認証情報を短TTLでキャッシュし、ローテーションに追従する"""

    def __init__(self, secret_name: str, region: str, ttl_seconds: int) -> None:
        self._secret_name = secret_name
        self._ttl_seconds = ttl_seconds
        self._client = boto3.client("secretsmanager", region_name=region)
        self._cache: dict[str, str] | None = None
        self._fetched_at: float = 0.0

    def get(self, force_refresh: bool = False) -> dict[str, str]:
        now = time.monotonic()
        if (
            force_refresh
            or self._cache is None
            or now - self._fetched_at >= self._ttl_seconds
        ):
            self._cache = self._fetch()
            self._fetched_at = now
        return self._cache

    def _fetch(self) -> dict[str, str]:
        response = self._client.get_secret_value(SecretId=self._secret_name)
        data = json.loads(response["SecretString"])
        return {"username": data["username"], "password": data["password"]}


def _register_rotation_listener(
    engine: Engine, secret_name: str, region: str, ttl_seconds: int
) -> None:
    """接続確立直前に最新の認証情報を注入する do_connect リスナーを登録する"""
    credentials = _RotatingCredentials(secret_name, region, ttl_seconds)

    @event.listens_for(engine, "do_connect")
    def _inject_credentials(dialect, conn_rec, cargs, cparams):
        creds = credentials.get()
        cparams["user"] = creds["username"]
        cparams["password"] = creds["password"]
        try:
            return dialect.connect(*cargs, **cparams)
        except psycopg2.OperationalError:
            # ローテーション直後の古いパスワードを想定し、最新を再取得して1回だけ再接続
            creds = credentials.get(force_refresh=True)
            cparams["user"] = creds["username"]
            cparams["password"] = creds["password"]
            return dialect.connect(*cargs, **cparams)


def _get_session_local() -> sessionmaker:
    global _engine, _SessionLocal
    if _SessionLocal is None:
        settings = get_settings()
        _engine = create_engine(
            settings.get_database_url(),
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
            pool_pre_ping=False,
        )
        if settings.db_secret_name:
            _register_rotation_listener(
                _engine,
                settings.db_secret_name,
                settings.aws_region,
                settings.db_secret_ttl_seconds,
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
