"""ZeroEval/LLM Stats benchmark JSON — parser owned by this spider."""

from __future__ import annotations

import json
from typing import Any

from ranks_scraper.parsing.normalize import (
    attach_normalized_scores,
    model_display_name,
    normalize_model_id,
)
from ranks_scraper.spiders.base import SourceSpider


class LlmStatsFramesSpider(SourceSpider):
    name = 'llm_stats_frames'
    source_title = 'LLM Stats FRAMES'
    start_urls = ['https://api.zeroeval.com/leaderboard/benchmarks/frames?top_n=500']
    browse_url = 'https://llm-stats.com/benchmarks/frames'
    kind = "benchmark"
    engine = "http"
    ze_id = 'frames'

    def parse_body(self, body: str) -> list[dict]:
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
            model_id = (
                short
                if "/" in short
                else normalize_model_id(f"{org}/{short}" if org else short)
            )
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
            if (
                entry.get("input_cost_per_million") is not None
                or entry.get("output_cost_per_million") is not None
            ):
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
                    "note": f"ZeroEval {self.ze_id} leaderboard rank {rank}",
                    "pricing": pricing,
                }
            )
        rows.sort(key=lambda r: r["rank"])
        return attach_normalized_scores(rows)

    def parse_response(self, response):
        rankings = self.parse_body(response.text)
        models = self.models_from_rankings(
            rankings, catalog_source="LLM Stats / ZeroEval"
        )
        # attach pricing fields onto models
        for row in rankings:
            mid = row["model_id"]
            pricing = row.get("pricing") or {}
            if mid in models:
                models[mid].update(
                    {
                        "price_source": pricing.get("source")
                        or "LLM Stats / ZeroEval leaderboard",
                        "input": pricing.get("input"),
                        "output": pricing.get("output"),
                        "context": pricing.get("context"),
                    }
                )
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name("llm_stats_frames_sample.json")
    body = sample.read_text() if sample.exists() else ""
    spider = LlmStatsFramesSpider()
    print(sample.name, "rankings", len(spider.parse_body(body)) if body else 0)
