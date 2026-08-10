"""LLM Stats leaderboard — parser owned by this spider."""

from __future__ import annotations

import json
from typing import Any

from ranks_scraper.parsing.normalize import (
    attach_normalized_scores,
    model_display_name,
    normalize_model_id,
    ranking_row,
)
from ranks_scraper.spiders.base import SourceSpider


class LlmStatsLeaderboardSpider(SourceSpider):
    name = "llm_stats_leaderboard"
    source_title = 'LLM Stats leaderboard'
    start_urls = ['https://llm-stats.com/leaderboards/llm-leaderboard']
    kind = "benchmark"
    engine = "http"
    note_prefix = "LLM Stats leaderboard"
    ze_id = "llm-stats"

    def parse_zeroeval_benchmark(self, body: str, *, ze_id: str) -> list[dict]:
        try:
            payload: Any = json.loads(body)
        except json.JSONDecodeError:
            return []
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            return []

        rows: list[dict] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            short = normalize_model_id(entry.get("model_id") or "")
            if not short:
                continue
            org = entry.get("organization_id") or entry.get("provider_id") or ""
            model_id = short if "/" in short else normalize_model_id(f"{org}/{short}" if org else short)
            raw = entry.get("normalized_score")
            if raw is None:
                raw = entry.get("benchmark_score")
            try:
                numeric = float(raw)
            except (TypeError, ValueError):
                continue
            normalized = round(numeric * 100.0, 1) if numeric <= 1.0 else round(numeric, 1)
            rank = int(entry.get("rank") or len(rows) + 1)
            pricing = None
            if entry.get("input_cost_per_million") is not None or entry.get("output_cost_per_million") is not None:
                pricing = {
                    "input": entry.get("input_cost_per_million"),
                    "output": entry.get("output_cost_per_million"),
                    "context": entry.get("context_window"),
                    "source": "ZeroEval leaderboard",
                }
            name = entry.get("model_name") or model_display_name(model_id)
            rows.append(
                {
                    "rank": rank,
                    "model_id": model_id,
                    "model": name,
                    "score": f"{normalized:g}/100",
                    "normalized_score": normalized,
                    "note": f"ZeroEval {ze_id} leaderboard rank {rank}",
                    "pricing": pricing,
                }
            )
        rows.sort(key=lambda r: r["rank"])
        return attach_normalized_scores(rows)

    def models_from_ze_rankings(self, rankings: list[dict], *, catalog_source: str = "ZeroEval") -> dict[str, dict]:
        models: dict[str, dict] = {}
        for row in rankings:
            mid = row["model_id"]
            models[mid] = {
                "name": row["model"],
                "vendor": mid.split("/")[0] if "/" in mid else "unknown",
                "discovered": True,
                "catalog_sources": [catalog_source],
                "price_source": (row.get("pricing") or {}).get("source") or f"{catalog_source} leaderboard",
                "input": (row.get("pricing") or {}).get("input"),
                "output": (row.get("pricing") or {}).get("output"),
                "context": (row.get("pricing") or {}).get("context"),
            }
        return models

    def parse_llm_stats_benchmarks_catalog(self, body: str) -> list[dict]:
        """Parse ZeroEval /leaderboard/benchmarks list into a lightweight catalog ranking.

        This source is an overview of benchmarks (not a model leaderboard). We surface
        the top benchmarks by entry count as informational rows with synthetic ids.
        """
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return []
        items = payload if isinstance(payload, list) else payload.get("benchmarks") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []
        scored: list[tuple[int, str, str]] = []
        for entry in items:
            if not isinstance(entry, dict):
                continue
            bid = str(entry.get("id") or entry.get("slug") or entry.get("benchmark_id") or "")
            name = str(entry.get("name") or bid)
            count = entry.get("entries_count") or entry.get("num_entries") or entry.get("models_count") or 0
            try:
                count_i = int(count)
            except (TypeError, ValueError):
                count_i = 0
            if not bid:
                continue
            scored.append((count_i, bid, name))
        scored.sort(key=lambda t: -t[0])
        rows: list[dict] = []
        for count_i, bid, name in scored:
            rank = len(rows) + 1
            mid = f"benchmark/{bid}"
            rows.append(
                ranking_row(
                    rank=rank,
                    model_id=mid,
                    score=f"{count_i} entries",
                    note=f"LLM Stats benchmark catalog by entry count rank {rank}",
                )
            )
            rows[-1]["model"] = name
        return attach_normalized_scores(rows)

    def parse_llm_stats_benchmark_table(self, 
        body: str,
        *,
        note_prefix: str,
        ze_id: str | None = None,
    ) -> list[dict]:
        stripped = body.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            if '"entries"' in stripped[:2000] and ze_id:
                rows = self.parse_zeroeval_benchmark(stripped, ze_id=ze_id)
                if rows:
                    return rows
            if "benchmark" in stripped[:500].lower() or '"id"' in stripped[:500]:
                rows = self.parse_llm_stats_benchmarks_catalog(stripped)
                if rows:
                    return rows

        rows_out: list[dict] = []
        seen: set[str] = set()
        for cells in self.iter_table_rows(body):
            if len(cells) < 3:
                continue
            joined = " ".join(cells).lower()
            if "model" in joined and "score" in joined:
                continue
            rank_num = self.first_number(cells[0])
            model_block = cells[1]
            score_cell = cells[2]
            if rank_num is None:
                model_block = cells[1] if len(cells) > 1 else cells[0]
                score_cell = cells[2] if len(cells) > 2 else ""
                if not self.first_number(score_cell):
                    continue
            lines = [ln.strip() for ln in model_block.split("\n") if ln.strip()]
            if not lines:
                continue
            model_name = lines[0]
            if model_name.lower() in {"model", "#"}:
                continue
            creator = lines[1] if len(lines) > 1 else ""
            score_val = self.first_number(score_cell)
            if score_val is None:
                continue
            mid = self.guess_model_id(model_name, creator)
            if not mid or mid in seen:
                continue
            seen.add(mid)
            if 0 <= score_val <= 1:
                normalized = round(score_val * 100.0, 1)
                score_str = f"{normalized:g}/100"
            elif 0 <= score_val <= 100:
                normalized = round(score_val, 1)
                score_str = f"{normalized:g}/100"
            else:
                normalized = None
                score_str = f"{score_val:g}"
            rank = len(rows_out) + 1
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=score_str,
                note=f"{note_prefix} rank {int(rank_num) if rank_num else rank}",
                normalized_score=normalized,
            )
            row["model"] = model_name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)
    def parse_response(self, response):
        rankings = self.parse_llm_stats_benchmark_table(
            response.text, note_prefix=self.note_prefix, ze_id=self.ze_id
        )
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name("llm_stats_leaderboard_sample.html")
    body = sample.read_text() if sample.exists() else ""
    spider = LlmStatsLeaderboardSpider()
    n = len(
        spider.parse_llm_stats_benchmark_table(
            body, note_prefix=spider.note_prefix, ze_id=spider.ze_id
        )
    ) if body else 0
    print(sample.name, "rankings", n)
