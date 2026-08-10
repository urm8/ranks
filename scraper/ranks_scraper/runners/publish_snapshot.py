"""Build FE snapshot from /data/scrapes and write ranks_snapshots in Postgres."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ranks_scraper.parsing.db import publish_from_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish ranks snapshot from scrape dir")
    parser.add_argument(
        "--out",
        default=os.environ.get("RANKS_SCRAPE_OUT_DIR", "/data/scrapes"),
        help="Directory containing spider JSON / fetched.json",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Only write snapshot.json",
    )
    args = parser.parse_args(argv)
    out_dir = Path(args.out)
    snapshot = publish_from_dir(out_dir, write_db=not args.skip_db)
    bench_counts = {
        b.get("id"): len(b.get("rankings") or [])
        for b in (snapshot.get("benchmarks") or [])
        if isinstance(b, dict)
    }
    print(
        json.dumps(
            {
                "generated_at": snapshot.get("generated_at"),
                "stored": bool(snapshot.get("_stored_generated_at")),
                "models": len(snapshot.get("models") or {}),
                "benchmarks": len(snapshot.get("benchmarks") or []),
                "benchmark_rankings": bench_counts,
                "categories": len(snapshot.get("categories") or []),
                "emerging_models": len(snapshot.get("emerging_models") or []),
                "sources_ok": sum(1 for s in snapshot.get("sources") or [] if s.get("ok")),
                "snapshot_path": str(out_dir / "snapshot.json"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
