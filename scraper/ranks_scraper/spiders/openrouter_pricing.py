from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

import re

from ranks_scraper.parsing.normalize import attach_normalized_scores, normalize_model_id, ranking_row

class OpenrouterPricingSpider(SourceSpider):
    name = "openrouter_pricing"
    source_title = 'OpenRouter pricing'
    start_urls = ['https://openrouter.ai/pricing']
    kind = 'pricing'
    engine = 'http'

    def parse_openrouter_pricing(self, body: str) -> list[dict]:
        rows_out: list[dict] = []
        seen: set[str] = set()
        # Prefer vendor/slug paths in tables or links
        for cells in self.iter_table_rows(body):
            text = " | ".join(cells)
            m = re.search(r"\b([a-z0-9_.-]+/[a-z0-9_./:+-]+)\b", text, re.I)
            if not m:
                continue
            mid = normalize_model_id(m.group(1))
            if mid in seen:
                continue
            nums = [self.first_number(c) for c in cells]
            nums = [n for n in nums if n is not None]
            inp = nums[0] if nums else None
            out = nums[1] if len(nums) > 1 else None
            seen.add(mid)
            rank = len(rows_out) + 1
            pricing = {
                "input": inp,
                "output": out,
                "context": None,
                "source": "OpenRouter pricing",
            }
            rows_out.append(
                ranking_row(
                    rank=rank,
                    model_id=mid,
                    score=f"${inp:g}/M in" if inp is not None else "priced",
                    note=f"OpenRouter pricing list rank {rank}",
                    pricing=pricing,
                )
            )
        if rows_out:
            return attach_normalized_scores(rows_out)

        text = self.strip_tags(body)
        for m in re.finditer(r"\b([a-z0-9_.-]+/[a-z0-9_.-]+)\b", text, re.I):
            mid = normalize_model_id(m.group(1))
            if mid in seen or mid.count("/") != 1:
                continue
            vendor = mid.split("/")[0]
            if vendor in {"http", "https", "www", "api", "docs"}:
                continue
            seen.add(mid)
            rank = len(rows_out) + 1
            rows_out.append(
                ranking_row(
                    rank=rank,
                    model_id=mid,
                    score="listed",
                    note=f"OpenRouter pricing page mention rank {rank}",
                )
            )
        return attach_normalized_scores(rows_out)

    def parse_response(self, response):
        rankings = self.parse_openrouter_pricing(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('openrouter_pricing_sample.html')
    body = sample.read_text() if sample.exists() else ""
    spider = OpenrouterPricingSpider()
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
