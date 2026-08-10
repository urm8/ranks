from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

import json
import re
from typing import Any

from ranks_scraper.parsing.normalize import attach_normalized_scores, ranking_row

class TauBenchSpider(SourceSpider):
    name = "tau_bench"
    source_title = 'tau-bench / tau2-bench'
    start_urls = ['https://sierra-tau-bench-public.s3.us-west-2.amazonaws.com/submissions/manifest.json']
    browse_url = 'https://www.tau-bench.com/'
    kind = 'benchmark'
    engine = 'http'

    def parse_tau_manifest(self, body: str) -> list[dict]:
        try:
            payload: Any = json.loads(body)
        except json.JSONDecodeError:
            return self._parse_tau_html_fallback(body)

        submissions: list[Any]
        if isinstance(payload, list):
            submissions = payload
        elif isinstance(payload, dict):
            submissions = (
                payload.get("submissions")
                or payload.get("entries")
                or payload.get("results")
                or []
            )
            if not submissions and "models" in payload:
                submissions = payload["models"]
        else:
            return []

        scored: list[tuple[float, str, str]] = []
        for entry in submissions:
            if isinstance(entry, str):
                # path-like: claude-opus-4-5_sierra_...
                name = entry.split("/")[-1].split("_")[0]
                scored.append((0.0, name, entry))
                continue
            if not isinstance(entry, dict):
                continue
            name = (
                entry.get("model")
                or entry.get("model_name")
                or entry.get("name")
                or entry.get("id")
                or ""
            )
            score = (
                entry.get("score")
                or entry.get("pass_rate")
                or entry.get("success_rate")
                or entry.get("avg_reward")
                or entry.get("overall")
            )
            if score is None and isinstance(entry.get("metrics"), dict):
                metrics = entry["metrics"]
                score = metrics.get("pass_hat") or metrics.get("avg_reward") or metrics.get("score")
            try:
                numeric = float(score)
            except (TypeError, ValueError):
                numeric = 0.0
            if not name:
                continue
            scored.append((numeric, str(name), json.dumps(entry)[:80]))

        # Prefer higher scores; if all zero (paths only), keep order
        if any(s[0] > 0 for s in scored):
            scored.sort(key=lambda t: -t[0])

        rows: list[dict] = []
        seen: set[str] = set()
        for numeric, name, _meta in scored:
            mid = self.guess_model_id(name)
            if mid in seen:
                continue
            seen.add(mid)
            if 0 < numeric <= 1:
                normalized = round(numeric * 100.0, 1)
                score_str = f"{normalized:g}/100"
            elif numeric > 0:
                normalized = round(numeric, 1) if numeric <= 100 else None
                score_str = f"{numeric:g}"
            else:
                normalized = None
                score_str = "listed"
            rank = len(rows) + 1
            row = ranking_row(
                rank=rank,
                model_id=mid,
                score=score_str,
                note=f"tau-bench submission rank {rank}",
                normalized_score=normalized,
            )
            row["model"] = name
            rows.append(row)
        return attach_normalized_scores(rows)

    def _parse_tau_html_fallback(self, body: str) -> list[dict]:
        # Pull model-ish tokens from page text when manifest isn't JSON
        names = re.findall(
            r"\b((?:claude|gpt|gemini|glm|qwen|kimi|o3|o4)[a-z0-9._-]*)\b",
            body,
            flags=re.I,
        )
        rows: list[dict] = []
        seen: set[str] = set()
        for name in names:
            mid = self.guess_model_id(name)
            if mid in seen:
                continue
            seen.add(mid)
            rank = len(rows) + 1
            rows.append(
                ranking_row(
                    rank=rank,
                    model_id=mid,
                    score="listed",
                    note=f"tau-bench page mention rank {rank}",
                )
            )
        return attach_normalized_scores(rows)

    def parse_tau_bench(self, body: str) -> list[dict]:
        return self.parse_tau_manifest(body)

    def parse_response(self, response):
        rankings = self.parse_tau_bench(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('tau_bench_sample.json')
    body = sample.read_text() if sample.exists() else ""
    spider = TauBenchSpider()
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
