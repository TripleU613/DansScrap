"""Command-line interface for running the DansScrap spiders."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scrapy.cmdline import execute

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _build_command(args: argparse.Namespace) -> list[str]:
    command: list[str] = ["scrapy", "crawl", "tech_talk"]

    def add_arg(flag: str, value: str) -> None:
        command.extend([flag, value])

    add_arg("-a", f"board={args.board}")
    add_arg("-a", f"fetch_posts={'true' if args.fetch_posts else 'false'}")
    if args.max_board_pages is not None:
        add_arg("-a", f"max_board_pages={args.max_board_pages}")
    if args.max_topics is not None:
        add_arg("-a", f"max_topics={args.max_topics}")
    if args.max_topic_pages is not None:
        add_arg("-a", f"topic_max_pages={args.max_topic_pages}")
    add_arg("-a", f"bootstrap={args.bootstrap}")
    add_arg("-a", f"cf_mode={args.cf_mode}")

    add_arg("--set", f"LOG_LEVEL={args.log_level}")
    add_arg("--set", f"PLAYWRIGHT_STATE_TTL={args.state_ttl}")
    data_dir = Path(args.data_dir).resolve()
    add_arg("--set", f"DATA_DIR={data_dir}")

    return command


def run_from_args(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run the DansScrap Tech Talk spider with convenient options.",
    )
    parser.add_argument("--board", default="8", help="Board id or full board URL (default: 8)")
    fetch_group = parser.add_mutually_exclusive_group()
    fetch_group.add_argument(
        "--fetch-posts",
        dest="fetch_posts",
        action="store_true",
        default=True,
        help="Download individual topic posts (default)",
    )
    fetch_group.add_argument(
        "--no-fetch-posts",
        dest="fetch_posts",
        action="store_false",
        help="Skip downloading per-topic posts",
    )
    parser.add_argument("--max-board-pages", type=int, default=None, help="Limit number of forum pages crawled")
    parser.add_argument("--max-topics", type=int, default=None, help="Limit number of topics processed")
    parser.add_argument("--max-topic-pages", type=int, default=None, help="Limit pages fetched within each topic")
    parser.add_argument(
        "--bootstrap",
        choices=["auto", "skip"],
        default="auto",
        help="Whether to bootstrap cookies with undetected_chromedriver (default: auto)",
    )
    parser.add_argument(
        "--cf-mode",
        choices=["auto", "manual"],
        default="auto",
        help="Cloudflare handling strategy (default: auto)",
    )
    parser.add_argument(
        "--state-ttl",
        type=int,
        default=12 * 3600,
        help="Seconds to reuse the stored browser state before refreshing (default: 43200)",
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Directory where scraped data is written (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Scrapy log level (default: INFO)",
    )

    args = parser.parse_args(argv)
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    command = _build_command(args)
    execute(command)


def main() -> None:
    try:
        run_from_args()
    except KeyboardInterrupt:
        sys.stderr.write("\nInterrupted by user.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
