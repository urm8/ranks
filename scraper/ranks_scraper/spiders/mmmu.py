from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

import json
from typing import Any

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row

class MmmuSpider(SourceSpider):
    name = "mmmu"
    source_title = 'MMMU'
    start_urls = ['https://mmmu-benchmark.github.io/leaderboard_data.json']
    browse_url = 'https://mmmu-benchmark.github.io/'
    kind = 'benchmark'
    engine = 'http'

    def parse_mmmu_json(self, payload: Any) -> list[dict]:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return []
        data = payload.get("leaderboardData") if isinstance(payload, dict) else payload
        if not isinstance(data, list):
            return []
        rows_out: list[dict] = []
        seen: set[str] = set()
        scored: list[tuple[float, str, str]] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            info = entry.get("info") or {}
            name = info.get("name") or ""
            if not name or info.get("type") == "human_expert":
                continue
            val = (entry.get("validation") or {}).get("overall")
            try:
                score = float(str(val).replace("*", ""))
            except (TypeError, ValueError):
                continue
            scored.append((score, name, info.get("size") or ""))
        scored.sort(key=lambda t: -t[0])
        for score, name, _size in scored:
            mid = self.guess_model_id(name)
            if mid in seen:
                continue
            seen.add(mid)
            rank = len(rows_out) + 1
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=f"{score:g}%",
                note=f"MMMU validation overall rank {rank}",
                normalized_score=float(score) if score <= 100 else None,
            )
            row["model"] = name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

    def parse_mmmu_table(self, body: str) -> list[dict]:
        rows_out: list[dict] = []
        seen: set[str] = set()
        for cells in self.iter_table_rows(body):
            if len(cells) < 4:
                continue
            joined = " ".join(cells).lower()
            if "mmmu" in joined and "name" in joined:
                continue
            # Flexible: find a name-like cell and an overall % near the end
            name = None
            score = None
            for cell in cells:
                if name is None and any(c.isalpha() for c in cell) and self.first_number(cell) is None:
                    if cell.lower() not in {"reset", "name", "size", "date", "overall"}:
                        name = cell.strip()
                val = self.first_number(cell.replace("*", ""))
                if val is not None and 0 < val <= 100:
                    score = val  # keep last plausible overall
            if not name or score is None:
                continue
            mid = self.guess_model_id(name)
            if mid in seen:
                continue
            seen.add(mid)
            rank = len(rows_out) + 1
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=f"{score:g}%",
                note=f"MMMU overall rank {rank}",
                normalized_score=float(score),
            )
            row["model"] = name
            rows_out.append(row)
        return attach_normalized_scores(rows_out)

    def parse_mmmu(self, body: str) -> list[dict]:
        stripped = body.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            rows = self.parse_mmmu_json(stripped)
            if rows:
                return rows
        # embedded JSON file reference may appear; try extract leaderboard_data blob
        if "leaderboardData" in body:
            start = body.find('{"leaderboardData"')
            if start < 0:
                start = body.find('{"leaderboardData":')
            if start >= 0:
                # crude brace match limited
                depth = 0
                for i, ch in enumerate(body[start : start + 2_000_000]):
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            rows = self.parse_mmmu_json(body[start : start + i + 1])
                            if rows:
                                return rows
                            break
        return self.parse_mmmu_table(body)

    def parse_response(self, response):
        rankings = self.parse_mmmu(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('mmmu_sample.json')
    body = sample.read_text() if sample.exists() else ""
    spider = MmmuSpider()
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
