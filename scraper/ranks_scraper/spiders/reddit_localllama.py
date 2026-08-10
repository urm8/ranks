from __future__ import annotations

from ranks_scraper.spiders.base import SourceSpider

import json
import re
from typing import Any

from ranks_scraper.parsing.normalize import attach_normalized_scores, normalize_model_id, ranking_row

MODEL_PATH_RE = re.compile(r"\b([a-z0-9][\w.-]*)/([a-z0-9][\w.-]+)\b", re.I)

VENDOR_HINTS = {
    "anthropic", "openai", "google", "qwen", "deepseek", "moonshotai", "moonshot",
    "meta-llama", "meta", "mistralai", "mistral", "x-ai", "xai", "z-ai", "zai",
    "cohere", "amazon", "nvidia", "microsoft", "perplexity", "01-ai", "ai21",
    "tencent", "bytedance", "minimax", "lmstudio", "nousresearch", "huggingface",
}

class RedditLocalllamaSpider(SourceSpider):
    name = "reddit_localllama"
    source_title = 'Reddit LocalLLaMA benchmark discussion'
    start_urls = ['https://www.reddit.com/r/LocalLLaMA/search.json?q=best%20LLM%20benchmark%20coding%20writing%20OpenRouter&restrict_sr=1&sort=new&limit=100']
    kind = 'community'
    engine = 'http'

    def parse_reddit_localllama(self, body: str) -> list[dict]:
        """Parse ALL search result posts — no mention cap."""
        try:
            payload: Any = json.loads(body)
        except json.JSONDecodeError:
            return []
        posts = (((payload or {}).get("data") or {}).get("children")) if isinstance(payload, dict) else None
        if not isinstance(posts, list):
            return []
        rows: list[dict] = []
        seen: set[str] = set()
        for child in posts:
            data = (child or {}).get("data") or {}
            text = " ".join(str(data.get(k) or "") for k in ("title", "selftext", "url"))
            for match in MODEL_PATH_RE.finditer(text):
                vendor, slug = match.group(1).lower(), match.group(2).lower()
                if vendor not in VENDOR_HINTS:
                    continue
                if slug in {"models", "chat", "api", "docs", "blog", "pricing", "comments"}:
                    continue
                mid = normalize_model_id(f"{vendor}/{slug}")
                if mid in seen:
                    continue
                seen.add(mid)
                rows.append(
                    ranking_row(
                        rank=len(rows) + 1,
                        model_id=mid,
                        score="mentioned",
                        note="Reddit LocalLLaMA discussion mention order",
                    )
                )
            for token in re.findall(
                r"\b(claude-[\w.-]+|gpt-[\w.-]+|llama-[\w.-]+|qwen[\w.-]+|deepseek-[\w.-]+|mistral-[\w.-]+|gemma-[\w.-]+|gemini-[\w.-]+)\b",
                text,
                re.I,
            ):
                mid = self.guess_model_id(token)
                if mid in seen:
                    continue
                seen.add(mid)
                rows.append(
                    ranking_row(
                        rank=len(rows) + 1,
                        model_id=mid,
                        score="mentioned",
                        note="Reddit LocalLLaMA discussion mention order",
                    )
                )
        return attach_normalized_scores(rows)

    def parse_response(self, response):
        rankings = self.parse_reddit_localllama(response.text)
        models = self.models_from_rankings(rankings)
        return {
            "rankings": rankings,
            "models": models,
            "mentions": [r["model_id"] for r in rankings],
        }


if __name__ == "__main__":
    from pathlib import Path

    sample = Path(__file__).with_name('reddit_localllama_sample.json')
    body = sample.read_text() if sample.exists() else ""
    spider = RedditLocalllamaSpider()
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
