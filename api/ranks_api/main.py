from __future__ import annotations

import hashlib
import json
import os
import threading
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response

from ranks_api.db import EMPTY_SNAPSHOT, dispose_engine, get_db, get_session_factory
from ranks_api.snapshot import (
    DEFAULT_CHUNK,
    MAX_CHUNK,
    load_index,
    ranking_page,
    reset_index_cache,
)


def _cache_headers(etag: str) -> dict[str, str]:
    return {
        "Cache-Control": "public, max-age=60, s-maxage=300, stale-while-revalidate=3600",
        "ETag": etag,
        "Vary": "Accept-Encoding",
    }


def _cached_json(request: Request, body: bytes, etag: str) -> Response:
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=_cache_headers(etag))
    return Response(
        content=body,
        media_type="application/json",
        headers=_cache_headers(etag),
    )


def _warm_index() -> None:
    try:
        session = get_session_factory()()
        try:
            load_index(session)
        finally:
            session.close()
    except Exception:
        return


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_warm_index, daemon=True).start()
    yield
    reset_index_cache()
    dispose_engine()


app = FastAPI(title="ranks-api", version="0.1.0", lifespan=lifespan)

_cors = os.environ.get(
    "RANKS_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)


def _index(db: Session):
    try:
        index = load_index(db)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if index is None:
        return None
    return index


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/data")
def api_data(request: Request, db: Session = Depends(get_db)) -> Response:
    index = _index(db)
    if index is None:
        slim = dict(EMPTY_SNAPSHOT)
        slim["model_count"] = 0
        slim.pop("models", None)
        slim.pop("mentions", None)
        slim.pop("estimation_basis", None)
        body = json.dumps(slim, separators=(",", ":")).encode()
        return _cached_json(request, body, '"empty"')
    return _cached_json(request, index.homepage_json, index.etag)


@app.get("/api/rankings")
def api_rankings(
    request: Request,
    list_id: Annotated[str, Query(alias="list", min_length=1)],
    cursor: str | None = None,
    limit: int = DEFAULT_CHUNK,
    db: Session = Depends(get_db),
) -> Response:
    if limit < 1 or limit > MAX_CHUNK:
        raise HTTPException(status_code=400, detail=f"limit must be 1..{MAX_CHUNK}")
    index = _index(db)
    if index is None:
        raise HTTPException(status_code=404, detail="no snapshot")
    try:
        page = ranking_page(index, list_id, cursor, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown list {exc.args[0]}") from exc
    body = json.dumps(page, separators=(",", ":"), ensure_ascii=False).encode()
    token = hashlib.sha256(
        f"{index.generated_at}:{list_id}:{cursor or ''}:{limit}".encode()
    ).hexdigest()[:16]
    return _cached_json(request, body, f'"{token}"')


@app.get("/api/benchmarks/{benchmark_id}")
def api_benchmark(
    request: Request,
    benchmark_id: str,
    db: Session = Depends(get_db),
) -> Response:
    index = _index(db)
    if index is None:
        raise HTTPException(status_code=404, detail="no snapshot")

    needle = benchmark_id.strip().lower()
    for bench in index.homepage.get("benchmarks") or []:
        if not isinstance(bench, dict):
            continue
        candidates = [
            str(bench.get("id") or ""),
            str(bench.get("name") or ""),
        ]
        if any(c.lower() == needle for c in candidates if c):
            body = json.dumps(bench, separators=(",", ":"), ensure_ascii=False).encode()
            return _cached_json(request, body, index.etag)

    raise HTTPException(status_code=404, detail="benchmark not found")


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("ranks_api.main:app", host=host, port=port, proxy_headers=True)


if __name__ == "__main__":
    main()
