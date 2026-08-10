# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY pyproject.toml uv.lock* README.md ./
COPY ranks_scraper ./ranks_scraper
COPY scrapy.cfg ./

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then uv sync --frozen --no-dev; else uv sync --no-dev; fi

FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
      libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
      libgbm1 libasound2 libpango-1.0-0 libcairo2 libx11-xcb1 libx11-6 \
      libxcb1 libxext6 libxshmfence1 fonts-liberation ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    SCRAPY_SETTINGS_MODULE=ranks_scraper.settings \
    RANKS_SCRAPE_OUT_DIR=/data/scrapes \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY --from=builder /app /app

RUN playwright install chromium \
    && useradd --create-home --uid 1000 ranks \
    && mkdir -p /data/scrapes /ms-playwright \
    && chown -R ranks:ranks /app /data /ms-playwright

USER ranks
WORKDIR /app
VOLUME ["/data/scrapes"]

ENTRYPOINT ["ranks-crawl-all"]
CMD ["--out", "/data/scrapes"]
