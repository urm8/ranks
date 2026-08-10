from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

import re

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row

class WebarenaSpider(SourceSpider):
    name = "webarena"
    source_title = 'WebArena'
    start_urls = ['https://webarena.dev/']
    kind = 'benchmark'
    engine = 'playwright'

    def parse_webarena(self, body: str) -> list[dict]:
        rows_out: list[dict] = []
        seen: set[str] = set()
        for cells in self.iter_table_rows(body):
            if len(cells) < 2:
                continue
            joined = " ".join(cells).lower()
            if "success" in joined and "model" in joined:
                continue
            model_name = cells[0].strip()
            score = self.first_number(cells[1]) if len(cells) > 1 else None
            if not model_name or score is None:
                continue
            mid = self.guess_model_id(model_name)
            if mid in seen:
                continue
            seen.add(mid)
            rank = len(rows_out) + 1
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=f"{score:g}%",
                note=f"WebArena table rank {rank}",
                normalized_score=float(score) if score <= 100 else None,
            )
            row["model"] = model_name
            rows_out.append(row)
        if rows_out:
            return attach_normalized_scores(rows_out)

        # Landing page is often a project index without scores — return empty rather than inventing.
        text = self.strip_tags(body)
        if re.search(r"webarena", text, re.I):
            return []
        return []

    def parse_response(self, response):
        rankings = self.parse_webarena(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('webarena_sample.html')
    body = sample.read_text() if sample.exists() else ""
    spider = WebarenaSpider()
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
