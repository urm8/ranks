"""Build FE-compatible ranks snapshot and persist to Postgres."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ranks_scraper.parsing.benchmarks import (
    BENCHMARK_BY_SPIDER,
    CATEGORY_DEFS,
    TOKEN_CYCLES,
)
from ranks_scraper.parsing.normalize import normalize_model_id


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_scrape_dir(out_dir: str | Path) -> list[dict]:
    out_dir = Path(out_dir)
    combined = out_dir / "fetched.json"
    if combined.exists():
        data = json.loads(combined.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    rows: list[dict] = []
    for path in sorted(out_dir.glob("*.json")):
        if path.name in {"fetched.json", "index.json", "snapshot.json"}:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows.extend(payload)
        elif isinstance(payload, dict):
            rows.append(payload)
    return rows


def _merge_models(*catalogs: dict[str, dict]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for catalog in catalogs:
        for mid, entry in (catalog or {}).items():
            key = normalize_model_id(mid)
            if key not in merged:
                merged[key] = dict(entry)
                continue
            cur = merged[key]
            for field in ("name", "vendor", "release_date", "input", "output", "context", "price_source"):
                if cur.get(field) in (None, "", []) and entry.get(field) not in (None, "", []):
                    cur[field] = entry[field]
            srcs = list(cur.get("catalog_sources") or [])
            for s in entry.get("catalog_sources") or []:
                if s not in srcs:
                    srcs.append(s)
            cur["catalog_sources"] = srcs
            cur["discovered"] = True
    return merged


def build_snapshot(fetched: list[dict]) -> dict[str, Any]:
    models: dict[str, dict] = {}
    for item in fetched:
        models = _merge_models(models, item.get("models") or {})

    # Ensure ranking model ids exist in models table.
    for item in fetched:
        for row in item.get("rankings") or []:
            mid = normalize_model_id(row.get("model_id") or "")
            if not mid:
                continue
            if mid not in models:
                models[mid] = {
                    "name": row.get("model") or mid.split("/")[-1],
                    "vendor": mid.split("/")[0] if "/" in mid else "unknown",
                    "discovered": True,
                    "catalog_sources": [item.get("name") or item.get("spider") or "scrape"],
                    "price_source": "seed pricing",
                }
            pricing = row.get("pricing") or {}
            entry = models[mid]
            for src, dst in (("input", "input"), ("output", "output"), ("context", "context")):
                if entry.get(dst) is None and pricing.get(src) is not None:
                    entry[dst] = pricing[src]
                    entry["price_source"] = pricing.get("source") or entry.get("price_source")

    benchmarks_by_id: dict[str, dict] = {}
    for item in fetched:
        spider = item.get("spider") or ""
        meta = BENCHMARK_BY_SPIDER.get(spider)
        rankings = item.get("rankings") or []
        if not meta or not rankings:
            continue
        bid = meta["id"]
        prefer = bool(meta.get("prefer"))
        existing = benchmarks_by_id.get(bid)
        if existing and existing.get("rankings") and not prefer:
            # Keep preferred (ZeroEval) if already set; otherwise first wins unless prefer.
            if existing.get("_prefer"):
                continue
        card = {
            "id": bid,
            "category": meta["category"],
            "name": meta["name"],
            "measures": meta["measures"],
            "url": meta.get("url") or item.get("url"),
            "rankings": rankings,
            "source_status": {
                "ok": bool(item.get("ok")),
                "spider": spider,
                "fetched_at": item.get("fetched_at"),
                "source_date": item.get("source_date"),
                "error": item.get("error"),
            },
            "_prefer": prefer,
        }
        benchmarks_by_id[bid] = card

    benchmarks = []
    for card in benchmarks_by_id.values():
        card.pop("_prefer", None)
        benchmarks.append(card)
    benchmarks.sort(key=lambda b: b["id"])

    categories = []
    for cat in CATEGORY_DEFS:
        cat_benchmarks = [b for b in benchmarks if b.get("category") == cat["id"]]
        quality: dict[str, dict] = {}
        for bench in cat_benchmarks:
            for row in bench.get("rankings") or []:
                mid = row.get("model_id")
                if not mid:
                    continue
                score = float(row.get("normalized_score") or 0)
                prev = quality.get(mid)
                if prev is None or score > float(prev.get("quality") or 0):
                    model = models.get(mid) or {}
                    pricing = row.get("pricing") or {}
                    quality[mid] = {
                        "id": mid,
                        "name": row.get("model") or model.get("name") or mid,
                        "vendor": model.get("vendor") or mid.split("/")[0],
                        "quality": score,
                        "input": pricing.get("input", model.get("input")),
                        "output": pricing.get("output", model.get("output")),
                        "context": pricing.get("context", model.get("context")),
                        "price_source": pricing.get("source") or model.get("price_source"),
                        "note": f"Auto-included from live {bench.get('name')} ranking.",
                        "auto": True,
                        "cycle_cost": None,
                        "value": None,
                    }
                    inp = quality[mid].get("input")
                    out = quality[mid].get("output")
                    cycle = TOKEN_CYCLES.get(cat["id"])
                    if cycle and inp is not None and out is not None:
                        try:
                            cost = (float(inp) * cycle["input"] + float(out) * cycle["output"]) / 1_000_000
                            quality[mid]["cycle_cost"] = cost
                            quality[mid]["value"] = (score / cost) if cost > 0 else None
                        except (TypeError, ValueError):
                            pass
        quality_ranked = sorted(quality.values(), key=lambda r: (-float(r.get("quality") or 0), r["id"]))
        value_ranked = sorted(
            [r for r in quality_ranked if r.get("value") is not None],
            key=lambda r: (-float(r["value"]), r["id"]),
        )
        categories.append(
            {
                "id": cat["id"],
                "title": cat["title"],
                "summary": cat["summary"],
                "benchmarks": [b["id"] for b in cat_benchmarks],
                "benchmark_details": cat_benchmarks,
                "candidates": [],
                "cycle": TOKEN_CYCLES.get(cat["id"]),
                "quality_ranked": quality_ranked,
                "value_ranked": value_ranked,
            }
        )

    ranked_ids = {row.get("model_id") for b in benchmarks for row in (b.get("rankings") or [])}
    ranked_ids.update({row["id"] for c in categories for row in c.get("quality_ranked") or []})
    emerging = []
    for mid, entry in models.items():
        if mid in ranked_ids:
            continue
        if not entry.get("discovered"):
            continue
        emerging.append(
            {
                "id": mid,
                "name": entry.get("name") or mid,
                "vendor": entry.get("vendor"),
                "input": entry.get("input"),
                "output": entry.get("output"),
                "context": entry.get("context"),
                "release_date": entry.get("release_date"),
                "catalog_sources": entry.get("catalog_sources") or [],
                "price_source": entry.get("price_source"),
                "discovered": True,
            }
        )
    emerging.sort(key=lambda r: (r.get("release_date") or "", r["id"]), reverse=True)

    mentions: dict[str, list[str]] = {}
    for item in fetched:
        name = item.get("name") or item.get("spider")
        if not name:
            continue
        found = []
        for row in item.get("rankings") or []:
            mid = row.get("model_id")
            if mid and mid not in found:
                found.append(mid)
        if found:
            mentions[name] = found

    sources = []
    for item in fetched:
        sources.append({k: v for k, v in item.items() if k not in {"body", "models", "rankings", "mentions"}})

    return {
        "generated_at": utc_now_iso(),
        "sources": sources,
        "models": models,
        "benchmarks": benchmarks,
        "categories": categories,
        "emerging_models": emerging,
        "mentions": mentions,
        "estimation_basis": {"cycles": TOKEN_CYCLES},
    }


def store_snapshot(data: dict[str, Any]) -> str:
    """Insert snapshot into ranks_snapshots (same table the FE app reads)."""
    import pg8000.native

    user = os.environ["RANKS_DB_USER"]
    password = os.environ["RANKS_DB_PASSWORD"]
    host = os.environ["RANKS_DB_HOST"]
    port = int(os.environ.get("RANKS_DB_PORT") or "5432")
    database = os.environ["RANKS_DB_NAME"]
    conn = pg8000.native.Connection(
        user=user,
        password=password,
        host=host,
        port=port,
        database=database,
        timeout=30,
    )
    try:
        conn.run(
            """
            CREATE TABLE IF NOT EXISTS ranks_snapshots (
                id BIGSERIAL PRIMARY KEY,
                generated_at TIMESTAMPTZ NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        generated_at = data.get("generated_at") or utc_now_iso()
        conn.run(
            "INSERT INTO ranks_snapshots (generated_at, data) VALUES (:generated_at::timestamptz, :data::jsonb)",
            generated_at=generated_at,
            data=json.dumps(data),
        )
        conn.run(
            "DELETE FROM ranks_snapshots WHERE id NOT IN "
            "(SELECT id FROM ranks_snapshots ORDER BY generated_at DESC LIMIT 60)"
        )
        return generated_at
    finally:
        conn.close()


def publish_from_dir(out_dir: str | Path, *, write_db: bool = True) -> dict[str, Any]:
    fetched = load_scrape_dir(out_dir)
    snapshot = build_snapshot(fetched)
    out_path = Path(out_dir) / "snapshot.json"
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    if write_db:
        generated_at = store_snapshot(snapshot)
        snapshot["_stored_generated_at"] = generated_at
    return snapshot
