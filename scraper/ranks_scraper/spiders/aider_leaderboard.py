from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

import re

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row

class AiderLeaderboardSpider(SourceSpider):
    name = "aider_leaderboard"
    source_title = 'Aider Polyglot'
    start_urls = ['https://aider.chat/docs/leaderboards/']
    kind = 'benchmark'
    engine = 'http'

    def parse_aider_leaderboard(self, body: str) -> list[dict]:
        rows_out: list[dict] = []
        seen: set[str] = set()
        for cells in self.iter_table_rows(body):
            if len(cells) < 3:
                continue
            joined = " ".join(cells).lower()
            if "percent correct" in joined or joined.startswith("model"):
                continue
            # Skip expandable detail rows
            if "dirname" in joined and "test cases" in joined:
                continue
            model_name = cells[1].split("\n")[0].strip() if len(cells) > 1 else cells[0]
            if not model_name or model_name in {"▶", "Model"}:
                continue
            pct = self.first_number(cells[2] if len(cells) > 2 else "")
            if pct is None:
                continue
            command = cells[4] if len(cells) > 4 else ""
            mid = ""
            m = re.search(r"--model\s+([a-z0-9_.-]+/[a-z0-9_./:+-]+)", command, re.I)
            if m:
                mid = m.group(1).split(":")[0].lower()
                if mid.startswith("openrouter/"):
                    mid = mid[len("openrouter/") :]
            if not mid:
                mid = self.guess_model_id(model_name)
            if not mid or mid in seen:
                continue
            seen.add(mid)
            cost = self.first_number((cells[3] if len(cells) > 3 else "").replace("$", ""))
            pricing = None
            if cost is not None:
                pricing = {"input": None, "output": None, "context": None, "source": "Aider leaderboard", "run_cost_usd": cost}
            rank = len(rows_out) + 1
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=f"{pct:g}%",
                note=f"Aider polyglot percent correct rank {rank}",
                normalized_score=float(pct) if pct <= 100 else None,
                pricing=pricing,
            )
            row["model"] = model_name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

    def parse_response(self, response):
        rankings = self.parse_aider_leaderboard(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('aider_leaderboard_sample.html')
    body = sample.read_text() if sample.exists() else ""
    spider = AiderLeaderboardSpider()
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
