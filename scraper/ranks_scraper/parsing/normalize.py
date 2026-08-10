"""Score and model-id normalization matching ranks.urm8.org FE expectations."""

from __future__ import annotations

import re
from typing import Any


LABEL_SCORE_MAP = {
    "top tier": 95.0,
    "balanced": 85.0,
    "value": 80.0,
    "open/value": 78.0,
    "open/vendor-diverse": 76.0,
    "open/vendor-diverse seed": 76.0,
}


def quality_from_rank(rank: int, total: int) -> float:
    """Map 1..N ranks onto 100..55 (span 45)."""
    if total <= 1:
        return 100.0
    span = 45.0
    return round(100.0 - (max(1, int(rank)) - 1) * span / (total - 1), 1)


def normalize_benchmark_score(score: Any, rank: int, total: int) -> float:
    """Always produce a 0-100 score for benchmark cards."""
    if isinstance(score, (int, float)):
        value = float(score)
        if 0.0 <= value <= 1.0:
            return round(value * 100.0, 1)
        if 0.0 <= value <= 100.0:
            return round(value, 1)

    label = str(score or "").strip().lower()
    numeric = re.match(r"^(\d+(?:\.\d+)?)\s*(%|/100)?$", label)
    if numeric:
        value = float(numeric.group(1))
        unit = numeric.group(2)
        if unit == "/100":
            return round(value, 1)
        if unit == "%" or value <= 100:
            return round(value, 1)

    if label in LABEL_SCORE_MAP:
        return LABEL_SCORE_MAP[label]
    return quality_from_rank(rank, total)


def attach_normalized_scores(rows: list[dict]) -> list[dict]:
    total = len(rows) or 1
    out: list[dict] = []
    for index, row in enumerate(rows, start=1):
        item = dict(row)
        rank = item.get("rank") or index
        item["rank"] = rank
        if item.get("normalized_score") is None:
            item["normalized_score"] = normalize_benchmark_score(
                item.get("score"), rank, total
            )
        out.append(item)
    return out


def normalize_model_id(model_id: str | None) -> str:
    text = str(model_id or "").strip().lower()
    text = text.replace(" ", "-")
    text = re.sub(r"/+", "/", text)
    return text.strip("/")


def model_display_name(model_id: str, models: dict | None = None) -> str:
    models = models or {}
    entry = models.get(model_id) or {}
    if entry.get("name"):
        return str(entry["name"])
    slug = model_id.split("/")[-1]
    return slug.replace("-", " ").replace(".", " ").title()


def ranking_row(
    *,
    rank: int,
    model_id: str,
    score: Any,
    note: str,
    models: dict | None = None,
    normalized_score: float | None = None,
    pricing: dict | None = None,
) -> dict:
    models = models or {}
    mid = normalize_model_id(model_id)
    price = pricing
    if price is None:
        entry = models.get(mid) or {}
        if any(entry.get(k) is not None for k in ("input", "output", "context")):
            price = {
                "input": entry.get("input"),
                "output": entry.get("output"),
                "context": entry.get("context"),
                "source": entry.get("price_source") or "catalog",
            }
    row = {
        "rank": rank,
        "model_id": mid,
        "model": model_display_name(mid, models),
        "score": score,
        "note": note,
        "pricing": price,
    }
    if normalized_score is not None:
        row["normalized_score"] = normalized_score
    return row
