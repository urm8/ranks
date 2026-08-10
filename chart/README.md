# ranks Helm chart

Deploys the ranks stack (API, web SPA, scraper CronJob).

| Component | Image |
|-----------|--------|
| API | `ghcr.io/urm8/ranks-api` |
| Web SPA | `ghcr.io/urm8/ranks-web` |
| Scraper CronJob | `ghcr.io/urm8/ranks-scraper` |

Copy `values.example.yaml` → `values.yaml` for local/CI (gitignored). Ingress: `ranks.urm8.org` (`/api` + `/healthz` → API, `/` → web).

`scripts/app.py` under this chart is **legacy** and is not mounted or deployed.