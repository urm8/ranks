from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

import csv
import io

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row

class AlpacaEvalSpider(SourceSpider):
    name = "alpaca_eval"
    source_title = 'AlpacaEval'
    start_urls = ['https://raw.githubusercontent.com/tatsu-lab/alpaca_eval/main/docs/data_AlpacaEval_2/weighted_alpaca_eval_gpt4_turbo_leaderboard.csv']
    browse_url = 'https://tatsu-lab.github.io/alpaca_eval/'
    kind = 'benchmark'
    engine = 'http'

    def parse_alpaca_eval_csv(self, body: str) -> list[dict]:
        reader = csv.DictReader(io.StringIO(body))
        scored: list[tuple[float, str]] = []
        for row in reader:
            name = (row.get("name") or row.get("Model Name") or row.get("model") or "").strip()
            raw = (
                row.get("length_controlled_winrate")
                or row.get("LC Win Rate")
                or row.get("win_rate")
                or row.get("Win Rate")
                or ""
            )
            val = self.first_number(str(raw))
            if not name or val is None:
                continue
            # CSV often stores fractions
            if 0 <= val <= 1:
                val = val * 100.0
            scored.append((val, name))
        scored.sort(key=lambda t: -t[0])
        rows_out: list[dict] = []
        seen: set[str] = set()
        for lc, name in scored:
            mid = self.guess_model_id(name)
            if mid in seen:
                continue
            seen.add(mid)
            rank = len(rows_out) + 1
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=f"{lc:g}%",
                note=f"AlpacaEval LC win rate rank {rank}",
                normalized_score=round(lc, 1) if lc <= 100 else None,
            )
            row["model"] = name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

    def parse_alpaca_eval_table(self, body: str) -> list[dict]:
        rows_out: list[dict] = []
        seen: set[str] = set()
        for cells in self.iter_table_rows(body):
            if len(cells) < 3:
                continue
            joined = " ".join(cells).lower()
            if "win rate" in joined and "model" in joined:
                continue
            rank_num = self.first_number(cells[0])
            model_name = cells[1].replace("📄", "").strip()
            lc = self.first_number(cells[2])
            if not model_name or lc is None or rank_num is None:
                continue
            mid = self.guess_model_id(model_name)
            if mid in seen:
                continue
            seen.add(mid)
            rank = len(rows_out) + 1
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=f"{lc:g}%",
                note=f"AlpacaEval LC win rate rank {int(rank_num)}",
                normalized_score=float(lc) if lc <= 100 else None,
            )
            row["model"] = model_name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

    def parse_alpaca_eval(self, body: str) -> list[dict]:
        stripped = body.lstrip()
        if "length_controlled_winrate" in stripped[:2000] or stripped.startswith("name,"):
            rows = self.parse_alpaca_eval_csv(stripped)
            if rows:
                return rows
        return self.parse_alpaca_eval_table(body)

    def parse_response(self, response):
        rankings = self.parse_alpaca_eval(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('alpaca_eval_sample.html')
    body = sample.read_text() if sample.exists() else ""
    spider = AlpacaEvalSpider()
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
