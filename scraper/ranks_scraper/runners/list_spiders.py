"""List registered ranks spiders via Scrapy spider loader."""

from __future__ import annotations

import json

from ranks_scraper.discovery import load_spider, spider_names


def main() -> int:
    rows = []
    for name in spider_names():
        cls = load_spider(name)
        start_urls = list(getattr(cls, "start_urls", None) or [])
        rows.append(
            {
                "spider": name,
                "engine": getattr(cls, "engine", "http"),
                "kind": getattr(cls, "kind", None),
                "name": getattr(cls, "source_title", None) or name,
                "url": start_urls[0] if len(start_urls) == 1 else (start_urls or None),
                "browse_url": getattr(cls, "browse_url", None),
            }
        )
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
