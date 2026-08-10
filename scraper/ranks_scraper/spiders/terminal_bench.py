from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row

class TerminalBenchSpider(SourceSpider):
    name = "terminal_bench"
    source_title = 'Terminal-Bench'
    start_urls = ['https://www.tbench.ai/leaderboard/terminal-bench/2.0']
    browse_url = 'https://www.tbench.ai/leaderboard'
    kind = 'benchmark'
    engine = 'http'

    def parse_terminal_bench(self, body: str) -> list[dict]:
        rows_out: list[dict] = []
        seen: set[str] = set()
        for cells in self.iter_table_rows(body):
            if len(cells) < 2:
                continue
            joined = " ".join(cells).lower()
            if ("agent" in joined or "model" in joined) and ("score" in joined or "resolved" in joined or "accuracy" in joined):
                continue
            model_name = None
            score = None
            for cell in cells:
                lower = cell.lower()
                if model_name is None and any(c.isalpha() for c in cell):
                    if lower not in {"agent", "model", "rank", "framework"}:
                        model_name = cell.strip().split("\n")[0]
                val = self.first_number(cell)
                if val is not None and 0 <= val <= 100:
                    score = val
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
                note=f"Terminal-Bench rank {rank}",
                normalized_score=float(score),
            )
            row["model"] = model_name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

    def parse_response(self, response):
        rankings = self.parse_terminal_bench(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('terminal_bench_sample.html')
    body = sample.read_text() if sample.exists() else ""
    spider = TerminalBenchSpider()
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
