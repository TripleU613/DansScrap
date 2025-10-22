# DansDeals Tech Talk Scraper

This Scrapy project crawls the DansDeals “Tech Talk” board anonymously using Playwright for page rendering and Trafilatura for content extraction. It mirrors the JSON structure produced by the earlier `undetected_chromedriver` script while leaning on Scrapy’s scheduling, throttling, and pipeline system.

## Key Features

- **Playwright + Stealth**: Uses `scrapy-playwright` with `playwright-stealth` evasions to survive the Cloudflare challenge. Cookies are persisted as a Playwright storage state so subsequent runs reuse a clean session.
- **Undetected-Chromedriver Bootstrap**: When the storage state is missing or stale, the spider launches `undetected_chromedriver` once to clear the Cloudflare check (manual interaction may still be required the first time). Captured cookies are written to `output/playwright_state.json`.
- **Structured Output**: The pipeline saves board metadata, topic indices, and per-topic post dumps under `output/board_<id>/`. Trafilatura produces clean, plain-text content alongside the original HTML for each post.
- **Incremental Runs**: Re-running the spider merges new topic summaries and appends newly-seen posts. Existing JSON is preserved and updated in-place.

## Installation

```powershell
pip install scrapy scrapy-playwright playwright-stealth trafilatura undetected-chromedriver
playwright install chromium
```

## Usage

Run a small smoke test (first page, first topic, first page of posts):

```powershell
cd C:\Users\usher\Desktop\danscron\dansdeals_play
scrapy crawl tech_talk -a max_board_pages=1 -a max_topics=1 -a topic_max_pages=1
```

Full anonymous crawl of Tech Talk (board id 8), including posts:

```powershell
scrapy crawl tech_talk -a board=8 --set LOG_LEVEL=INFO
```

### Cloudflare Modes

- `cf_mode=auto` (default) – script tries to solve the checkbox automatically, then prompts you to finish in the helper Chrome window if needed. Falls back to importing cookies from your main Chrome profile when available.
- `cf_mode=manual` – opens a visible Playwright Chromium window and pauses until you solve Cloudflare there. Once you press Enter in the console, that same session's storage is persisted for the crawl.

Example manual run:

```powershell
scrapy crawl tech_talk -a board=8 -a cf_mode=manual --set LOG_LEVEL=INFO
```

### Arguments

- `board` – Numeric board id or SMF board URL (defaults to `8`).
- `fetch_posts` – `true`/`false` to enable or skip per-topic post harvesting (`true` by default).
- `max_board_pages`, `max_topics`, `topic_max_pages` – Optional caps for staged runs.
- `bootstrap` – Set to `skip` to bypass the `undetected_chromedriver` bootstrap (not recommended unless the storage state already exists).
- `state_ttl` – Seconds before the Playwright storage state is considered stale (default 12 hours).

### Data Outputs

```
output/
  board_8/
    board_info.json
    topics_index.json
    topics/
      <topic_id>.json
```

- `board_info.json` – Last-fetched board metadata.
- `topics_index.json` – Consolidated topic summaries with offsets and last-post info.
- `topics/<topic_id>.json` – Full post history for the topic, including raw HTML, cleaned text (`extracted_text`), signatures, likes, and attachments.

### Cloudflare Tips

The bootstrap step opens a visible Chromium window via `undetected_chromedriver`. If Cloudflare presents a “Just a moment…” spinner or checkbox, the spider wiggles a virtual mouse and attempts an off-center click automatically. When prompted in the console, finish the check manually in that window and press **Enter**—the gathered cookies are saved to `output/playwright_state.json` and reused afterwards. Keep the window open until the normal forum landing page loads; subsequent Playwright runs will reuse the stored state. In `cf_mode=manual`, a Playwright browser opens instead and waits indefinitely for you to solve the challenge before the crawl continues.

## Scheduling

The project works well with Windows Task Scheduler. Example daily refresh at 02:15:

```powershell
schtasks /Create /SC DAILY /ST 02:15 /TN DansDealsTechTalkScrape ^
  /TR "\"C:\Users\usher\AppData\Local\Programs\Python\Python313\python.exe\" C:\Users\usher\Desktop\danscron\dansdeals_play\run_daily.py\""
```

Where `run_daily.py` can simply call Scrapy via `subprocess` and log the outcome; remember to reuse the same `output` directory so incremental merges work correctly.

## Post-processing

Each `topics/<topic_id>.json` file includes both `content_html` and Trafilatura’s `extracted_text`. Feed the plain text directly into your LLM pipeline, or add additional tooling (vectorization, OpenAI batch ingestion, etc.) on top. The JSON layout is tolerant of appending new posts, so you can safely diff changes between runs.
