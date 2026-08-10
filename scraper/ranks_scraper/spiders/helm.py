from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row

class HelmSpider(SourceSpider):
    name = "helm"
    source_title = 'HELM'
    start_urls = ['https://crfm.stanford.edu/helm/lite/latest/']
    kind = 'benchmark'
    engine = 'playwright'

    def parse_helm(self, body: str) -> list[dict]:
        rows_out: list[dict] = []
        seen: set[str] = set()
        for cells in self.iter_table_rows(body):
            if len(cells) < 2:
                continue
            joined = " ".join(cells).lower()
            if "mean win rate" in joined:
                continue
            model_name = cells[0].strip()
            win = self.first_number(cells[1])
            if not model_name or win is None:
                continue
            if model_name.lower() == "model":
                continue
            mid = self.guess_model_id(model_name)
            if mid in seen:
                continue
            seen.add(mid)
            # HELM win rate is 0-1
            if 0 <= win <= 1:
                normalized = round(win * 100.0, 1)
                score = f"{normalized:g}/100"
            else:
                normalized = round(win, 1) if win <= 100 else None
                score = f"{win:g}"
            rank = len(rows_out) + 1
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=score,
                note=f"HELM mean win rate rank {rank}",
                normalized_score=normalized,
            )
            row["model"] = model_name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

    def parse_response(self, response):
        rankings = self.parse_helm(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('helm_sample.html')
    body = sample.read_text() if sample.exists() else ""
    spider = HelmSpider()
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
