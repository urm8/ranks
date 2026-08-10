# ranks.urm8.org agent notes

**Goal:** Operate and extend the ranks.urm8.org stack extracted from the ht cluster repo.

## Layout
- `api/` — FastAPI + SQLAlchemy/psycopg (uv)
- `web/` — Svelte 5 + Tailwind (pnpm)
- `scraper/` — Scrapy per-source spiders (uv); samples beside spiders
- `chart/` — Helm (API + nginx web + scraperCron + db-init)

## Deploy
- CI: push to `master` → `.github/workflows/deploy.yml` (GHCR arm64 images + helm)
- Local kubeconfig / `chart/values.yaml` are gitignored (cluster topology stays out of the public repo); start from `chart/values.example.yaml`
- Images: `ghcr.io/urm8/ranks-{api,web,scraper}` (OrbStack for local builds)
- Ingress host: `ranks.urm8.org`

## Gotchas
- Spiders own parse logic in-module; do not reintroduce a central SOURCES URL registry for crawling
- Playwright only when HTTP body is useless
- API does not scrape; scraper publishes `ranks_snapshots`
- Master node OOM / k3s TLS issues: see ht learned rule hetzner-k3s-apiserver-oom

## Status
- 2026-08-07: Project extracted from `ht/cluster/ranks_*` into this repo for dedicated ownership and deploy of SPA+API+scraper stack.
