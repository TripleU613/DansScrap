# DansScrap

A Scrapy project that archives the DansDeals "Tech Talk" forum anonymously using Playwright. The project produces structured JSON suitable for downstream LLM or data-ingestion pipelines and keeps a reusable browser storage state so that subsequent runs reuse the Cloudflare solution.

## Features

- **Playwright integration** – uses `scrapy-playwright` (with optional stealth evasions) to render pages and survive Cloudflare challenges.
- **Manual or automatic Cloudflare flow** – run in `auto` mode (attempts to solve using undetected-chromedriver) or `manual` mode (you solve once inside a Playwright window and the resulting storage is reused).
- **Incremental JSON output** – board metadata, topic summaries, and per-topic post archives are merged on every run under `data/`.
- **Python CLI** – cross-platform helper (`python -m dansscrap.cli`) exposes common crawler options instead of the previous batch file.

## Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

Navigate to the repository root and run the CLI:

```bash
python -m dansscrap.cli \
  --board 8 \
  --cf-mode manual \
  --data-dir ./data \
  --log-level INFO
```

Common flags:

- `--board` – SMF board id or full board URL (defaults to `8`).
- `--fetch-posts` / `--no-fetch-posts` – include topic contents (enabled by default).
- `--max-board-pages`, `--max-topics`, `--max-topic-pages` – restrict crawl size for testing.
- `--bootstrap {auto,skip}` – control the undetected-chromedriver bootstrap pass (`auto` by default).
- `--cf-mode {auto,manual}` – choose how to satisfy Cloudflare (auto retries or fully manual Playwright window).
- `--state-ttl` – seconds to reuse the stored storage state (default `43200`).
- `--data-dir` – where JSON output is written (default `./data`).

### Cloudflare workflow

- **Auto** – a helper Chromium window from `undetected_chromedriver` attempts the checkbox and then prompts you if manual input is required. Once the forum loads, the storage state is saved locally and reused next time.
- **Manual** – a Playwright browser window opens and waits indefinitely while you solve the challenge. Press Enter in the terminal only after the forum renders successfully; the command double-checks with a live request before proceeding.

## Output structure

The pipeline writes JSON snapshots under `data/`:

```
data/
  board_<id>/
    board_info.json
    topics_index.json
    topics/
      <topic_id>.json
```

- `board_info.json` – latest metadata for the board (name, description, stats).
- `topics_index.json` – consolidated topic summaries with last-post metadata and crawl offsets.
- `topics/<topic_id>.json` – ordered post history including raw HTML, cleaned text, signatures, likes, and attachments.

## Development

You can still run Scrapy directly if you prefer:

```bash
scrapy crawl tech_talk -a board=8 -a cf_mode=auto --set LOG_LEVEL=INFO
```

The project configuration lives in `dansscrap/settings.py` and `scrapy.cfg`. Adjust `DATA_DIR` via command-line (`--set DATA_DIR=/path/to/output`) or the CLI since both write to the same Scrapy setting.

## Requirements

See [`requirements.txt`](requirements.txt) for the dependency list. Tested against Python 3.13 on Windows; the CLI should work on any platform supported by Playwright and Scrapy.
