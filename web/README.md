# ranks-web

Svelte 5 + Tailwind SPA for [ranks.urm8.org](https://ranks.urm8.org).

Consumes `GET /api/data` from `cluster/ranks_api`. Ranking tables show the **top 5** by performance and expand to reveal the rest.

## Local

Terminal 1 — API:

```bash
cd cluster/ranks_api && uv sync && uv run ranks-api
```

Terminal 2 — SPA (Vite proxies `/api` → `:8080`):

```bash
cd cluster/ranks_web
pnpm install
pnpm dev
```

Open http://127.0.0.1:5173

## Build

```bash
pnpm build
```

## Image

```bash
docker build -t ghcr.io/urm8/ranks-web:latest .
```
