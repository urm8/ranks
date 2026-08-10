"""Run every registered ranks spider, then publish FE snapshot to Postgres."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "ranks_scraper.settings")

from ranks_scraper.discovery import spider_engine, spider_names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crawl ranks spiders and publish snapshot")
    parser.add_argument(
        "--out",
        default=os.environ.get("RANKS_SCRAPE_OUT_DIR", "/data/scrapes"),
        help="Output directory for JSON scrape artifacts",
    )
    parser.add_argument("--only", nargs="*", default=None, help="Optional subset of spider names")
    parser.add_argument(
        "--skip-playwright",
        action="store_true",
        help="Skip spiders that require Playwright",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Build snapshot.json but do not write Postgres",
    )
    parser.add_argument(
        "--crawl-only",
        action="store_true",
        help="Only crawl; do not build/publish snapshot",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    names = args.only or spider_names()
    if args.skip_playwright:
        names = [name for name in names if spider_engine(name) != "playwright"]

    env = os.environ.copy()
    env["RANKS_SCRAPE_OUT_DIR"] = str(out_dir)
    env["SCRAPY_SETTINGS_MODULE"] = "ranks_scraper.settings"
    project_root = Path(__file__).resolve().parents[2]

    failures: list[str] = []
    for name in names:
        cmd = [
            sys.executable,
            "-m",
            "scrapy",
            "crawl",
            name,
            "-s",
            f"RANKS_SCRAPE_OUT_DIR={out_dir}",
        ]
        print(f"==> crawling {name}", flush=True)
        result = subprocess.run(cmd, env=env, cwd=str(project_root))
        if result.returncode != 0:
            failures.append(name)
            print(f"!! spider {name} exited {result.returncode}", flush=True)

    summary: dict = {
        "spiders": names,
        "out": str(out_dir),
        "failures": failures,
    }
    index_path = out_dir / "index.json"
    if index_path.exists():
        summary["index"] = json.loads(index_path.read_text(encoding="utf-8"))

    # Per-spider parsed counts (actual rankings/models, not display preview).
    parsed_counts: dict[str, dict[str, int]] = {}
    for name in names:
        path = out_dir / f"{name}.json"
        if not path.exists():
            continue
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(rows, list):
            rows = [rows]
        parsed_counts[name] = {
            "items": len(rows),
            "rankings": sum(len(r.get("rankings") or []) for r in rows if isinstance(r, dict)),
            "models": sum(len(r.get("models") or {}) for r in rows if isinstance(r, dict)),
            "ok": sum(1 for r in rows if isinstance(r, dict) and r.get("ok")),
        }
    summary["parsed"] = parsed_counts
    for name, counts in parsed_counts.items():
        print(
            f"==> parsed {name}: rankings={counts['rankings']} models={counts['models']} "
            f"ok={counts['ok']}/{counts['items']}",
            flush=True,
        )

    if not args.crawl_only:
        from ranks_scraper.parsing.db import publish_from_dir

        write_db = not args.skip_db and all(
            os.environ.get(k)
            for k in ("RANKS_DB_HOST", "RANKS_DB_NAME", "RANKS_DB_USER", "RANKS_DB_PASSWORD")
        )
        if not args.skip_db and not write_db:
            print("!! missing RANKS_DB_* env; writing snapshot.json only", flush=True)
        snapshot = publish_from_dir(out_dir, write_db=write_db)
        bench_counts = {
            b.get("id"): len(b.get("rankings") or [])
            for b in (snapshot.get("benchmarks") or [])
            if isinstance(b, dict)
        }
        summary["snapshot"] = {
            "generated_at": snapshot.get("generated_at"),
            "stored": bool(snapshot.get("_stored_generated_at")),
            "models": len(snapshot.get("models") or {}),
            "benchmarks": len(snapshot.get("benchmarks") or []),
            "benchmark_rankings": bench_counts,
            "categories": len(snapshot.get("categories") or []),
            "sources": len(snapshot.get("sources") or []),
            "sources_ok": sum(1 for s in snapshot.get("sources") or [] if s.get("ok")),
            "emerging_models": len(snapshot.get("emerging_models") or []),
        }

    print(json.dumps(summary, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
