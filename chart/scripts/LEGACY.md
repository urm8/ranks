# Legacy

`app.py` (and any recovered `parser.py`) under this directory are the old
monolithic HTML server. They are **not** deployed by the Helm chart.

Primary stack:

- `cluster/ranks_web` — Svelte SPA
- `cluster/ranks_api` — FastAPI snapshot reader
- `cluster/ranks_scraper` — Scrapy ingestion
