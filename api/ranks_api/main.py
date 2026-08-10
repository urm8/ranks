from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from ranks_api.db import EMPTY_SNAPSHOT, dispose_engine, fetch_latest_snapshot, get_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
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


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/data")
def api_data(db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        data = fetch_latest_snapshot(db)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if data is None:
        return EMPTY_SNAPSHOT
    return data


@app.get("/api/benchmarks/{benchmark_id}")
def api_benchmark(
    benchmark_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        data = fetch_latest_snapshot(db)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if data is None:
        raise HTTPException(status_code=404, detail="no snapshot")

    needle = benchmark_id.strip().lower()
    for bench in data.get("benchmarks") or []:
        if not isinstance(bench, dict):
            continue
        candidates = [
            str(bench.get("id") or ""),
            str(bench.get("slug") or ""),
            str(bench.get("name") or ""),
        ]
        if any(c.lower() == needle for c in candidates if c):
            return bench

    for cat in data.get("categories") or []:
        if not isinstance(cat, dict):
            continue
        for bench in cat.get("benchmark_details") or cat.get("benchmarks") or []:
            if not isinstance(bench, dict):
                continue
            candidates = [
                str(bench.get("id") or ""),
                str(bench.get("slug") or ""),
                str(bench.get("name") or ""),
            ]
            if any(c.lower() == needle for c in candidates if c):
                return bench

    raise HTTPException(status_code=404, detail="benchmark not found")


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("ranks_api.main:app", host=host, port=port, proxy_headers=True)


if __name__ == "__main__":
    main()
