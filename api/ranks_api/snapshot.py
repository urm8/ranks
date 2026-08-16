from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import time
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ranks_api.db import fetch_latest_generated_at, fetch_latest_snapshot

PREVIEW_LIMIT = 5
DEFAULT_CHUNK = 200
MAX_CHUNK = 500
EMERGING_PREVIEW = 24
DEFAULT_CACHE_TTL = 60.0
PAGE_CACHE_MAX = 256


@dataclass
class SnapshotIndex:
    generated_at: str
    lists: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    homepage: dict[str, Any] = field(default_factory=dict)
    homepage_json: bytes = b"{}"
    etag: str = '""'


_lock = threading.Lock()
_index: SnapshotIndex | None = None
_cached_at: datetime | None = None
_ttl_until: float = 0.0
_page_cache: dict[tuple[str, str, str, int], dict[str, Any]] = {}


def cache_ttl_seconds() -> float:
    raw = os.environ.get("RANKS_CACHE_TTL", str(int(DEFAULT_CACHE_TTL)))
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_CACHE_TTL


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _model_key(row: dict[str, Any]) -> str:
    return str(
        row.get("model_id") or row.get("id") or row.get("name") or row.get("model") or ""
    ).casefold()


def _source_key(row: dict[str, Any]) -> str:
    raw = row.get("source") or row.get("price_source") or row.get("spider")
    if isinstance(raw, list) and raw:
        raw = raw[0]
    return str(raw or "").casefold()


def _date_key(row: dict[str, Any]) -> str:
    raw = (
        row.get("parse_date")
        or row.get("source_date")
        or row.get("fetched_at")
        or row.get("discovered")
    )
    return str(raw or "")


def _score_value(row: dict[str, Any]) -> float | None:
    score = _as_float(row.get("score"))
    if score is None:
        score = _as_float(row.get("normalized_score"))
    return score


def order_key(row: dict[str, Any]) -> tuple:
    """Total order for listings and keyset seeks: quality, score, rank, model, source, date."""
    quality = _as_float(row.get("quality"))
    score = _score_value(row)
    rank = _as_float(row.get("rank"))
    return (
        0 if quality is not None else 1,
        -(quality or 0.0),
        0 if score is not None else 1,
        -(score or 0.0),
        rank if rank is not None else float("inf"),
        _model_key(row),
        _source_key(row),
        _date_key(row),
    )


def cursor_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "m": _model_key(row),
        "src": _source_key(row),
        "d": _date_key(row),
        "q": _as_float(row.get("quality")),
        "sc": _score_value(row),
        "r": _as_float(row.get("rank")),
    }


def encode_cursor(row: dict[str, Any]) -> str:
    raw = json.dumps(cursor_payload(row), separators=(",", ":"), ensure_ascii=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> dict[str, Any]:
    if cursor is None or cursor == "":
        raise ValueError("cursor is empty")
    if cursor.isdigit():
        raise ValueError("cursor must be a keyset, not an offset")
    pad = "=" * (-len(cursor) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + pad))
    except Exception as exc:
        raise ValueError("cursor is not a valid keyset") from exc
    if not isinstance(data, dict) or "m" not in data:
        raise ValueError("cursor is not a valid keyset")
    return data


def order_key_from_cursor(cursor: dict[str, Any]) -> tuple:
    quality = _as_float(cursor.get("q"))
    score = _as_float(cursor.get("sc"))
    rank = _as_float(cursor.get("r"))
    return (
        0 if quality is not None else 1,
        -(quality or 0.0),
        0 if score is not None else 1,
        -(score or 0.0),
        rank if rank is not None else float("inf"),
        str(cursor.get("m") or "").casefold(),
        str(cursor.get("src") or "").casefold(),
        str(cursor.get("d") or ""),
    )


def sort_by_performance(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=order_key)


