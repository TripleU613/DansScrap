from __future__ import annotations

import asyncio
import contextlib
import json
import random
import re
import time
import uuid
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Set, Tuple
from urllib.parse import urlencode

from playwright_stealth import Stealth
from bs4 import BeautifulSoup
import scrapy
import trafilatura
from scrapy_playwright.page import PageMethod
import logging
from playwright.sync_api import sync_playwright
from scrapy import signals

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from .. import settings as project_settings
from ..items import BoardInfoItem, PostItem, TopicSummaryItem
from ..utils import (
    collect_offsets,
    detect_step,
    next_offset,
    normalize_space,
    parse_int,
    parse_topic_id,
)


LOGGER = logging.getLogger(__name__)
_stealth = Stealth()


async def enable_stealth(page, request):
    await _stealth.apply_stealth_async(page)
    page.on("load", lambda: asyncio.create_task(_handle_page_load(page)))


def _normalize_same_site(value: Optional[str]) -> str:
    if not value:
        return "None"
    lower = value.lower()
    if "strict" in lower:
        return "Strict"
    if "lax" in lower:
        return "Lax"
    return "None"


async def _handle_page_load(page) -> None:
    if getattr(page, "_cf_handled", False):
        return
    setattr(page, "_cf_handled", True)
    try:
        await asyncio.sleep(random.uniform(0.8, 1.6))
        title = (await page.title() or "").lower()
        if "just a moment" in title or "attention required" in title:
            success = await _attempt_cloudflare_checkbox(page)
            if not success:
                LOGGER.warning(
                    "Cloudflare prompt detected. If it persists, click the checkbox in the Playwright window."
                )
    except Exception as exc:  # pragma: no cover
        LOGGER.debug("Cloudflare handler error: %s", exc, exc_info=True)


async def _attempt_cloudflare_checkbox(page) -> bool:
    candidates = [
        "input[type='checkbox']",
        "label[for*='cf']",
        "div[class*='checkbox']",
    ]
    frames = [page] + list(page.frames)
    for frame in frames:
        for selector in candidates:
            try:
                locator = frame.locator(selector).first
                if not await locator.count():
                    continue
                box = await locator.bounding_box()
                if not box:
                    continue
                await _move_mouse_human_like(page, box)
                click_x = box["x"] + random.uniform(0.25, 0.75) * box["width"]
                click_y = box["y"] + random.uniform(0.25, 0.75) * box["height"]
                await asyncio.sleep(random.uniform(0.15, 0.35))
                await page.mouse.click(click_x, click_y, delay=random.randint(60, 140))
                await asyncio.sleep(random.uniform(0.4, 1.0))
                return True
            except Exception as exc:
                LOGGER.debug("Checkbox interaction failed via %s: %s", selector, exc)
                continue
    return False


async def _move_mouse_human_like(page, box: Dict[str, float]) -> None:
    viewport = await page.evaluate("({width: innerWidth, height: innerHeight})")
    target_x = box["x"] + random.uniform(0.3, 0.7) * box["width"]
    target_y = box["y"] + random.uniform(0.3, 0.7) * box["height"]
    start_x = max(0, min(target_x + random.uniform(-180, 180), viewport["width"] - 1))
    start_y = max(0, min(target_y + random.uniform(-150, 150), viewport["height"] - 1))
    points = _generate_mouse_path((start_x, start_y), (target_x, target_y))
    for px, py in points:
        px = max(0, min(px, viewport["width"] - 1))
        py = max(0, min(py, viewport["height"] - 1))
        await page.mouse.move(px, py, steps=random.randint(8, 15))
        await asyncio.sleep(random.uniform(0.02, 0.08))


def _generate_mouse_path(start: Tuple[float, float], end: Tuple[float, float]) -> Sequence[Tuple[float, float]]:
    points = []
    segments = random.randint(3, 6)
    for i in range(1, segments):
        t = i / segments
        jitter = random.uniform(-25, 25)
        px = start[0] + (end[0] - start[0]) * t + jitter
        py = start[1] + (end[1] - start[1]) * t + random.uniform(-20, 20)
        points.append((px, py))
    points.append(end)
    return points


