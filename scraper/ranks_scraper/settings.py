import os

BOT_NAME = "ranks_scraper"

SPIDER_MODULES = ["ranks_scraper.spiders"]
NEWSPIDER_MODULE = "ranks_scraper.spiders"

ADDONS = {}

ROBOTSTXT_OBEY = False
COOKIES_ENABLED = False
TELNETCONSOLE_ENABLED = False
LOG_LEVEL = os.environ.get("RANKS_SCRAPY_LOG_LEVEL", "INFO")

DEFAULT_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}

CONCURRENT_REQUESTS = int(os.environ.get("RANKS_SCRAPY_CONCURRENT_REQUESTS", "8"))
DOWNLOAD_TIMEOUT = int(os.environ.get("RANKS_SCRAPY_DOWNLOAD_TIMEOUT", "45"))
DOWNLOAD_MAXSIZE = int(os.environ.get("RANKS_MAX_BODY_BYTES", "8000000"))
RETRY_TIMES = 2

ITEM_PIPELINES = {
    "ranks_scraper.pipelines.FetchedSourcePipeline": 300,
}

RANKS_SCRAPE_OUT_DIR = os.environ.get("RANKS_SCRAPE_OUT_DIR", "/data/scrapes")

DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "args": ["--no-sandbox", "--disable-dev-shm-usage"],
}
PLAYWRIGHT_CONTEXTS = {
    "default": {
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1400, "height": 900},
    },
}
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = DOWNLOAD_TIMEOUT * 1000

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
FEED_EXPORT_ENCODING = "utf-8"
