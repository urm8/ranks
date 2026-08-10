"""LLM Stats benchmarks catalog — parser owned by this spider."""

from __future__ import annotations

import json

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row
from ranks_scraper.spiders.base import SourceSpider


class LlmStatsBenchmarksSpider(SourceSpider):
    name = "llm_stats_benchmarks"
    source_title = 'LLM Stats benchmark overview'
    start_urls = ['https://api.zeroeval.com/leaderboard/benchmarks']
    kind = "catalog"
    engine = "http"

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
    def parse_response(self, response):
        rankings = self.parse_llm_stats_benchmarks_catalog(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name("llm_stats_benchmarks_sample.json")
    body = sample.read_text() if sample.exists() else ""
    spider = LlmStatsBenchmarksSpider()
    print(sample.name, "rankings", len(spider.parse_llm_stats_benchmarks_catalog(body)) if body else 0)
