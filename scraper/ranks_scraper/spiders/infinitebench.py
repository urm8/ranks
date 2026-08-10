"""InfiniteBench GitHub README — parser owned by this spider.

The README publishes a transposed score table (rows = tasks, columns = models).
We average each model column across tasks into a single ranking score.
"""

from __future__ import annotations

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row
from ranks_scraper.spiders.base import SourceSpider


# Task / schema tables that are not model leaderboards.
_NON_MODEL_HEADERS = {
    "task name",
    "context",
    "# examples",
    "avg input tokens",
    "avg output tokens",
    "description",
    "argument to specify in --task",
    "name",
    "last commit message",
    "last commit date",
}


class InfinitebenchSpider(SourceSpider):
    name = "infinitebench"
    source_title = "InfiniteBench"
    start_urls = ["https://github.com/OpenBMB/InfiniteBench"]
    kind = "benchmark"
    engine = "http"
    note_prefix = "InfiniteBench GitHub"

    def _cell_score(self, text: str) -> float | None:
        raw = (text or "").strip().lower()
        if not raw or raw in {"-", "–", "—", "n/a", "na"}:
            return None
        # "< 5%" style thresholds → treat as mid-bin estimate
        if raw.startswith("<"):
            val = self.first_number(raw)
            return float(val) if val is not None else None
        return self.first_number(raw.replace("%", ""))

    def parse_transposed_score_table(self, body: str) -> list[dict]:
        """Parse Task×Model tables; return models ranked by mean task score."""
        best: dict[str, tuple[str, float, int]] = {}  # mid -> (display, sum, n)

        rows = list(self.iter_table_rows(body))
        i = 0
        while i < len(rows):
            cells = rows[i]
            if len(cells) < 3:
                i += 1
                continue
            header_l = [c.strip().lower() for c in cells]
            if header_l[0] not in {"task name", "task"}:
                i += 1
                continue
            model_headers = []
            for h in cells[1:]:
                name = h.strip().split("\n")[0].strip()
                if not name or name.lower() in _NON_MODEL_HEADERS:
                    model_headers.append(None)
                else:
                    model_headers.append(name)
            if sum(1 for h in model_headers if h) < 2:
                i += 1
                continue
            # Looks like a model score matrix when several headers look like models
            # and the next rows contain percentages.
            i += 1
            while i < len(rows):
                data = rows[i]
                if not data or data[0].strip().lower() in {"task name", "task"}:
                    break
                if len(data) < 2:
                    i += 1
                    continue
                # Stop if this is another schema table (non-score)
                joined = " ".join(data).lower()
                if "argument to specify" in joined or "avg input tokens" in joined:
                    break
                for col, model_name in enumerate(model_headers, start=1):
                    if model_name is None or col >= len(data):
                        continue
                    score = self._cell_score(data[col])
                    if score is None or not (0 <= score <= 100):
                        continue
                    mid = self.guess_model_id(model_name)
                    if not mid:
                        continue
                    display, total, n = best.get(mid, (model_name, 0.0, 0))
                    best[mid] = (display, total + score, n + 1)
                i += 1
            continue

        ranked = sorted(
            (
                (mid, display, total / n)
                for mid, (display, total, n) in best.items()
                if n > 0
            ),
            key=lambda t: t[2],
            reverse=True,
        )
        rows_out: list[dict] = []
        for rank, (mid, display, avg) in enumerate(ranked, start=1):
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=f"{avg:.2f}%",
                note=f"{self.note_prefix} mean task score rank {rank}",
                normalized_score=float(avg),
            )
            row["model"] = display
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

    def parse_body(self, body: str) -> list[dict]:
        return self.parse_transposed_score_table(body)

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

    sample = Path(__file__).with_name("infinitebench_sample.html")
    body = sample.read_text() if sample.exists() else ""
    spider = InfinitebenchSpider()
    print(sample.name, "rankings", len(spider.parse_body(body)) if body else 0)
