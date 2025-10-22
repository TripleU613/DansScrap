import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from itemadapter import ItemAdapter

from . import settings as project_settings
from .items import BoardInfoItem, PostItem, TopicSummaryItem


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PostStorePipeline:
    def __init__(self, data_dir: Path | None = None) -> None:
        base = data_dir or project_settings.DATA_DIR
        self.data_dir = Path(base)
        self.board_info: Dict[str, Dict] = {}
        self.topic_summaries: Dict[str, Dict[str, Dict]] = defaultdict(dict)
        self.topic_posts: Dict[Tuple[str, str], Dict[str, Dict]] = defaultdict(dict)

    @classmethod
    def from_crawler(cls, crawler):
        data_dir = crawler.settings.get("DATA_DIR")
        return cls(Path(data_dir) if data_dir else None)

    def open_spider(self, spider):
        self.data_dir.mkdir(exist_ok=True)

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        if isinstance(item, BoardInfoItem):
            board_id = adapter["board_id"]
            payload = adapter.asdict()
            payload["fetched_at"] = iso_now()
            self.board_info[board_id] = payload
            return item

        if isinstance(item, TopicSummaryItem):
            board_id = adapter["board_id"]
            topic_id = adapter["topic_id"]
            payload = adapter.asdict()
            payload["fetched_at"] = iso_now()
            self.topic_summaries[board_id][topic_id] = payload
            return item

        if isinstance(item, PostItem):
            board_id = adapter["board_id"]
            topic_id = adapter["topic_id"]
            post_id = adapter["post_id"]
            payload = adapter.asdict()
            payload["fetched_at"] = iso_now()
            self.topic_posts[(board_id, topic_id)][post_id] = payload
            return item

        return item

    def close_spider(self, spider):
        for board_id, info in self.board_info.items():
            board_path = self._board_dir(board_id)
            board_path.mkdir(parents=True, exist_ok=True)
            self._merge_json(board_path / "board_info.json", info, overwrite=True)

        for board_id, topics in self.topic_summaries.items():
            board_path = self._board_dir(board_id)
            board_path.mkdir(parents=True, exist_ok=True)
            index_file = board_path / "topics_index.json"
            existing = self._load_json(index_file, default={})
            stored_topics = {t["topic_id"]: t for t in existing.get("topics", [])} if existing else {}
            stored_topics.update(topics)
            payload = {
                "board_id": board_id,
                "collected_at": iso_now(),
                "topics": sorted(stored_topics.values(), key=lambda t: (t.get("board_offset", 0), t["topic_id"])),
            }
            if board_id in self.board_info:
                payload["board_name"] = self.board_info[board_id].get("name")
            self._write_json(index_file, payload)

        for (board_id, topic_id), posts in self.topic_posts.items():
            board_path = self._board_dir(board_id)
            topic_dir = board_path / "topics"
            topic_dir.mkdir(parents=True, exist_ok=True)
            topic_file = topic_dir / f"{topic_id}.json"
            existing = self._load_json(topic_file, default={})
            stored_posts = {p["post_id"]: p for p in existing.get("posts", [])} if existing else {}
            stored_posts.update(posts)
            payload = existing or {}
            payload.update({
                "board_id": board_id,
                "topic_id": topic_id,
                "posts_total": len(stored_posts),
                "updated_at": iso_now(),
                "posts": sorted(
                    stored_posts.values(),
                    key=lambda p: (p.get("position", 0), p["post_id"]),
                ),
            })
            self._write_json(topic_file, payload)

    def _board_dir(self, board_id: str) -> Path:
        return self.data_dir / f"board_{board_id}"

    def _load_json(self, path: Path, default):
        if not path.exists():
            return default
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except json.JSONDecodeError:
            return default

    def _write_json(self, path: Path, payload: Dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def _merge_json(self, path: Path, payload: Dict, overwrite: bool = False) -> None:
        if path.exists() and not overwrite:
            existing = self._load_json(path, default={})
            existing.update(payload)
            payload = existing
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