def dedupe_rows(rows: list[Any]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ident = (_model_key(row), _source_key(row), _date_key(row))
        if ident[0] and ident in seen:
            continue
        if ident[0]:
            seen.add(ident)
        out.append(row)
    return out


def prepare_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return dedupe_rows(sort_by_performance([r for r in rows if isinstance(r, dict)]))


def page_items(
    items: list[dict[str, Any]],
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    limit = min(limit, MAX_CHUNK)
    if cursor:
        start = bisect_right(
            items,
            order_key_from_cursor(decode_cursor(cursor)),
            key=order_key,
        )
    else:
        start = 0
    chunk = items[start : start + limit]
    next_cursor = (
        encode_cursor(chunk[-1]) if chunk and start + len(chunk) < len(items) else None
    )
    return {
        "items": chunk,
        "total": len(items),
        "next_cursor": next_cursor,
    }


def _bench_id(bench: dict[str, Any]) -> str:
    return str(bench.get("id") or bench.get("slug") or bench.get("name") or "").strip()


def _cat_id(cat: dict[str, Any]) -> str:
    return str(cat.get("id") or cat.get("name") or "").strip()


def _model_count(models: Any) -> int:
    if isinstance(models, dict):
        return len(models)
    if isinstance(models, list):
        return len(models)
    return 0


def _preview(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    preview = items[:PREVIEW_LIMIT]
    nxt = encode_cursor(preview[-1]) if preview and len(items) > PREVIEW_LIMIT else None
    return preview, nxt


def build_index(data: dict[str, Any]) -> SnapshotIndex:
    lists: dict[str, list[dict[str, Any]]] = {}
    benches_out: list[dict[str, Any]] = []
    seen_benches: set[str] = set()

    for bench in data.get("benchmarks") or []:
        if not isinstance(bench, dict):
            continue
        bid = _bench_id(bench)
        if not bid:
            continue
        key = bid.casefold()
        if key in seen_benches:
            continue
        seen_benches.add(key)
        list_id = f"benchmark:{bid}"
        ranked = prepare_rows(bench.get("rankings"))
        lists[list_id] = ranked
        preview, nxt = _preview(ranked)
        benches_out.append(
            {
                "id": bid,
                "name": bench.get("name") or bid,
                "url": bench.get("url"),
                "category": bench.get("category"),
                "list": list_id,
                "rankings": preview,
                "rankings_total": len(ranked),
                "next_cursor": nxt,
            }
        )

    # Nested copies under categories are the same lists; index only if missing.
    for cat in data.get("categories") or []:
        if not isinstance(cat, dict):
            continue
        for bench in cat.get("benchmark_details") or []:
            if not isinstance(bench, dict):
                continue
            bid = _bench_id(bench)
            if not bid or bid.casefold() in seen_benches:
                continue
            seen_benches.add(bid.casefold())
            list_id = f"benchmark:{bid}"
            ranked = prepare_rows(bench.get("rankings"))
            lists[list_id] = ranked
            preview, nxt = _preview(ranked)
            benches_out.append(
                {
                    "id": bid,
                    "name": bench.get("name") or bid,
                    "url": bench.get("url"),
                    "category": bench.get("category") or cat.get("id"),
                    "list": list_id,
                    "rankings": preview,
                    "rankings_total": len(ranked),
                    "next_cursor": nxt,
                }
            )

    bench_by_id = {str(b["id"]).casefold(): b for b in benches_out}
    categories_out: list[dict[str, Any]] = []
    for cat in data.get("categories") or []:
        if not isinstance(cat, dict):
            continue
        cid = _cat_id(cat)
        if not cid:
            continue
        q_id = f"category:{cid}:quality"
        ranked = prepare_rows(cat.get("quality_ranked"))
        lists[q_id] = ranked
        preview, nxt = _preview(ranked)

        refs: list[dict[str, Any]] = []
        seen_refs: set[str] = set()
        raw_refs = cat.get("benchmarks") or []
        for ref in raw_refs:
            bid = str(ref).strip() if not isinstance(ref, dict) else _bench_id(ref)
            if not bid:
                continue
            token = bid.casefold()
            if token in seen_refs:
                continue
            seen_refs.add(token)
            meta = bench_by_id.get(token) or {"id": bid, "name": bid}
            refs.append({"id": meta.get("id") or bid, "name": meta.get("name") or bid})

        categories_out.append(
            {
                "id": cid,
                "name": cat.get("name") or cid,
                "description": cat.get("description"),
                "list": q_id,
                "quality_ranked": preview,
                "quality_total": len(ranked),
                "next_cursor": nxt,
                "benchmarks": refs,
            }
        )

    emerging = [
        row
        for row in (data.get("emerging_models") or [])
        if isinstance(row, dict)
    ]
    homepage = {
        "generated_at": data.get("generated_at"),
        "sources": data.get("sources") or [],
        "model_count": _model_count(data.get("models")),
        "emerging_models": emerging[:EMERGING_PREVIEW],
        "emerging_total": len(emerging),
        "benchmarks": benches_out,
        "categories": categories_out,
    }
    body = json.dumps(homepage, separators=(",", ":"), ensure_ascii=False).encode()
    digest = hashlib.sha256(body).hexdigest()[:16]
    return SnapshotIndex(
        generated_at=str(data.get("generated_at") or ""),
        lists=lists,
        homepage=homepage,
        homepage_json=body,
        etag=f'"{digest}"',
    )


def load_index(session: Session) -> SnapshotIndex | None:
    global _index, _cached_at, _ttl_until
    now = time.monotonic()
    with _lock:
        if _index is not None and now < _ttl_until:
            return _index

    latest = fetch_latest_generated_at(session)
    with _lock:
        if _index is not None and latest is not None and _cached_at == latest:
            _ttl_until = time.monotonic() + cache_ttl_seconds()
            return _index
        if _index is not None and latest is None:
            _ttl_until = time.monotonic() + cache_ttl_seconds()
            return _index

    data = fetch_latest_snapshot(session)
    if data is None:
        return None
    built = build_index(data)
    with _lock:
        _index = built
        _cached_at = latest
        _ttl_until = time.monotonic() + cache_ttl_seconds()
        _page_cache.clear()
    return built


def reset_index_cache() -> None:
    global _index, _cached_at, _ttl_until
    with _lock:
        _index = None
        _cached_at = None
        _ttl_until = 0.0
        _page_cache.clear()


def ranking_page(
    index: SnapshotIndex,
    list_id: str,
    cursor: str | None,
    limit: int = DEFAULT_CHUNK,
) -> dict[str, Any]:
    key = (index.generated_at, list_id, cursor or "", limit)
    with _lock:
        hit = _page_cache.get(key)
        if hit is not None:
            return hit
    items = index.lists.get(list_id)
    if items is None:
        raise KeyError(list_id)
    page = page_items(items, cursor, limit)
    page["list"] = list_id
    with _lock:
        if len(_page_cache) >= PAGE_CACHE_MAX:
            _page_cache.clear()
        _page_cache[key] = page
    return page
