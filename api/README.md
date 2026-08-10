# ranks-api

Small FastAPI service for [ranks.urm8.org](https://ranks.urm8.org).

Reads the latest row from Postgres `ranks_snapshots` (same `RANKS_DB_*` env vars as the scraper). Does **not** scrape or rebuild rankings.

## DB stack

- **SQLAlchemy 2.x** (sync) + **psycopg 3** (`psycopg[binary]`)
- URL built as `postgresql+psycopg://…` from `RANKS_DB_HOST|PORT|NAME|USER|PASSWORD`
- One SQLAlchemy `Session` per request via FastAPI `Depends`; engine disposed on shutdown
- `/healthz` does not touch the DB; `/api/data` and `/api/benchmarks/{id}` return **503** if Postgres is unreachable

## Layout

| Path | Role |
|------|------|
| `cluster/ranks_api/` | FastAPI + uv (this package) |
| `cluster/ranks_web/` | Svelte + Tailwind SPA (pnpm) |
| `cluster/ranks_scraper/` | Scrapy ingestion (uv) |
| `cluster/ranks_chart/` | Helm chart deploying API + web + scraperCron |

## Local

```bash
cd cluster/ranks_api
uv sync
export RANKS_DB_HOST=localhost RANKS_DB_PORT=5432
export RANKS_DB_NAME=ranks RANKS_DB_USER=ranks RANKS_DB_PASSWORD=...
uv run ranks-api
# or: uv run uvicorn ranks_api.main:app --reload --port 8080
```

Endpoints: `GET /healthz`, `GET /api/data`, `GET /api/benchmarks/{id}`.

## Image

```bash
docker build -t ghcr.io/urm8/ranks-api:latest .
```
