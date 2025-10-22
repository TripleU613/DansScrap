from pathlib import Path


BOT_NAME = "dansdeals_play"

SPIDER_MODULES = ["dansdeals_play.spiders"]
NEWSPIDER_MODULE = "dansdeals_play.spiders"

ROBOTSTXT_OBEY = False

LOG_LEVEL = "INFO"

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 90 * 1000
PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": False,
    "args": [
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--start-maximized",
    ],
}

DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

CONCURRENT_REQUESTS = 8
DOWNLOAD_DELAY = 1.5
RANDOMIZE_DOWNLOAD_DELAY = True

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

ITEM_PIPELINES = {
    "dansdeals_play.pipelines.PostStorePipeline": 300,
}

DATA_DIR = Path(__file__).resolve().parent.parent / "output"
DATA_DIR.mkdir(exist_ok=True)

FEED_EXPORT_ENCODING = "utf-8"
