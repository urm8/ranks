"""Shared spider helpers for ranks source crawls.

Each spider module owns its ``name``, ``start_urls`` (or ``start_requests``),
source metadata, and ``parse_response`` logic. This base only handles download
wiring (HTTP vs Playwright) and emitting ``FetchedSourceItem``.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import scrapy
from scrapy_playwright.page import PageMethod

from ranks_scraper.items import FetchedSourceItem


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def header_date(headers: Any, *names: str) -> str | None:
    if headers is None:
        return None
    for name in names:
        value = headers.get(name) or headers.get(name.lower())
        if value:
            if isinstance(value, bytes):
                value = value.decode("latin-1", "replace")
            if isinstance(value, (list, tuple)):
                value = value[0]
            return str(value).strip()
    return None


def default_playwright_page_methods() -> list[PageMethod]:
    """Wait for client render, then scroll so virtualized tables hydrate."""
    return [
        PageMethod("wait_for_timeout", 4500),
        PageMethod(
            "evaluate",
            """async () => {
                const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
                const step = Math.max(400, Math.floor(window.innerHeight * 0.85));
                for (let i = 0; i < 40; i++) {
                    const before = document.body
                        ? document.body.scrollHeight
                        : 0;
                    window.scrollBy(0, step);
                    await sleep(200);
                    const after = document.body
                        ? document.body.scrollHeight
                        : 0;
                    const atBottom =
                        (window.scrollY + window.innerHeight) >=
                        (after - 8);
                    if (atBottom && after <= before) break;
                }
                window.scrollTo(0, 0);
                await sleep(300);
            }""",
        ),
        PageMethod("wait_for_timeout", 1000),
    ]


class SourceSpider(scrapy.Spider):
    """Base spider: fetch ``start_urls``, run ``parse_response()``, emit items.

    Subclasses must set class attributes (Scrapy style), not look up a global
    registry:

    - ``name``
    - ``start_urls`` (or override ``start_requests``)
    - ``source_title`` — human-readable source name for FE snapshot
    - ``kind`` — catalog | scores | benchmark | pricing | community | …
    - ``engine`` — ``http`` (default) or ``playwright``
    - optional ``browse_url``
    """

    source_title: str = ""
    browse_url: str | None = None
    kind: str | None = None
    engine: str = "http"
    custom_settings: dict = {}
    # Keep raw bodies out of default JSON artifacts when large; subclasses may override.
    store_body: bool = False
    # Persist rate-limit / soft-fail / validation pages instead of dropping them.
    handle_httpstatus_list = [403, 404, 422, 429, 500, 502, 503]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.source_title:
            raise RuntimeError(f"{type(self).__name__} must set source_title")
        if not self.start_urls and type(self).start is SourceSpider.start:
            raise RuntimeError(
                f"{type(self).__name__} must set start_urls or override start()"
            )
        if self.engine not in ("http", "playwright"):
            raise RuntimeError(
                f"{type(self).__name__} engine must be 'http' or 'playwright', got {self.engine!r}"
            )

    async def start(self):
        """Scrapy >=2.13 entrypoint — yield requests with download-side meta."""
        for url in self.start_urls:
            yield self.make_source_request(url)

    def start_requests(self):
        """Back-compat for Scrapy <2.13 (ignored when ``start()`` is defined)."""
        for url in self.start_urls:
            yield self.make_source_request(url)

    def make_source_request(self, url: str, **meta_extra):
        """Build a Request with download-side meta (playwright flags, timing)."""
        meta: dict[str, Any] = {"source_started": time.time(), **meta_extra}
        if self.engine == "playwright":
            meta.setdefault("playwright", True)
            meta.setdefault("playwright_include_page", False)
            meta.setdefault("playwright_page_methods", default_playwright_page_methods())
        return scrapy.Request(
            url,
            callback=self.parse,
            errback=self.errback,
            meta=meta,
            dont_filter=True,
        )


    # --- generic DOM / model-id helpers (used by spider-owned parsers) ---

    @staticmethod
    def strip_tags(fragment: str) -> str:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            BeautifulSoup = None  # type: ignore[misc, assignment]
        if BeautifulSoup is not None:
            import html as html_lib
            import re as _re

            text = BeautifulSoup(fragment, "lxml").get_text("\n", strip=False)
            return _re.sub(r"[ \t]+", " ", html_lib.unescape(text)).strip()
        import html as html_lib
        import re as _re

        text = _re.sub(r"<script\b.*?</script>", " ", fragment, flags=_re.I | _re.S)
        text = _re.sub(r"<style\b.*?</style>", " ", text, flags=_re.I | _re.S)
        text = _re.sub(r"<br\s*/?>", "\n", text, flags=_re.I)
        text = _re.sub(r"<[^>]+>", " ", text)
        return _re.sub(r"[ \t]+", " ", html_lib.unescape(text)).strip()

    def iter_table_rows(self, body: str):
        """Yield cell texts for each <tr> (uncapped). Prefer bs4/lxml."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            BeautifulSoup = None  # type: ignore[misc, assignment]
        if BeautifulSoup is not None:
            soup = BeautifulSoup(body, "lxml")
            for tr in soup.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if not cells:
                    continue
                yield [c.get_text("\n", strip=True) for c in cells]
            return
        import re as _re

        for tr in _re.findall(r"<tr\b[^>]*>(.*?)</tr>", body, flags=_re.I | _re.S):
            cells = _re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, flags=_re.I | _re.S)
            if not cells:
                continue
            yield [self.strip_tags(c) for c in cells]

    @staticmethod
    def first_number(text: str) -> float | None:
        import re as _re

        match = _re.search(r"(-?\d+(?:\.\d+)?)", (text or "").replace(",", ""))
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def guess_model_id(name: str, creator: str | None = None) -> str:
        """Best-effort OpenRouter-style id from a leaderboard display name."""
        import re as _re

        from ranks_scraper.parsing.normalize import normalize_model_id

        creator_vendor = {
            "anthropic": "anthropic", "openai": "openai", "google": "google",
            "deepmind": "google", "meta": "meta-llama", "meta-llama": "meta-llama",
            "mistral": "mistralai", "mistralai": "mistralai", "xai": "x-ai",
            "x-ai": "x-ai", "x.ai": "x-ai", "deepseek": "deepseek", "qwen": "qwen",
            "alibaba": "qwen", "kimi": "moonshotai", "moonshot": "moonshotai",
            "moonshotai": "moonshotai", "zhipu": "z-ai", "zai": "z-ai", "z-ai": "z-ai",
            "cohere": "cohere", "amazon": "amazon", "nvidia": "nvidia",
            "microsoft": "microsoft", "perplexity": "perplexity", "ai21": "ai21",
            "minimax": "minimax", "01.ai": "01-ai", "01-ai": "01-ai",
            "tencent": "tencent", "bytedance": "bytedance", "ibm": "ibm",
            "databricks": "databricks", "reka": "reka", "nousresearch": "nousresearch",
            "nous research": "nousresearch",
        }
        name_hints = (
            (r"\bclaude\b", "anthropic"), (r"\bgpt-?\d", "openai"), (r"\bo[1-4]\b", "openai"),
            (r"\bgemini\b", "google"), (r"\bgemma\b", "google"), (r"\bllama\b", "meta-llama"),
            (r"\bmistral\b|\bmixtral\b|\bcodestral\b|\bpixtral\b", "mistralai"),
            (r"\bgrok\b", "x-ai"), (r"\bdeepseek\b", "deepseek"), (r"\bqwen\b", "qwen"),
            (r"\bkimi\b|\bmoonshot\b", "moonshotai"), (r"\bglm-?\d|\bchatglm\b", "z-ai"),
            (r"\bcommand\b", "cohere"), (r"\bnemotro?n\b|\bnemotron\b", "nvidia"),
            (r"\bphi-?\d", "microsoft"), (r"\bsonar\b", "perplexity"),
        )
        raw = (name or "").strip()
        if not raw:
            return ""
        if "/" in raw and " " not in raw.split("/", 1)[0]:
            return normalize_model_id(raw)
        cmd = _re.search(
            r"(?:--model\s+|model[:\s]+)([a-z0-9_.-]+/[a-z0-9_./:+-]+)", raw, _re.I
        )
        if cmd:
            return normalize_model_id(cmd.group(1).split(":")[0])
        vendor = None
        if creator:
            key = creator.strip().lower()
            vendor = creator_vendor.get(key)
            if vendor is None:
                for hint, v in creator_vendor.items():
                    if hint in key:
                        vendor = v
                        break
        if vendor is None:
            lower = raw.lower()
            for pattern, v in name_hints:
                if _re.search(pattern, lower):
                    vendor = v
                    break
        vendor = vendor or "unknown"
        text = raw.strip().lower()
        text = _re.sub(r"\([^)]*\)", " ", text)
        text = text.replace("'", "").replace("’", "")
        slug = _re.sub(r"[^a-z0-9]+", "-", text).strip("-")
        if not slug:
            return ""
        for prefix in (f"{vendor}-", "openai-", "anthropic-", "google-", "meta-", "meta-llama-"):
            if slug.startswith(prefix):
                slug = slug[len(prefix):]
                break
        return normalize_model_id(f"{vendor}/{slug}")

    @staticmethod
    def vendor_from_name(name: str) -> str | None:
        import re as _re

        hints = (
            (r"\bclaude\b", "anthropic"), (r"\bgpt-?\d", "openai"), (r"\bo[1-4]\b", "openai"),
            (r"\bgemini\b", "google"), (r"\bgemma\b", "google"), (r"\bllama\b", "meta-llama"),
            (r"\bmistral\b|\bmixtral\b|\bcodestral\b|\bpixtral\b", "mistralai"),
            (r"\bgrok\b", "x-ai"), (r"\bdeepseek\b", "deepseek"), (r"\bqwen\b", "qwen"),
            (r"\bkimi\b|\bmoonshot\b", "moonshotai"), (r"\bglm-?\d|\bchatglm\b", "z-ai"),
            (r"\bcommand\b", "cohere"),
        )
        lower = (name or "").lower()
        for pattern, vendor in hints:
            if _re.search(pattern, lower):
                return vendor
        return None

    def parse_response(self, response) -> dict:
        """Return dict with optional rankings/models/mentions. Override in each spider."""
        raise NotImplementedError(f"{type(self).__name__} must implement parse_response()")

    def models_from_rankings(
        self,
        rankings: list[dict],
        *,
        catalog_source: str | None = None,
    ) -> dict[str, dict]:
        """Build the common FE models dict from ranking rows."""
        source = catalog_source or self.source_title or self.name
        models: dict[str, dict] = {}
        for row in rankings:
            mid = row.get("model_id")
            if not mid:
                continue
            models[mid] = {
                "name": row.get("model") or mid,
                "vendor": mid.split("/")[0] if "/" in mid else "unknown",
                "discovered": True,
                "catalog_sources": [source],
            }
        return models

    def parse(self, response):
        started = response.meta.get("source_started", time.time())
        try:
            body = response.text
        except AttributeError:
            # Binary payloads (xlsx, etc.) — parsers should use response.body.
            body = ""
        parsed: dict = {}
        error = None
        try:
            parsed = self.parse_response(response) or {}
        except Exception as exc:  # noqa: BLE001 - persist parse failure on item
            error = f"parse error: {exc}"
            self.logger.exception("parse_response failed for %s", self.name)

        rankings = parsed.get("rankings") or []
        models = parsed.get("models") or {}
        self.logger.info(
            "%s parse: status=%s rankings=%d models=%d",
            self.name,
            response.status,
            len(rankings),
            len(models),
        )

        body_bytes = getattr(response, "body", b"") or b""
        yield FetchedSourceItem(
            name=self.source_title,
            url=response.url,
            browse_url=self.browse_url,
            kind=self.kind,
            spider=self.name,
            ok=error is None and response.status < 400,
            status=response.status,
            body=body if self.store_body else "",
            bytes=len(body_bytes),
            elapsed_ms=int((time.time() - started) * 1000),
            fetched_at=utc_now_iso(),
            source_date=header_date(response.headers, "Last-Modified", "Date"),
            error=error,
            engine=self.engine,
            rankings=rankings,
            models=models,
            mentions=parsed.get("mentions") or [],
        )

    def errback(self, failure):
        request = failure.request
        started = request.meta.get("source_started", time.time())
        status = None
        if hasattr(failure.value, "response") and failure.value.response is not None:
            status = failure.value.response.status
        yield FetchedSourceItem(
            name=self.source_title,
            url=request.url,
            browse_url=self.browse_url,
            kind=self.kind,
            spider=self.name,
            ok=False,
            status=status,
            body="",
            bytes=0,
            elapsed_ms=int((time.time() - started) * 1000),
            fetched_at=utc_now_iso(),
            source_date=None,
            error=str(failure.value),
            engine=self.engine,
            rankings=[],
            models={},
            mentions=[],
        )
