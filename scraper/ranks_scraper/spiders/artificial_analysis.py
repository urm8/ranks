from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row

class ArtificialAnalysisSpider(SourceSpider):
    name = "artificial_analysis"
    source_title = 'Artificial Analysis model leaderboard'
    start_urls = ['https://artificialanalysis.ai/leaderboards/models']
    kind = 'benchmark'
    engine = 'http'

    def parse_artificial_analysis(self, body: str) -> list[dict]:
        """Parse the Models leaderboard table (Model / Creator / Intelligence Index)."""
        rows_out: list[dict] = []
        seen: set[str] = set()
        header_seen = False
        for cells in self.iter_table_rows(body):
            if not cells:
                continue
            joined = " ".join(cells).lower()
            if not header_seen:
                if "intelligence" in joined and ("model" in joined or "creator" in joined):
                    header_seen = True
                continue
            # Data row: Model, Context, Creator, Intelligence, Price, Speed, ...
            if len(cells) < 4:
                continue
            model_name = cells[0].split("\n")[0].strip()
            if not model_name or model_name.lower() in {"model", "features"}:
                continue
            creator = cells[2] if len(cells) > 2 else ""
            intelligence = self.first_number(cells[3] if len(cells) > 3 else "")
            if intelligence is None:
                # sometimes creator/index shifted
                for cell in cells[1:6]:
                    val = self.first_number(cell)
                    if val is not None and 0 <= val <= 100:
                        intelligence = val
                        break
            if intelligence is None:
                continue
            mid = self.guess_model_id(model_name, creator)
            if not mid or mid in seen:
                continue
            seen.add(mid)
            price_raw = cells[4] if len(cells) > 4 else ""
            price_num = self.first_number(price_raw.replace("$", "")) if price_raw else None
            pricing = None
            if price_num is not None:
                pricing = {
                    "input": None,
                    "output": None,
                    "context": self.first_number(cells[1]) if len(cells) > 1 else None,
                    "source": "Artificial Analysis",
                    "cost_per_task_usd": price_num,
                }
            rank = len(rows_out) + 1
            rows_out.append(
                ranking_row(
                    rank=rank,
                    model_id=mid,
                    score=f"{intelligence:g}/100",
                    note=f"Artificial Analysis Intelligence Index rank {rank}",
                    normalized_score=float(intelligence),
                    pricing=pricing,
                )
            )
            # prefer display name from source
            rows_out[-1]["model"] = model_name
        return attach_normalized_scores(rows_out)

    def parse_response(self, response):
        rankings = self.parse_artificial_analysis(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('artificial_analysis_sample.html')
    body = sample.read_text() if sample.exists() else ""
    spider = ArtificialAnalysisSpider()
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
