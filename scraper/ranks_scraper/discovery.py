"""Discover ranks spiders via Scrapy's spider loader.

Spiders own their URLs and metadata as class attributes. This module only
lists/loads spider classes — it is not a source-of-truth URL registry.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from scrapy.settings import Settings
from scrapy.spiderloader import SpiderLoader

if TYPE_CHECKING:
    from scrapy import Spider


@lru_cache(maxsize=1)
def spider_loader() -> SpiderLoader:
    settings = Settings()
    settings.setmodule("ranks_scraper.settings")
    return SpiderLoader.from_settings(settings)


def spider_names() -> list[str]:
    return sorted(spider_loader().list())


def load_spider(name: str) -> type[Spider]:
    return spider_loader().load(name)


def spider_engine(name: str) -> str:
    cls = load_spider(name)
    return getattr(cls, "engine", "http")
