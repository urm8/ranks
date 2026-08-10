"""WritingBench GitHub — best-effort reference spider.

The README links to Hugging Face / ModelScope leaderboards and only embeds
pipeline images — no HTML score table. Rankings stay empty unless a table is
added. Prefer those external leaderboards for live scores.
"""

from __future__ import annotations

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row
from ranks_scraper.spiders.base import SourceSpider


class WritingbenchSpider(SourceSpider):
    name = "writingbench"
    source_title = "WritingBench"
    start_urls = ["https://github.com/X-PLUG/WritingBench"]
    kind = "benchmark"
    engine = "http"
    note_prefix = "WritingBench GitHub"

    def parse_readme_score_table(self, body: str, *, note_prefix: str | None = None) -> list[dict]:
        note_prefix = note_prefix or self.note_prefix
        rows_out: list[dict] = []
        seen: set[str] = set()
        model_idx: int | None = None
        score_idx: int | None = None
        for cells in self.iter_table_rows(body):
            if len(cells) < 2:
                continue
            lower = [c.strip().lower() for c in cells]
            joined = " ".join(lower)
            if "model" in joined and any(
                k in joined for k in ("score", "pass", "acc", "resolved", "win", "rating")
            ):
                model_idx = next((i for i, c in enumerate(lower) if c == "model"), None)
                score_idx = next(
                    (
                        i
                        for i, c in enumerate(lower)
                        if any(
                            k in c
                            for k in ("score", "pass", "acc", "resolved", "win", "rating")
                        )
                    ),
                    None,
                )
                continue
            if model_idx is None or score_idx is None:
                continue
            if model_idx >= len(cells) or score_idx >= len(cells):
                continue
            model_name = cells[model_idx].strip().split("\n")[0]
            if not model_name or model_name.lower() in {"model", "method", "system", "name"}:
                continue
            score = self.first_number(cells[score_idx])
            if score is None or not (0 <= score <= 100):
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
                note=f"{note_prefix} rank {rank}",
                normalized_score=float(score),
            )
            row["model"] = model_name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

    def parse_body(self, body: str) -> list[dict]:
        return self.parse_readme_score_table(body)

    def parse_response(self, response):
        rankings = self.parse_body(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name("writingbench_sample.html")
    body = sample.read_text() if sample.exists() else ""
    spider = WritingbenchSpider()
    print(sample.name, "rankings", len(spider.parse_body(body)) if body else 0)
