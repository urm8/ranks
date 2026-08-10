FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml README.md ./
COPY ranks_api ./ranks_api

RUN uv sync --no-dev --no-editable \
 && useradd --system --uid 1000 --home /tmp app \
 && chown -R app:app /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PORT=8080
EXPOSE 8080

USER app
CMD ["uvicorn", "ranks_api.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