class TechTalkSpider(scrapy.Spider):
    name = "tech_talk"
    allowed_domains = ["forums.dansdeals.com"]
    handle_httpstatus_list = [403, 520]

    custom_settings = {
        "PLAYWRIGHT_PAGE_CLOSE_ON_ERROR": True,
    }
    cf_max_retries = 3
    default_user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        board: str = "8",
        fetch_posts: bool = "true",
        max_board_pages: Optional[int] = None,
        max_topics: Optional[int] = None,
        topic_max_pages: Optional[int] = None,
        *args,
        **kwargs,
    ) -> None:
        self.bootstrap_mode = kwargs.pop("bootstrap", "auto")
        self.storage_state_ttl = int(kwargs.pop("state_ttl", 12 * 3600))
        self.cf_mode = kwargs.pop("cf_mode", "auto").lower()
        if self.cf_mode not in {"auto", "manual"}:
            raise ValueError("cf_mode must be 'auto' or 'manual'")
        super().__init__(*args, **kwargs)
        self.board_id = board.split(".")[0]
        self.fetch_posts = str(fetch_posts).lower() not in {"0", "false", "no"}
        self.max_board_pages = int(max_board_pages) if max_board_pages else None
        self.max_topics = int(max_topics) if max_topics else None
        self.topic_max_pages = int(topic_max_pages) if topic_max_pages else None
        self.board_pages_processed = 0
        self.topic_seen: Set[str] = set()
        self.board_metadata_emitted = False
        self.storage_state_path: Optional[Path] = None
        self.data_dir: Optional[Path] = None
        self.bootstrap_driver = None

    def start_requests(self) -> Iterable[scrapy.Request]:
        self._ensure_storage_state()
        params = {"board": f"{self.board_id}.0"}
        url = f"https://forums.dansdeals.com/index.php?{urlencode(params)}"
        yield scrapy.Request(
            url,
            meta=self._build_meta({"board_offset": 0, "cf_retry": 0}),
            callback=self.parse_board,
        )

    def _build_meta(self, extra: Optional[Dict] = None, *, new_context: bool = False) -> Dict:
        page_methods = [PageMethod("wait_for_load_state", "domcontentloaded")]
        if self.cf_mode != "manual":
            page_methods.extend(
                [
                    PageMethod("wait_for_load_state", "networkidle"),
                    PageMethod("wait_for_timeout", 8000),
                ]
            )
        meta: Dict = {
            "playwright": True,
            "playwright_page_methods": page_methods,
            "playwright_context_kwargs": {
                "ignore_https_errors": True,
                "user_agent": self.default_user_agent,
                "viewport": {"width": 1280, "height": 720},
            },
        }
        if self.cf_mode != "manual":
            meta["playwright_page_init_callback"] = enable_stealth
        if self.storage_state_path and self.storage_state_path.exists():
            meta["playwright_context_kwargs"]["storage_state"] = str(self.storage_state_path)
        if new_context:
            meta["playwright_context"] = f"context-{uuid.uuid4()}"
        if extra:
            meta.update(extra)
        return meta

    def _retry_with_new_context(self, response: scrapy.http.Response) -> Optional[scrapy.Request]:
        if self.cf_mode == "manual":
            self.logger.error("Manual mode encountered HTTP %s on %s; aborting retries.", response.status, response.url)
            return None

        retry_count = response.meta.get("cf_retry", 0)
        if retry_count >= self.cf_max_retries:
            self.logger.error("Exceeded Cloudflare retry limit for %s", response.url)
            return None
        extra: Dict = {
            key: value
            for key, value in response.meta.items()
            if key in {"board_offset", "topic_offset", "board_id", "topic_id"}
        }
        extra["cf_retry"] = retry_count + 1
        request = response.request.replace(
            meta=self._build_meta(extra, new_context=True),
            dont_filter=True,
        )
        self.logger.warning(
            "Cloudflare challenge (%s) on %s. Retrying (%s/%s).",
            response.status,
            response.url,
            retry_count + 1,
            self.cf_max_retries,
        )
        return request

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider.storage_state_ttl = crawler.settings.getint(
            "PLAYWRIGHT_STATE_TTL", spider.storage_state_ttl
        )
        data_dir_setting = crawler.settings.get("DATA_DIR")
        if data_dir_setting:
            spider.data_dir = Path(data_dir_setting)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    def spider_closed(self):
        if self.bootstrap_driver:
            with contextlib.suppress(Exception):
                self.bootstrap_driver.quit()
            self.bootstrap_driver = None

    def _prompt(self, message: str, default: str = "") -> str:
        try:
            response = input(message)
        except (EOFError, KeyboardInterrupt):
            return default
        return response.strip()

    def _manual_playwright_bootstrap(self, storage_path: Path) -> Dict:
        self.logger.info("Manual mode: launching Chromium window for you to solve Cloudflare.")
        launch_opts = project_settings.PLAYWRIGHT_LAUNCH_OPTIONS
        args = launch_opts.get("args", [])
        headless = launch_opts.get("headless", False)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless, args=args)
            context = browser.new_context(
                user_agent=self.default_user_agent,
                viewport={"width": 1280, "height": 720},
            )
            page = context.new_page()
            page.goto("https://forums.dansdeals.com/index.php", wait_until="domcontentloaded")
            self.logger.info(
                "Manual mode: a Chromium window is open. Solve the Cloudflare prompt there."
            )
            while True:
                response = self._prompt(
                    "Press Enter when the forum loads (or type SKIP to abort): ", default=""
                ).lower()
                if response == "skip":
                    context.close()
                    browser.close()
                    self.logger.warning("Manual bootstrap aborted by user.")
                    return {}
                title = (page.title() or "").lower()
                ready = page.evaluate("document.readyState")
                has_main = bool(page.query_selector("div#main_content_section"))
                if "just a moment" not in title and "attention required" not in title and ready == "complete" and has_main:
                    # double-check by issuing a request with current storage state
                    try:
                        test_response = context.request.get(
                            "https://forums.dansdeals.com/index.php?board=8.0"
                        )
                        status_code = test_response.status
                    except Exception as exc:
                        self.logger.debug("Manual verification request failed: %s", exc)
                        status_code = 0
                    if status_code == 200:
                        break
                    print(
                        f"Received HTTP {status_code} when checking the forum. Please ensure the challenge is solved, then press Enter again."
                    )
                    continue
                print(
                    "Cloudflare page still loading. Finish the challenge in the Chromium window, then press Enter again."
                )
            state = context.storage_state()
            storage_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            self.logger.info("Manual storage state captured at %s", storage_path)
            context.close()
            browser.close()
            return state

    def _auto_bootstrap(self) -> Dict:
        self.logger.info("Bootstrapping Cloudflare cookies with undetected_chromedriver.")
        try:
            import undetected_chromedriver as uc
        except ImportError:  # pragma: no cover
            self.logger.error("undetected_chromedriver is not installed; cannot bootstrap session.")
            return {}

        options = uc.ChromeOptions()
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        driver = uc.Chrome(options=options)
        self.bootstrap_driver = driver
        close_driver = False
        cookies = []
        try:
            driver.get("https://forums.dansdeals.com/index.php")
            solved = False
            try:
                WebDriverWait(driver, 120).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                    and bool(d.find_elements(By.CSS_SELECTOR, "div#main_content_section"))
                )
                solved = True
            except TimeoutException:
                self.logger.warning(
                    "Cloudflare challenge still active. Solve it in the helper window, then confirm here."
                )

            if not solved:
                manual_deadline = time.time() + 300
                while True:
                    try:
                        title = (driver.title or "").lower()
                        ready = driver.execute_script("return document.readyState")
                        has_main = bool(driver.find_elements(By.CSS_SELECTOR, "div#main_content_section"))
                    except Exception:
                        break
                    if "just a moment" not in title and "attention required" not in title and ready == "complete" and has_main:
                        solved = True
                        break
                    if time.time() > manual_deadline:
                        self.logger.warning("Manual wait timed out; continuing without confirmed cookies.")
                        break
                    response = self._prompt(
                        "Type DONE when the forum loads (SKIP to continue without cookies): ",
                        default="done",
                    ).lower()
                    if response == "skip":
                        break
                    if response not in ("done", ""):
                        print("Unrecognised response. Type DONE or SKIP.")
                        continue
                    print("Still waiting for the Cloudflare page to finish loading...")
                    time.sleep(2)
            cookies = driver.get_cookies()
            if solved and cookies:
                answer = self._prompt(
                    "Cloudflare cleared. Close helper window now? [Y/n]: ", default="y"
                ).lower()
                if answer in ("", "y", "yes"):
                    close_driver = True
                else:
                    self.logger.info("Keeping helper window open; close it manually when convenient.")
        finally:
            if close_driver:
                with contextlib.suppress(Exception):
                    driver.quit()
                self.bootstrap_driver = None

        formatted = [
            {
                "name": cookie.get("name"),
                "value": cookie.get("value"),
                "domain": cookie.get("domain") or "forums.dansdeals.com",
                "path": cookie.get("path") or "/",
                "expires": cookie.get("expiry", -1),
                "httpOnly": cookie.get("httpOnly", False),
                "secure": cookie.get("secure", True),
                "sameSite": _normalize_same_site(cookie.get("sameSite")),
            }
            for cookie in cookies
            if cookie.get("name") and cookie.get("value")
        ]

        return {
            "cookies": formatted,
            "origins": [
                {
                    "origin": "https://forums.dansdeals.com",
                    "localStorage": [],
                    "sessionStorage": [],
                }
            ],
        }

    def _ensure_storage_state(self) -> None:
        base_dir = self.data_dir or (Path(__file__).resolve().parent.parent / "output")
        base_dir.mkdir(parents=True, exist_ok=True)
        storage_path = base_dir / "playwright_state.json"
        self.storage_state_path = storage_path
        if storage_path.exists():
            age = time.time() - storage_path.stat().st_mtime
            if age < self.storage_state_ttl:
                self.logger.debug(
                    "Reusing existing Playwright storage state (%ss old)",
                    int(age),
                )
                return
            self.logger.info(
                "Existing storage state is stale (age %ss); refreshing.",
                int(age),
            )

        if self.cf_mode == "manual":
            state = self._manual_playwright_bootstrap(storage_path)
        else:
            if self.bootstrap_mode == "skip":
                self.logger.warning(
                    "Skipping automated bootstrap; continuing without storage state."
                )
                return
            state = self._auto_bootstrap()

        if not state or not state.get("cookies"):
            self.logger.warning("No cookies captured during bootstrap; continuing without storage state.")
            return

        storage_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        self.logger.info("Stored Playwright storage state at %s", storage_path)

    def parse_board(self, response: scrapy.http.Response):
        if response.status in (403, 520):
            retry_request = self._retry_with_new_context(response)
            if retry_request:
                yield retry_request
            return
        board_offset = response.meta.get("board_offset", 0)
        soup = BeautifulSoup(response.text, "html.parser")

        if not self.board_metadata_emitted:
            info_item = self._build_board_info(soup, response.url)
            if info_item:
                yield info_item
            self.board_metadata_emitted = True

        topics = self._extract_topics(soup, board_offset, response.url)
        for topic in topics:
            if topic["topic_id"] in self.topic_seen:
                continue
            if self.max_topics and len(self.topic_seen) >= self.max_topics:
                break
            self.topic_seen.add(topic["topic_id"])
            yield TopicSummaryItem(**topic)
            if self.fetch_posts:
                yield from self._schedule_topic(topic["topic_id"], topic["topic_url"], 0)

        self.board_pages_processed += 1
        if self.max_board_pages and self.board_pages_processed >= self.max_board_pages:
            return

        offsets = collect_offsets(soup, "board", self.board_id)
        step = detect_step(offsets, 25)
        next_off = next_offset(offsets, board_offset)
        if next_off is None:
            return
        params = {"board": f"{self.board_id}.{next_off}"}
        next_url = f"https://forums.dansdeals.com/index.php?{urlencode(params)}"
        meta = self._build_meta(
            {
                "board_offset": next_off,
                "board_step": step,
                "cf_retry": 0,
            }
        )
        yield scrapy.Request(
            next_url,
            callback=self.parse_board,
            meta=meta,
        )

    def _build_board_info(self, soup: BeautifulSoup, url: str) -> Optional[BoardInfoItem]:
        title_el = soup.select_one("div.navigate_section li.last span")
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            head_title = soup.select_one("title")
            title = head_title.get_text(strip=True) if head_title else f"Board {self.board_id}"
        description_el = soup.select_one("div#main_content_section > p.description")
        description = (
            description_el.get_text(" ", strip=True) if description_el else ""
        )
        stats_text = ""
        stat_rows = soup.select("div#main_content_section div.titlebg span.smalltext")
        if stat_rows:
            stats_text = " ".join(normalize_space(row.get_text(" ", strip=True)) for row in stat_rows)
        posts = parse_int(stats_text) if stats_text else None
        info = BoardInfoItem()
        info["board_id"] = self.board_id
        info["name"] = title
        info["description"] = description
        info["topics"] = None
        info["posts"] = posts
        info["url"] = url
        return info

    def _extract_topics(self, soup: BeautifulSoup, offset: int, page_url: str) -> Iterable[Dict]:
        rows = soup.select("div#messageindex table.table_grid tbody tr")
        for row in rows:
            subject_link = row.select_one("td.subject span[id^='msg_'] > a")
            if not subject_link:
                continue
            topic_url = subject_link.get("href")
            topic_id = parse_topic_id(topic_url)
            if not topic_id:
                continue
            starter_el = row.select_one("td.subject p a[href*='profile;u=']")
            stats_el = row.select_one("td.stats")
            stats_text = stats_el.get_text(" ", strip=True) if stats_el else ""
            numbers = [
                int(num.replace(",", ""))
                for num in re.findall(r"\d[\d,]*", stats_text)
            ]
            replies = numbers[0] if numbers else None
            views = numbers[1] if len(numbers) > 1 else None
            last_post_cell = row.select_one("td.lastpost")
            last_author = None
            last_time = None
            last_link = None
            if last_post_cell:
                profile_link = last_post_cell.select_one("a[href*='profile;u=']")
                if profile_link:
                    last_author = profile_link.get_text(strip=True)
                last_anchor = last_post_cell.select_one("a[href*='topic=']")
                if last_anchor:
                    last_link = last_anchor.get("href")
                time_el = last_post_cell.find("strong")
                if time_el:
                    parts = [time_el.get_text(strip=True)]
                    sibling = time_el.next_sibling
                    while sibling:
                        if getattr(sibling, "name", None) == "br":
                            break
                        text = sibling.strip() if isinstance(sibling, str) else sibling.get_text(strip=True)
                        if text:
                            parts.append(text)
                        sibling = sibling.next_sibling
                    last_time = normalize_space(" ".join(parts))
                if not last_time:
                    last_time = normalize_space(last_post_cell.get_text(" ", strip=True))
            yield {
                "board_id": self.board_id,
                "board_offset": offset,
                "topic_id": topic_id,
                "subject": subject_link.get_text(strip=True),
                "starter": starter_el.get_text(strip=True) if starter_el else "",
                "replies": replies,
                "views": views,
                "last_post_author": last_author,
                "last_post_time": last_time,
                "last_post_link": last_link,
                "topic_url": topic_url,
                "page_url": page_url,
            }

    def _schedule_topic(self, topic_id: str, url: str, offset: int):
        yield scrapy.Request(
            url,
            callback=self.parse_topic,
            meta=self._build_meta(
                {
                    "board_id": self.board_id,
                    "topic_id": topic_id,
                    "topic_offset": offset,
                    "cf_retry": 0,
                }
            ),
        )

    def parse_topic(self, response: scrapy.http.Response):
        if response.status in (403, 520):
            retry_request = self._retry_with_new_context(response)
            if retry_request:
                yield retry_request
            return
        topic_id = response.meta["topic_id"]
        board_id = response.meta["board_id"]
        offset = response.meta.get("topic_offset", 0)
        soup = BeautifulSoup(response.text, "html.parser")
        posts = self._extract_posts(soup, board_id, topic_id, offset, response.url)
        for post in posts:
            yield PostItem(**post)

        pages_seen = response.meta.get("pages_seen", 0) + 1
        if self.topic_max_pages and pages_seen >= self.topic_max_pages:
            return

        offsets = collect_offsets(soup, "topic", topic_id)
        next_off = next_offset(offsets, offset)
        if next_off is None:
            return

        params = {"topic": f"{topic_id}.{next_off}"}
        next_url = f"https://forums.dansdeals.com/index.php?{urlencode(params)}"
        yield scrapy.Request(
            next_url,
            callback=self.parse_topic,
            meta=self._build_meta(
                {
                    "board_id": board_id,
                    "topic_id": topic_id,
                    "topic_offset": next_off,
                    "pages_seen": pages_seen,
                    "cf_retry": 0,
                }
            ),
        )

    def _extract_posts(
        self,
        soup: BeautifulSoup,
        board_id: str,
        topic_id: str,
        offset: int,
        page_url: str,
    ):
        wrappers = soup.select("div#forumposts div.post_wrapper")
        for idx, wrapper in enumerate(wrappers):
            content_div = wrapper.select_one("div.post div.inner")
            if not content_div:
                continue
            post_id_attr = content_div.get("id", "")
            if not post_id_attr.startswith("msg_"):
                continue
            post_id = post_id_attr.replace("msg_", "")
            poster_link = wrapper.select_one("div.poster h4 a")
            author_name = poster_link.get_text(strip=True) if poster_link else ""
            author_profile = poster_link.get("href") if poster_link else None
            author_title = None
            author_details = []
            extra_info = wrapper.select_one(f"ul#msg_{post_id}_extra_info")
            if extra_info:
                for li in extra_info.select("li"):
                    text = li.get_text(" ", strip=True)
                    if text:
                        author_details.append(text)
                title_el = extra_info.select_one("li.membergroup")
                if title_el:
                    author_title = normalize_space(title_el.get_text(" ", strip=True))
            subject_el = wrapper.select_one(f"h5#subject_{post_id} a")
            subject = subject_el.get_text(strip=True) if subject_el else None
            permalink = subject_el.get("href") if subject_el else None
            time_el = wrapper.select_one("div.keyinfo div.smalltext")
            posted_at = normalize_space(time_el.get_text(" ", strip=True)) if time_el else None
            content_html = content_div.decode_contents()
            content_text = content_div.get_text("\n", strip=True)
            extracted_text = trafilatura.extract(
                f"<html><body>{content_html}</body></html>",
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )
            if not extracted_text:
                extracted_text = normalize_space(content_text)
            signature_div = wrapper.select_one("div.signature")
            signature_html = signature_div.decode_contents().strip() if signature_div else None
            signature_text = signature_div.get_text(" ", strip=True) if signature_div else None
            edited_div = wrapper.select_one("div.moderatorbar div.modified")
            edited = normalize_space(edited_div.get_text(" ", strip=True)) if edited_div else None
            likes_span = wrapper.select_one("div.like_post_box span")
            likes = parse_int(likes_span.get_text(strip=True)) if likes_span else None
            attachments = []
            for attach in wrapper.select("div.attachments li"):
                link = attach.find("a")
                if not link:
                    continue
                attachments.append(
                    {
                        "name": link.get_text(strip=True),
                        "url": link.get("href"),
                        "details": normalize_space(attach.get_text(" ", strip=True)),
                    }
                )
            yield {
                "board_id": board_id,
                "topic_id": topic_id,
                "post_id": post_id,
                "position": offset + idx + 1,
                "author_name": author_name,
                "author_profile": author_profile,
                "author_title": author_title,
                "author_details": author_details,
                "subject": subject,
                "posted_at": posted_at,
                "permalink": permalink,
                "content_html": content_html,
                "content_text": content_text,
                "extracted_text": extracted_text,
                "signature_html": signature_html,
                "signature_text": signature_text,
                "edited": edited,
                "likes": likes,
                "attachments": attachments,
                "page_url": page_url,
            }
