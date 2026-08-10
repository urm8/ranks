"""CRAG arXiv HTML — parser owned by this spider.

Parses Model/System + Accuracy tables from the paper HTML. Prefers the first
Accuracy value seen per model (typically the LLM-only / primary comparison).
"""

from __future__ import annotations

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row
from ranks_scraper.spiders.base import SourceSpider

_SKIP_NAMES = {
    "",
    "model",
    "method",
    "system",
    "name",
    "rank",
    "llm only",
    "task 1",
    "task 2",
    "task 3",
    "equal",
    "weighted",
    "traffic",
    "perfect",
    "acc.",
    "hall.",
    "miss.",
    "accurate",
    "incorrect",
    "missing",
    "average",
    "chatgpt",
    "llama 3",
}


class CragSpider(SourceSpider):
    name = "crag"
    source_title = "CRAG"
    start_urls = ["https://arxiv.org/html/2406.04744v2"]
    kind = "benchmark"
    engine = "http"
    note_prefix = "CRAG arXiv"

    @staticmethod
    def _looks_like_model(name: str) -> bool:
        text = (name or "").strip()
        if not text or not any(c.isalpha() for c in text):
            return False
        # Pure numeric / percent labels are metrics, not models
        stripped = text.replace("%", "").replace(",", "").strip()
        try:
            float(stripped)
            return False
        except ValueError:
            return True

    def parse_model_accuracy_tables(self, body: str) -> list[dict]:
        seen: set[str] = set()
        rows_out: list[dict] = []
        header_model_idx: int | None = None
        header_acc_idx: int | None = None
        for cells in self.iter_table_rows(body):
            if len(cells) < 2:
                continue
            lower_cells = [c.strip().lower() for c in cells]
            joined = " ".join(lower_cells)

            # Any header-like row resets column mapping
            looks_header = any(
                c in {"model", "system", "accuracy", "acc.", "precision", "recall", "f1 score"}
                for c in lower_cells
            ) or ("accuracy" in joined and ("model" in joined or "system" in joined))
            if looks_header:
                header_model_idx = None
                header_acc_idx = None
                if ("model" in joined or "system" in joined) and any(
                    k in joined for k in ("accuracy", "acc.", "acc)")
                ):
                    for idx, cell in enumerate(lower_cells):
                        if header_model_idx is None and cell in {"model", "system"}:
                            header_model_idx = idx
                        if header_acc_idx is None and (
                            cell.startswith("accuracy") or cell in {"acc.", "acc"}
                        ):
                            header_acc_idx = idx
                continue

            if header_model_idx is None or header_acc_idx is None:
                continue
            if header_model_idx >= len(cells) or header_acc_idx >= len(cells):
                continue

            model_name = cells[header_model_idx].strip().split("\n")[0].strip()
            if not model_name or model_name.lower() in _SKIP_NAMES:
                continue
            if model_name.lower().startswith("task "):
                continue
            if not self._looks_like_model(model_name):
                continue

            score = self.first_number(cells[header_acc_idx])
            if score is None or not (0 <= score <= 100):
                continue

            mid = self.guess_model_id(model_name)
            if not mid or mid in seen:
                continue
            # Reject ids that are just unknown/<number>
            slug = mid.split("/", 1)[-1]
            if slug.replace(".", "").replace("-", "").isdigit():
                continue
            seen.add(mid)
            row = ranking_row(
                rank=0,
                model_id=mid,
                score=f"{score:g}%",
                note="",
                normalized_score=float(score),
            )
            row["model"] = model_name
            rows_out.append(row)

        # Prefer higher accuracy; keep first-seen on ties via stable sort after reverse
        rows_out.sort(
            key=lambda r: float(r.get("normalized_score") or 0), reverse=True
        )
        for i, row in enumerate(rows_out, start=1):
            row["rank"] = i
            row["note"] = f"{self.note_prefix} accuracy rank {i}"
        return attach_normalized_scores(rows_out)

    def parse_body(self, body: str) -> list[dict]:
        return self.parse_model_accuracy_tables(body)

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

    sample = Path(__file__).with_name("crag_sample.html")
    body = sample.read_text() if sample.exists() else ""
    spider = CragSpider()
    print(sample.name, "rankings", len(spider.parse_body(body)) if body else 0)
