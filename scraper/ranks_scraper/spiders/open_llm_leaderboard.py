"""Open LLM Leaderboard — ALL rows from formatted JSON API."""

from __future__ import annotations

import json

from ranks_scraper.parsing.normalize import (
    attach_normalized_scores,
    model_display_name,
    normalize_model_id,
)
from ranks_scraper.spiders.base import SourceSpider

class OpenLlmLeaderboardSpider(SourceSpider):
    name = "open_llm_leaderboard"
    source_title = 'Hugging Face Open LLM Leaderboard'
    start_urls = ['https://open-llm-leaderboard-open-llm-leaderboard.hf.space/api/leaderboard/formatted']
    browse_url = 'https://huggingface.co/spaces/open-llm-leaderboard/open_llm_leaderboard'
    kind = 'benchmark'
    engine = 'http'

    def parse_open_llm_formatted(self, body: str) -> list[dict]:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        scored = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            model = entry.get("model") or {}
            name = model.get("name") or entry.get("id") or ""
            mid = normalize_model_id(str(name))
            if not mid:
                continue
            try:
                score_val = float(model.get("average_score"))
            except (TypeError, ValueError):
                continue
            scored.append((score_val, mid, model_display_name(mid)))
        scored.sort(key=lambda x: x[0], reverse=True)
        rows = [
            {
                "rank": idx,
                "model_id": mid,
                "model": display,
                "score": f"{score_val:.2f}",
                "normalized_score": round(score_val, 1),
                "note": "Open LLM Leaderboard average_score",
                "pricing": None,
            }
            for idx, (score_val, mid, display) in enumerate(scored, start=1)
        ]
        return attach_normalized_scores(rows)

    def parse_response(self, response):
        rankings = self.parse_open_llm_formatted(response.text)
        models = {
            r["model_id"]: {
                "name": r["model"],
                "vendor": r["model_id"].split("/")[0] if "/" in r["model_id"] else "unknown",
                "discovered": True,
                "catalog_sources": ["Open LLM Leaderboard"],
            }
            for r in rankings
        }
        return {"rankings": rankings, "models": models, "mentions": [r["model_id"] for r in rankings]}


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('open_llm_leaderboard_sample.json')
    body = sample.read_text() if sample.exists() else ""
    spider = OpenLlmLeaderboardSpider()
    if hasattr(spider, "parse_body") and body:
        out = spider.parse_body(body)
        n = len(out) if isinstance(out, list) else len(out or {})
    elif body:
        class _R:
            text = body
            url = (spider.start_urls or [""])[0]
            status = 200
        parsed = spider.parse_response(_R())
        n = len(parsed.get("rankings") or parsed.get("models") or {})
    else:
        n = 0
    print(sample.name, "parsed", n)
