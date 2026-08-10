from __future__ import annotations

import json
from pathlib import Path

from itemadapter import ItemAdapter


class FetchedSourcePipeline:
    """Write each spider's fetched payload as JSON under RANKS_SCRAPE_OUT_DIR."""

    def __init__(self, out_dir: str, crawler=None):
        self.out_dir = Path(out_dir)
        self.crawler = crawler
        self._items: dict[str, list[dict]] = {}

    @classmethod
    def from_crawler(cls, crawler):
        out_dir = crawler.settings.get("RANKS_SCRAPE_OUT_DIR", "/data/scrapes")
        return cls(out_dir=out_dir, crawler=crawler)

    def open_spider(self, spider):
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._items[spider.name] = []

    def process_item(self, item, spider):
        payload = ItemAdapter(item).asdict()
        self._items.setdefault(spider.name, []).append(payload)
        return item

    def close_spider(self, spider):
        rows = self._items.get(spider.name, [])
        path = self.out_dir / f"{spider.name}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        rankings_n = sum(len(row.get("rankings") or []) for row in rows)
        models_n = sum(len(row.get("models") or {}) for row in rows)
        spider.logger.info(
            "wrote %s (%d item(s), rankings=%d, models=%d)",
            path,
            len(rows),
            rankings_n,
            models_n,
        )
        index_path = self.out_dir / "index.json"
        index = {}
        if index_path.exists():
            try:
                index = json.loads(index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                index = {}
        index[spider.name] = {
            "file": path.name,
            "count": len(rows),
            "ok": sum(1 for row in rows if row.get("ok")),
            "rankings": rankings_n,
            "models": models_n,
        }
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        combined_path = self.out_dir / "fetched.json"
        combined = []
        if combined_path.exists():
            try:
                combined = json.loads(combined_path.read_text(encoding="utf-8"))
                if not isinstance(combined, list):
                    combined = []
            except json.JSONDecodeError:
                combined = []
        urls = {row.get("url") for row in rows}
        combined = [row for row in combined if row.get("url") not in urls]
        combined.extend(rows)
        combined_path.write_text(json.dumps(combined, ensure_ascii=False), encoding="utf-8")
