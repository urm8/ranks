from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row

class BfclSpider(SourceSpider):
    name = "bfcl"
    source_title = 'Berkeley Function Calling Leaderboard'
    start_urls = ['https://gorilla.cs.berkeley.edu/leaderboard.html']
    kind = 'benchmark'
    engine = 'playwright'

    def parse_bfcl(self, body: str) -> list[dict]:
        """BFCL V4 table: rank, overall score, model name, ..."""
        rows_out: list[dict] = []
        seen: set[str] = set()
        for cells in self.iter_table_rows(body):
            if len(cells) < 3:
                continue
            joined = " ".join(cells).lower()
            if "agentic" in joined and "multi turn" in joined:
                continue
            rank_num = self.first_number(cells[0])
            # Observed: [rank, overall, model_name, ...]
            overall = self.first_number(cells[1]) if len(cells) > 1 else None
            model_name = cells[2].strip() if len(cells) > 2 else ""
            if overall is None or not model_name:
                # alternate: rank, model, score
                model_name = cells[1].strip() if len(cells) > 1 else ""
                overall = self.first_number(cells[2]) if len(cells) > 2 else None
            if not model_name or overall is None or rank_num is None:
                continue
            # model names look like Claude-Opus-4-5-20251101 (FC)
            if overall > 100:
                continue
            mid = self.guess_model_id(model_name.replace("(FC)", "").replace("(Prompt)", "").strip())
            if mid in seen:
                continue
            seen.add(mid)
            rank = len(rows_out) + 1
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=f"{overall:g}%",
                note=f"BFCL overall rank {int(rank_num)}",
                normalized_score=float(overall),
            )
            row["model"] = model_name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

    def parse_response(self, response):
        rankings = self.parse_bfcl(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('bfcl_sample.html')
    body = sample.read_text() if sample.exists() else ""
    spider = BfclSpider()
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
