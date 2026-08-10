# ranks.urm8.org

AI model ranks dashboard: Scrapy ingestion → Postgres snapshots → FastAPI + Svelte SPA.

## Layout

| Path | Stack |
|------|--------|
| `api/` | FastAPI + SQLAlchemy + psycopg (**uv**) |
| `web/` | Svelte 5 + Tailwind SPA (**pnpm**) |
| `scraper/` | Scrapy spiders + Playwright when needed (**uv**) |
| `chart/` | Helm chart for API, web, scraper CronJob, DB init |

## Local

```bash
# API
cd api && uv sync && uv run ranks-api   # :8080

# Web (proxies /api → API)
cd web && pnpm install && pnpm dev      # :5173

# Scraper
cd scraper && uv sync
uv run scrapy list
uv run ranks-crawl-all --only openrouter_models zeroeval_swe_bench_pro --out /tmp/scrapes --skip-db
```

## Deploy

Pushes to `master` run `.github/workflows/deploy.yml` (build GHCR arm64 images + helm deploy).

Local/manual:

```bash
cp chart/values.example.yaml chart/values.yaml   # fill cluster-specific fields locally
export KUBECONFIG=./hetzner-k3s_kubeconfig.yaml
make images          # PLATFORM=linux/arm64 by default
make push
make deploy PASSWORD=...
make scraper-run     # optional
```

Site: https://ranks.urm8.org

## Notes

- Each scraper spider owns `start_urls`, consts, and parse methods; sample fixtures live as `spiders/<name>_sample.{html,json}`.
- API reads latest `ranks_snapshots` row; scraper writes snapshots via `store_snapshot`.
- UI shows top 5 rankings sorted by performance with expand for the full list.
