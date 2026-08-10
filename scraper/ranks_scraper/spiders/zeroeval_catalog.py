"""ZeroEval model catalog — ALL orgs/models from /leaderboard/models/list."""

from __future__ import annotations

import json

from ranks_scraper.parsing.normalize import model_display_name, normalize_model_id
from ranks_scraper.spiders.base import SourceSpider

class ZeroevalCatalogSpider(SourceSpider):
    name = "zeroeval_catalog"
    source_title = 'LLM Stats / ZeroEval model catalog'
    start_urls = ['https://api.zeroeval.com/leaderboard/models/list']
    kind = 'catalog'
    engine = 'http'

    def parse_zeroeval_model_catalog(self, body: str) -> dict[str, dict]:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, list):
            return {}
        models: dict[str, dict] = {}
        for org in payload:
            if not isinstance(org, dict):
                continue
            org_id = normalize_model_id(org.get("organization_id") or org.get("name") or "unknown")
            for model in org.get("models") or []:
                if not isinstance(model, dict):
                    continue
                short = normalize_model_id(model.get("model_id") or "")
                if not short:
                    continue
                mid = short if "/" in short else f"{org_id}/{short}"
                models[mid] = {
                    "name": model.get("name") or model_display_name(mid),
                    "vendor": org.get("name") or org_id,
                    "release_date": model.get("release_date"),
                    "input": model.get("inputPrice"),
                    "output": model.get("outputPrice"),
                    "context": model.get("context_window"),
                    "discovered": True,
                    "catalog_sources": ["LLM Stats / ZeroEval"],
                    "price_source": "LLM Stats / ZeroEval catalog",
                }
        return models

    def parse_response(self, response):
        models = self.parse_zeroeval_model_catalog(response.text)
        return {"models": models, "rankings": [], "mentions": list(models)}


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('zeroeval_catalog_sample.json')
    body = sample.read_text() if sample.exists() else ""
    spider = ZeroevalCatalogSpider()
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
