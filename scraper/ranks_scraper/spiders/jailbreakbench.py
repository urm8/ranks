from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

import re

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row

class JailbreakbenchSpider(SourceSpider):
    name = "jailbreakbench"
    source_title = 'JailbreakBench / HarmBench'
    start_urls = ['https://jailbreakbench.github.io/']
    kind = 'benchmark'
    engine = 'playwright'

    def _modelish(self, text: str) -> bool:
        return bool(re.search(r"[A-Za-z]", text)) and len(text.strip()) >= 3

    def parse_jailbreakbench(self, body: str) -> list[dict]:
        """Parse defense/attack tables — unique models by appearance order."""
        rows_out: list[dict] = []
        seen: set[str] = set()
        for cells in self.iter_table_rows(body):
            if len(cells) < 2:
                continue
            joined = " ".join(cells).lower()
            if "model" in joined and ("defense" in joined or "threat" in joined or "date" in joined):
                continue
            model_name = None
            metric = None
            for cell in cells:
                lower = cell.lower()
                if model_name is None and self._modelish(cell):
                    if lower not in {"model", "defense", "paper", "name", "date"}:
                        model_name = cell.strip()
                val = self.first_number(cell)
                if val is not None:
                    metric = val
            if not model_name:
                continue
            mid = self.guess_model_id(model_name)
            if mid in seen:
                continue
            seen.add(mid)
            rank = len(rows_out) + 1
            score = f"{metric:g}" if metric is not None else "listed"
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=score,
                note=f"JailbreakBench table rank {rank}",
            )
            row["model"] = model_name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

    def parse_response(self, response):
        rankings = self.parse_jailbreakbench(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('jailbreakbench_sample.html')
    body = sample.read_text() if sample.exists() else ""
    spider = JailbreakbenchSpider()
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
