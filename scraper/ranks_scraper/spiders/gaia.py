"""HF Gradio space leaderboard — parser owned by this spider."""

from __future__ import annotations

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row
from ranks_scraper.spiders.base import SourceSpider


class GaiaSpider(SourceSpider):
    name = 'gaia'
    source_title = 'GAIA'
    start_urls = ['https://gaia-benchmark-leaderboard.hf.space/']
    browse_url = 'https://huggingface.co/spaces/gaia-benchmark/leaderboard'
    kind = "benchmark"
    engine = "http"
    note_prefix = 'GAIA Gradio leaderboard'

    def parse_body(self, body: str) -> list[dict]:
        rows_out: list[dict] = []
        seen: set[str] = set()
        for cells in self.iter_table_rows(body):
            if len(cells) < 2:
                continue
            joined = " ".join(cells).lower()
            if "model" in joined and any(
                k in joined for k in ("score", "acc", "average", "level")
            ):
                continue
            model_name = None
            score = None
            for cell in cells:
                if model_name is None and any(c.isalpha() for c in cell):
                    cand = cell.strip().split("\n")[0]
                    if cand.lower() not in {
                        "model", "agent", "organisation", "organization", "name"
                    }:
                        model_name = cand
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
                note=f"{self.note_prefix} rank {rank}",
                normalized_score=float(score),
            )
            row["model"] = model_name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

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

    sample = Path(__file__).with_name("gaia_sample.html")
    body = sample.read_text() if sample.exists() else ""
    spider = GaiaSpider()
    print(sample.name, "rankings", len(spider.parse_body(body)) if body else 0)
