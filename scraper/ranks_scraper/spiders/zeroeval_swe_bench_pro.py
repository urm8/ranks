"""ZeroEval swe-bench-pro — dedicated in-spider parser for ALL entries."""

from __future__ import annotations

import json

from ranks_scraper.parsing.normalize import (
    attach_normalized_scores,
    model_display_name,
    normalize_model_id,
)
from ranks_scraper.spiders.base import SourceSpider

BENCHMARK_ID = "swe-bench-pro"

class ZeroevalSweBenchProSpider(SourceSpider):
    name = "zeroeval_swe_bench_pro"
    source_title = 'ZeroEval SWE-bench Pro'
    start_urls = ['https://api.zeroeval.com/leaderboard/benchmarks/swe-bench-pro?top_n=500']
    kind = 'scores'
    engine = 'http'

    def parse_zeroeval_swe_bench_pro_entries(self, body: str) -> tuple[list[dict], int | None]:
        """Return (rankings, total_models_from_api). Parses every entry — no artificial cap."""
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return [], None
        if not isinstance(payload, dict):
            return [], None
        entries = payload.get("entries")
        if not isinstance(entries, list):
            return [], None
        total_models = payload.get("total_models")
        if not isinstance(total_models, int):
            total_models = None

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
            rows.append(
                {
                    "rank": rank,
                    "model_id": model_id,
                    "model": entry.get("model_name") or model_display_name(model_id),
                    "score": f"{normalized:g}/100",
                    "normalized_score": normalized,
                    "note": f"ZeroEval {BENCHMARK_ID} leaderboard rank {rank}",
                    "pricing": pricing,
                }
            )
        rows.sort(key=lambda r: r["rank"])
        return attach_normalized_scores(rows), total_models

    def parse_response(self, response):
        rankings, total_models = self.parse_zeroeval_swe_bench_pro_entries(response.text)
        if total_models is not None and total_models != len(rankings):
            self.logger.warning(
                "%s: parsed rankings=%d but API total_models=%d (entries may be truncated by top_n)",
                self.name,
                len(rankings),
                total_models,
            )
        else:
            self.logger.info(
                "%s: parsed rankings=%d%s",
                self.name,
                len(rankings),
                f" (matches total_models={total_models})" if total_models is not None else "",
            )
        models = {
            row["model_id"]: {
                "name": row["model"],
                "vendor": row["model_id"].split("/")[0] if "/" in row["model_id"] else "unknown",
                "discovered": True,
                "catalog_sources": ["ZeroEval"],
                "price_source": (row.get("pricing") or {}).get("source") or "ZeroEval leaderboard",
                "input": (row.get("pricing") or {}).get("input"),
                "output": (row.get("pricing") or {}).get("output"),
                "context": (row.get("pricing") or {}).get("context"),
            }
            for row in rankings
        }
        return {"rankings": rankings, "models": models, "mentions": [r["model_id"] for r in rankings]}


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('zeroeval_swe_bench_pro_sample.json')
    body = sample.read_text() if sample.exists() else ""
    spider = ZeroevalSweBenchProSpider()
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
