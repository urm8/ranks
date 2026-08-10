"""LongBench / LongBench v2 — parser owned by this spider.

The GitHub README only embeds score charts as images (no HTML score table).
This spider scrapes the project leaderboard at longbench2.github.io instead.
"""

from __future__ import annotations

import re

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row
from ranks_scraper.spiders.base import SourceSpider


class LongbenchSpider(SourceSpider):
    name = "longbench"
    source_title = "LongBench / LongBench v2"
    start_urls = ["https://longbench2.github.io/"]
    browse_url = "https://longbench2.github.io/#leaderboard"
    kind = "benchmark"
    engine = "http"
    note_prefix = "LongBench v2 leaderboard"

    @staticmethod
    def _clean_model_name(raw: str) -> str:
        text = (raw or "").strip()
        # Drop emoji / vendor suffix markers like "🧠 Google"
        text = re.sub(r"[\U0001F300-\U0001FAFF]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        # Prefer the model token before a trailing org label if present
        # e.g. "Gemini-2.5-Pro Google" → keep full display, guess_model_id handles vendor
        return text

    def _overall_score(self, cells: list[str], overall_idx: int) -> float | None:
        """Pick Overall %, preferring the w/ CoT twin when the base cell is '-'."""
        candidates: list[float] = []
        for idx in (overall_idx, overall_idx + 1):
            if idx >= len(cells):
                continue
            raw = (cells[idx] or "").strip()
            if not raw or raw in {"-", "–", "—"}:
                continue
            val = self.first_number(raw.replace("%", ""))
            if val is not None and 0 <= val <= 100:
                candidates.append(val)
        if not candidates:
            return None
        # When both w/o and w/ CoT exist, prefer CoT (second); else the only value.
        return candidates[-1]

    def parse_leaderboard(self, body: str) -> list[dict]:
        rows_out: list[dict] = []
        seen: set[str] = set()
        model_idx: int | None = None
        overall_idx: int | None = None

        for cells in self.iter_table_rows(body):
            if len(cells) < 2:
                continue
            lower = [c.strip().lower() for c in cells]
            joined = " ".join(lower)

            if "model" in joined and "overall" in joined:
                model_idx = None
                overall_idx = None
                for idx, cell in enumerate(lower):
                    if model_idx is None and cell == "model":
                        model_idx = idx
                    if overall_idx is None and cell.startswith("overall"):
                        overall_idx = idx
                continue

            if model_idx is None or overall_idx is None:
                continue
            if model_idx >= len(cells):
                continue

            model_name = self._clean_model_name(
                cells[model_idx].strip().split("\n")[0]
            )
            if not model_name or model_name.lower() in {
                "model",
                "w/ cot",
                "w/o cot",
                "",
            }:
                continue

            score = self._overall_score(cells, overall_idx)
            if score is None:
                continue

            mid = self.guess_model_id(model_name)
            if not mid or mid in seen:
                continue
            # Skip non-model baselines on the public board
            if mid in {"unknown/human", "unknown/random"} or model_name.lower() in {
                "human",
                "random",
            }:
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

    def parse_body(self, body: str) -> list[dict]:
        return self.parse_leaderboard(body)

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

    sample = Path(__file__).with_name("longbench_sample.html")
    body = sample.read_text() if sample.exists() else ""
    spider = LongbenchSpider()
    print(sample.name, "rankings", len(spider.parse_body(body)) if body else 0)
