from __future__ import annotations

import json
import os
from collections.abc import Generator
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import DateTime, MetaData, Table, Column, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

EMPTY_SNAPSHOT: dict[str, Any] = {
    "generated_at": "never (no snapshot published yet)",
    "sources": [],
    "models": {},
    "benchmarks": [],
    "categories": [],
    "emerging_models": [],
    "mentions": {},
    "estimation_basis": {"cycles": {}},
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def database_url() -> str:
    """Build a SQLAlchemy URL from RANKS_DB_* env vars (psycopg3 driver)."""
    user = quote_plus(_env("RANKS_DB_USER", "ranks"))
    password = quote_plus(_env("RANKS_DB_PASSWORD", ""))
    host = _env("RANKS_DB_HOST", "localhost")
    port = _env("RANKS_DB_PORT", "5432")
    name = quote_plus(_env("RANKS_DB_NAME", "ranks"))
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None

metadata = MetaData()

ranks_snapshots = Table(
    "ranks_snapshots",
    metadata,
    Column("generated_at", DateTime(timezone=True), primary_key=True),
    Column("data", JSONB, nullable=False),
)


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(
            database_url(),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _SessionLocal = sessionmaker(
            bind=_engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one Session per request, always closed."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def dispose_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def _normalize_payload(data: Any, generated_at: datetime | None) -> dict[str, Any]:
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8")
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise RuntimeError("snapshot data is not an object")

    if generated_at is not None and "generated_at" not in data:
        data["generated_at"] = generated_at.isoformat()
    return data


def fetch_latest_generated_at(session: Session) -> datetime | None:
    stmt = (
        select(ranks_snapshots.c.generated_at)
        .order_by(ranks_snapshots.c.generated_at.desc())
        .limit(1)
    )
    try:
        row = session.execute(stmt).one_or_none()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"snapshot query failed: {exc}") from exc
    return None if row is None else row[0]


def fetch_latest_snapshot(session: Session) -> dict[str, Any] | None:
    """Return the newest ranks_snapshots.data payload, or None if the table is empty."""
    stmt = (
        select(ranks_snapshots.c.data, ranks_snapshots.c.generated_at)
        .order_by(ranks_snapshots.c.generated_at.desc())
        .limit(1)
    )
    try:
        row = session.execute(stmt).one_or_none()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"snapshot query failed: {exc}") from exc

    if row is None:
        return None

    data, generated_at = row[0], row[1]
    return _normalize_payload(data, generated_at)
