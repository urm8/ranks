from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row

class EqBenchSpider(SourceSpider):
    name = "eq_bench"
    source_title = 'EQ-Bench'
    start_urls = ['https://eqbench.com/']
    kind = 'benchmark'
    engine = 'playwright'

    def parse_eq_bench(self, body: str) -> list[dict]:
        rows_out: list[dict] = []
        seen: set[str] = set()
        for cells in self.iter_table_rows(body):
            if len(cells) < 3:
                continue
            joined = " ".join(cells).lower()
            if "model" in joined and "elo" in joined:
                continue
            if "traits" in joined and "abilities" in joined:
                continue
            # '', model, elo, ...
            model_name = cells[1].strip() if len(cells) > 1 else ""
            elo = self.first_number(cells[2]) if len(cells) > 2 else None
            if not model_name or elo is None:
                continue
            if model_name.lower() in {"model", "model▼", "details"}:
                continue
            if elo < 100:  # trait scores are small; Elo is ~1000+
                continue
            mid = self.guess_model_id(model_name)
            if mid in seen:
                continue
            seen.add(mid)
            rank = len(rows_out) + 1
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=f"{elo:g} Elo",
                note=f"EQ-Bench 4 Elo rank {rank}",
            )
            row["model"] = model_name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

    def parse_response(self, response):
        rankings = self.parse_eq_bench(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('eq_bench_sample.html')
    body = sample.read_text() if sample.exists() else ""
    spider = EqBenchSpider()
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
