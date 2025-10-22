import re
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_int(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    digits = re.findall(r"\d+", value.replace(",", ""))
    return int("".join(digits)) if digits else None


def parse_board_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "board" in qs:
        value = qs["board"][0]
    else:
        value = ""
    if not value and "board=" in url:
        value = url.rsplit("board=", 1)[-1]
    value = value.split(";", 1)[0]
    parts = value.split(".")
    return parts[0] if parts and parts[0] else None


def parse_topic_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "topic" not in qs:
        return None
    value = qs["topic"][0].split(";", 1)[0]
    return value.split(".", 1)[0]


def collect_offsets(soup: BeautifulSoup, param: str, ident: str) -> Set[int]:
    offsets: Set[int] = set()
    for link in soup.select("div.pagelinks a.navPages"):
        href = link.get("href")
        if not href:
            continue
        parsed = urlparse(href)
        query = parse_qs(parsed.query)
        if param not in query:
            continue
        entry = query[param][0].split(";", 1)[0]
        if "." not in entry:
            continue
        current_ident, offset = entry.split(".", 1)
        if current_ident != ident:
            continue
        offset = offset.split("#", 1)[0]
        match = re.match(r"(\d+)", offset)
        if match:
            offsets.add(int(match.group(1)))
    offsets.add(0)
    return offsets


def detect_step(offsets: Set[int], default: int) -> int:
    ordered = sorted(offsets)
    diffs = [b - a for a, b in zip(ordered, ordered[1:]) if b > a]
    positives = [d for d in diffs if d > 0]
    return min(positives) if positives else default


def next_offset(offsets: Set[int], current: int) -> Optional[int]:
    candidates = [value for value in offsets if value > current]
    return min(candidates) if candidates else None

