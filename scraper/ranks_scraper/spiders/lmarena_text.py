"""LMArena overall leaderboard — parser owned by this spider."""

from __future__ import annotations

import json
import re
from typing import Any

from ranks_scraper.parsing.normalize import (
    attach_normalized_scores,
    normalize_model_id,
    ranking_row,
)
from ranks_scraper.spiders.base import SourceSpider


class LmarenaTextSpider(SourceSpider):
    name = 'lmarena_text'
    source_title = 'LMArena text overall'
    start_urls = ['https://arena.ai/leaderboard/text']
    kind = "benchmark"
    engine = "http"
    arena_category = 'overall'

    CATEGORY_NOTES = {
        "overall": "LMArena text overall Elo",
        "coding": "LMArena coding Elo",
        "math": "LMArena math Elo",
        "creative-writing": "LMArena creative writing Elo",
    }

    def _split_arena_model_cell(self, block: str) -> tuple[str, str]:
        """Split collapsed 'Vendor slug Vendor · License' cells into (slug, org)."""
        text = (block or "").strip()
        if not text:
            return "", ""
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if len(lines) >= 2:
            return lines[0], lines[1]

        org_tail = ""
        left = text
        if " · " in text:
            left, org_tail = text.split(" · ", 1)

        tokens = left.split()
        slug = None
        for tok in tokens:
            if not re.fullmatch(r"[a-z0-9][\w.+-]*", tok):
                continue
            if "-" in tok or any(ch.isdigit() for ch in tok) or tok.startswith(
                (
                    "gpt",
                    "o1",
                    "o3",
                    "o4",
                    "claude",
                    "gemini",
                    "grok",
                    "qwen",
                    "kimi",
                    "glm",
                    "llama",
                    "deepseek",
                    "mistral",
                    "command",
                )
            ):
                slug = tok
                break
        if slug:
            org_bits = [t for t in tokens if t != slug]
            org_line = " ".join(org_bits)
            if org_tail:
                org_line = f"{org_line} · {org_tail}".strip(" ·")
            return slug, org_line
        return (tokens[0] if tokens else text), org_tail

    def _arena_model_id(self, slug: str, org_line: str = "") -> str:
        slug = normalize_model_id(slug.replace(" ", "-"))
        if "/" in slug:
            return slug
        vendor = self.vendor_from_name(slug) or self.vendor_from_name(org_line) or "arena"
        clean = re.sub(r"-text$", "", slug)
        for prefix in (f"{vendor}-", "anthropic-", "openai-", "google-", "meta-"):
            if clean.startswith(prefix):
                clean = clean[len(prefix) :]
                break
        return normalize_model_id(f"{vendor}/{clean}")

    def parse_lmarena_ratings_json(self, payload: Any, *, category: str) -> list[dict]:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return []
        if not isinstance(payload, dict):
            return []
        scored: list[tuple[int, float, str]] = []
        for slug, buckets in payload.items():
            if not isinstance(buckets, dict):
                continue
            bucket = buckets.get("0") or buckets.get(0)
            if not isinstance(bucket, dict):
                best = None
                for b in buckets.values():
                    if isinstance(b, dict) and isinstance(b.get("rating"), (int, float)):
                        if best is None or b["rating"] > best["rating"]:
                            best = b
                bucket = best
            if not isinstance(bucket, dict):
                continue
            rating = bucket.get("rating")
            if not isinstance(rating, (int, float)):
                continue
            rank = bucket.get("rankUpper") or bucket.get("rank") or 9999
            scored.append((int(rank), float(rating), str(slug)))
        scored.sort(key=lambda t: (t[0], -t[1]))
        note = self.CATEGORY_NOTES.get(category, f"LMArena {category} Elo")
        rows: list[dict] = []
        seen: set[str] = set()
        for rank_hint, rating, slug in scored:
            mid = self._arena_model_id(slug)
            if mid in seen:
                continue
            seen.add(mid)
            rank = len(rows) + 1
            rows.append(
                ranking_row(
                    rank=rank,
                    model_id=mid,
                    score=f"{rating:.0f} Elo",
                    note=f"{note} rank {rank_hint}",
                )
            )
            rows[-1]["model"] = slug
        return attach_normalized_scores(rows)

    def parse_lmarena_table(self, body: str, *, category: str) -> list[dict]:
        note = self.CATEGORY_NOTES.get(category, f"LMArena {category} Elo")
        rows_out: list[dict] = []
        seen: set[str] = set()
        for cells in self.iter_table_rows(body):
            if len(cells) < 4:
                continue
            joined = " ".join(cells).lower()
            if "rank" in joined and "model" in joined and "score" in joined:
                continue
            rank_num = self.first_number(cells[0])
            if rank_num is None:
                continue
            model_block = cells[2] if len(cells) > 2 else cells[1]
            model_name, org_line = self._split_arena_model_cell(model_block)
            if not model_name:
                continue
            score_cell = cells[3] if len(cells) > 3 else cells[-1]
            elo = self.first_number(score_cell)
            if elo is None or elo < 500:
                continue
            mid = self._arena_model_id(model_name, org_line)
            if mid in seen:
                continue
            seen.add(mid)
            rank = len(rows_out) + 1
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=f"{elo:g} Elo",
                note=f"{note} rank {int(rank_num)}",
            )
            row["model"] = model_name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

    def parse_lmarena(self, body: str, *, category: str) -> list[dict]:
        stripped = body.lstrip()
        if stripped.startswith("{"):
            rows = self.parse_lmarena_ratings_json(stripped, category=category)
            if rows:
                return rows
        return self.parse_lmarena_table(body, category=category)
    def parse_response(self, response):
        rankings = self.parse_lmarena(response.text, category=self.arena_category)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name(f"{Path(__file__).stem}_sample.html")
    body = sample.read_text() if sample.exists() else ""
    spider = LmarenaTextSpider()
    rows = spider.parse_lmarena(body, category=spider.arena_category) if body else []
    print(sample.name, "rankings", len(rows))
