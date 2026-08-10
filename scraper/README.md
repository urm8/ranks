# ranks-scraper

Scrapy project with **one self-contained spider module per source**, FE-compatible
ranking rows, and Postgres snapshot publish to `ranks_snapshots`.

## Scrapy model

Each spider owns its crawl config as class attributes (Scrapy style):

- `name`, `start_urls` (or async `start()` for custom requests)
- `source_title`, `kind`, `engine` (`http` | `playwright`)
- optional `browse_url`
- `parse_response()` / parsers for that source

Spiders inherit `SourceSpider`, which implements Scrapy 2.13+ `async def start()`
so download meta (`playwright`, page methods) is applied. Overriding only the
legacy `start_requests()` is ignored on Scrapy ≥2.13 and will skip Playwright.

There is **no** global `SOURCES` URL registry. Discovery for `ranks-crawl-all` /
`ranks-list-spiders` uses Scrapy's spider loader (`scrapy list`).

Shared base (`spiders/base.py`) only wires download (HTTP vs Playwright meta) and
emits `FetchedSourceItem`. Project settings stay project-wide (pipelines,
concurrency, Playwright reactor).

## Parsing

- Dedicated parsers live either **in the spider file** (ZeroEval, OpenRouter,
  Open LLM Leaderboard, …) or under `ranks_scraper/parsing/sources/<source>.py`
  (LMArena, Artificial Analysis, Aider HTML, HF Gradio, GitHub README tables, …).
- `parsing/normalize.py` is shared FE math only (`normalized_score`, model ids).
- Rankings/models are **uncapped**: each parser keeps the full ordered list the
  source exposes (ZeroEval uses `?top_n=500`, the API maximum).

## Layout

```
cluster/ranks_scraper/
  ranks_scraper/
    discovery.py               # Scrapy spider loader helpers (list/load)
    parsing/
      normalize.py             # 0-100 normalized_score helpers
      sources/                 # per-source parsers (HTML/JSON specifics)
      benchmarks.py            # spider -> FE benchmark card map
      db.py                    # build_snapshot + store_snapshot
    spiders/<source>.py        # name, start_urls, engine, parse_response
    runners/
      crawl_all.py             # crawl then publish
      list_spiders.py          # list via spider loader
      publish_snapshot.py      # publish existing scrapes
```

## Local

```bash
cd cluster/ranks_scraper
uv sync
uv run playwright install chromium   # for playwright spiders
uv run scrapy list
uv run scrapy crawl openrouter_models -s RANKS_SCRAPE_OUT_DIR=/tmp/ranks-scrapes
uv run scrapy crawl zeroeval_swe_bench_pro -s RANKS_SCRAPE_OUT_DIR=/tmp/ranks-scrapes
uv run ranks-publish-snapshot --out /tmp/ranks-scrapes --skip-db
```

### Publish to Postgres

Requires env (same as the old parser CronJob):

- `RANKS_DB_HOST`
- `RANKS_DB_PORT` (default 5432)
- `RANKS_DB_NAME`
- `RANKS_DB_USER`
- `RANKS_DB_PASSWORD`

```bash
export RANKS_DB_HOST=... RANKS_DB_NAME=ranks RANKS_DB_USER=ranks RANKS_DB_PASSWORD=...
uv run ranks-crawl-all --only openrouter_models zeroeval_catalog zeroeval_swe_bench_pro --out /tmp/ranks-scrapes
# or after a crawl:
uv run ranks-publish-snapshot --out /tmp/ranks-scrapes
```

`store_snapshot` creates `ranks_snapshots` if needed, inserts one JSONB row, and
keeps the latest 60 snapshots.

## Image / CronJob

Entrypoint `ranks-crawl-all` crawls then publishes when `RANKS_DB_*` are set.

Chart: `cluster/ranks_chart` `scraperCron` (default disabled) injects DB secret
`ranks-db` into the job.

```bash
make ranks-scraper-image-build
make ranks-scraper-image-push
helm upgrade --install ranks ./cluster/ranks_chart -n ranks \
  --set ranks.scraperCron.enabled=true \
  --set ranks.database.password='...'
```
