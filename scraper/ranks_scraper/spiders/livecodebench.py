"""LiveCodeBench leaderboard — HTML table (RANK / MODEL / PASS@1).

The table is filled by client-side JS (`loadData` / `buildLeaderboard`), so this
spider must wait for rendered rows (Playwright), not the empty shell HTML.
"""

from __future__ import annotations

from scrapy_playwright.page import PageMethod

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row
from ranks_scraper.spiders.base import SourceSpider

class LivecodebenchSpider(SourceSpider):
    name = "livecodebench"
    source_title = 'LiveCodeBench'
    start_urls = ['https://livecodebench.github.io/leaderboard.html']
    kind = 'benchmark'
    engine = 'playwright'

    async def start(self):
        for url in self.start_urls:
            yield self.make_source_request(
                url,
                playwright_page_goto_kwargs={"wait_until": "networkidle", "timeout": 60000},
                playwright_page_methods=[PageMethod("wait_for_timeout", 6000)],
            )

    def parse_livecodebench(self, body: str) -> list[dict]:
        """Parse LiveCodeBench Pass@1 table — all rows, no cap."""
        rows_out: list[dict] = []
        seen: set[str] = set()
        for cells in self.iter_table_rows(body):
            if len(cells) < 3:
                continue
            joined = " ".join(cells).lower()
            if "pass@1" in joined and "model" in joined:
                continue
            rank_num = self.first_number(cells[0])
            model_name = cells[1].strip()
            pass1 = self.first_number(cells[2])
            if not model_name or pass1 is None:
                continue
            if model_name.lower() == "model":
                continue
            mid = self.guess_model_id(model_name)
            if mid in seen:
                continue
            seen.add(mid)
            rank = int(rank_num) if rank_num else len(rows_out) + 1
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=f"{pass1:g}%",
                note=f"LiveCodeBench pass@1 rank {rank}",
                normalized_score=float(pass1) if pass1 <= 100 else None,
            )
            row["model"] = model_name
            rows_out.append(row)
        rows_out.sort(key=lambda r: r["rank"])
        return attach_normalized_scores(rows_out)

    def parse_response(self, response):
        rankings = self.parse_livecodebench(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('livecodebench_sample.html')
    body = sample.read_text() if sample.exists() else ""
    spider = LivecodebenchSpider()
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
