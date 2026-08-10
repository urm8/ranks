from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row

class SwebenchSpider(SourceSpider):
    name = "swebench"
    source_title = 'SWE-bench'
    start_urls = ['https://www.swebench.com/']
    kind = 'benchmark'
    engine = 'playwright'  # leaderboard table is client-rendered

    def parse_swebench(self, body: str) -> list[dict]:
        rows_out: list[dict] = []
        seen: set[str] = set()
        for cells in self.iter_table_rows(body):
            if len(cells) < 3:
                continue
            joined = " ".join(cells).lower()
            if "resolved" in joined and "model" in joined:
                continue
            model_name = cells[1].replace("🆕", "").strip().split("\n")[0]
            resolved = self.first_number(cells[2])
            if not model_name or resolved is None:
                continue
            if model_name.lower() == "model":
                continue
            mid = self.guess_model_id(model_name)
            if mid in seen:
                continue
            seen.add(mid)
            rank = len(rows_out) + 1
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=f"{resolved:g}%",
                note=f"SWE-bench % resolved rank {rank}",
                normalized_score=float(resolved) if resolved <= 100 else None,
            )
            row["model"] = model_name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

    def parse_response(self, response):
        rankings = self.parse_swebench(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('swebench_sample.html')
    body = sample.read_text() if sample.exists() else ""
    spider = SwebenchSpider()
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
