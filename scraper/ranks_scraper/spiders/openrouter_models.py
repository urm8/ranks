"""OpenRouter models API — catalog ALL text I/O models (uncapped)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ranks_scraper.parsing.normalize import model_display_name, normalize_model_id
from ranks_scraper.spiders.base import SourceSpider

class OpenrouterModelsSpider(SourceSpider):
    name = "openrouter_models"
    source_title = 'OpenRouter text models'
    start_urls = ['https://openrouter.ai/api/v1/models']
    browse_url = 'https://openrouter.ai/models?input_modalities=text&output_modalities=text'
    kind = 'catalog'
    engine = 'http'

    def _supports_text_io(self, entry: dict) -> bool:
        arch = entry.get("architecture") or {}
        inputs = {str(x).lower() for x in (arch.get("input_modalities") or [])}
        outputs = {str(x).lower() for x in (arch.get("output_modalities") or [])}
        if not inputs and not outputs:
            return True
        return "text" in inputs and "text" in outputs

    def parse_openrouter_models(self, body: str) -> dict[str, dict]:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return {}
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return {}
        models: dict[str, dict] = {}
        for entry in data:
            if not isinstance(entry, dict) or not self._supports_text_io(entry):
                continue
            mid = normalize_model_id(entry.get("id") or "")
            if not mid:
                continue
            pricing = entry.get("pricing") or {}
            try:
                inp = float(pricing.get("prompt") or 0) * 1_000_000
                out = float(pricing.get("completion") or 0) * 1_000_000
            except (TypeError, ValueError):
                inp = out = None
            created = entry.get("created")
            release_date = None
            if isinstance(created, (int, float)) and created > 0:
                release_date = datetime.fromtimestamp(created, tz=timezone.utc).date().isoformat()
            models[mid] = {
                "name": entry.get("name") or model_display_name(mid),
                "vendor": mid.split("/")[0],
                "input": inp,
                "output": out,
                "context": entry.get("context_length"),
                "discovered": True,
                "catalog_sources": ["OpenRouter"],
                "price_source": "OpenRouter",
                "release_date": release_date,
            }
        return models

    def parse_response(self, response):
        models = self.parse_openrouter_models(response.text)
        return {"models": models, "rankings": [], "mentions": list(models)}


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('openrouter_models_sample.json')
    body = sample.read_text() if sample.exists() else ""
    spider = OpenrouterModelsSpider()
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
