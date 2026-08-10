from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

import json
import re
from typing import Any

from ranks_scraper.parsing.normalize import model_display_name, normalize_model_id

class LmstudioModelsSpider(SourceSpider):
    name = "lmstudio_models"
    source_title = 'LM Studio model catalog'
    start_urls = ['https://lmstudio.ai/models']
    kind = 'catalog'
    engine = 'http'

    def parse_lmstudio_models(self, body: str) -> dict[str, dict]:
        models: dict[str, dict] = {}
        m = re.search(
            r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            body,
            flags=re.I | re.S,
        )
        if m:
            try:
                payload: Any = json.loads(m.group(1))
                self._walk_models(payload, models)
            except json.JSONDecodeError:
                pass
        if models:
            return models

        # Card /models/ links
        for href in re.findall(r'href="(/models/[a-zA-Z0-9._-]+)"', body):
            slug = href.rstrip("/").split("/")[-1]
            mid = normalize_model_id(f"lmstudio/{slug}")
            if mid not in models:
                models[mid] = {
                    "name": model_display_name(mid),
                    "vendor": "lmstudio",
                    "discovered": True,
                    "catalog_sources": ["LM Studio"],
                    "price_source": "LM Studio catalog",
                }

        text = self.strip_tags(body)
        for match in re.finditer(r"\b([a-z0-9_.-]+/[a-z0-9_.-]+)\b", text, re.I):
            mid = normalize_model_id(match.group(1))
            vendor = mid.split("/")[0]
            if vendor in {"http", "https", "www", "api", "docs", "static"}:
                continue
            if mid in models:
                continue
            models[mid] = {
                "name": model_display_name(mid),
                "vendor": vendor,
                "discovered": True,
                "catalog_sources": ["LM Studio"],
                "price_source": "seed pricing",
            }
        return models

    def _walk_models(self, node: Any, out: dict[str, dict], depth: int = 0) -> None:
        if depth > 64:
            return
        if isinstance(node, dict):
            keys = {str(k).lower() for k in node}
            name = node.get("name") or node.get("model") or node.get("title")
            mid = node.get("id") or node.get("model_id") or node.get("slug")
            if mid and ("model" in keys or "name" in keys or "publisher" in keys):
                mid_s = normalize_model_id(str(mid))
                if "/" not in mid_s and name:
                    mid_s = self.guess_model_id(str(name), str(node.get("publisher") or node.get("creator") or ""))
                if mid_s and mid_s not in out:
                    out[mid_s] = {
                        "name": str(name or model_display_name(mid_s)),
                        "vendor": mid_s.split("/")[0],
                        "discovered": True,
                        "catalog_sources": ["LM Studio"],
                        "price_source": "seed pricing",
                    }
            for v in node.values():
                self._walk_models(v, out, depth=depth + 1)
        elif isinstance(node, list):
            for item in node:
                self._walk_models(item, out, depth=depth + 1)

    def parse_response(self, response):
        models = self.parse_lmstudio_models(response.text)
        return {"models": models, "rankings": [], "mentions": list(models)}


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('lmstudio_models_sample.html')
    body = sample.read_text() if sample.exists() else ""
    spider = LmstudioModelsSpider()
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
