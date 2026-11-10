"""Local, offline YouTube video bookmarks for NeonTube Downloader.

Only non-sensitive public video metadata is stored in the user's AppData.
This module does not call YouTube and never saves API credentials.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")


def normalize_favorite(item: dict) -> dict | None:
    """Turn one YouTube Data API result (or stored entry) into a safe bookmark."""
    if not isinstance(item, dict):
        return None
    video_id = item.get("id")
    if not isinstance(video_id, str) or VIDEO_ID.fullmatch(video_id) is None:
        return None
    title = str(item.get("title") or "YouTube-Video").strip()[:300]
    channel = str(item.get("channel") or "YouTube").strip()[:140]
    duration = str(item.get("duration") or "–").strip()[:32]
    created = item.get("added_at")
    if not isinstance(created, str) or not created:
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": title or "YouTube-Video",
        "channel": channel or "YouTube",
        "duration": duration or "–",
        "added_at": created,
    }


class FavoriteStore:
    """Small persistent store with atomic writes and deduplication by video ID."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._entries: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            raw = {"items": []}
        if isinstance(raw, dict):
            raw = raw.get("items", [])
        if not isinstance(raw, list):
            raw = []
        entries: dict[str, dict] = {}
        for candidate in raw:
            item = normalize_favorite(candidate)
            if item is not None and item["id"] not in entries:
                entries[item["id"]] = item
        self._entries = entries

    def all(self) -> list[dict]:
        return [dict(item) for item in self._entries.values()]

    def has(self, video_id: str) -> bool:
        return video_id in self._entries

    def add(self, candidate: dict) -> bool:
        item = normalize_favorite(candidate)
        if item is None:
            raise ValueError("Ungültige YouTube-Video-ID")
        if self.has(item["id"]):
            return False
        self._entries[item["id"]] = item
        try:
            self.save()
        except OSError:
            del self._entries[item["id"]]
            raise
        return True

    def remove(self, video_id: str) -> bool:
        if not self.has(video_id):
            return False
        item = self._entries.pop(video_id)
        try:
            self.save()
        except OSError:
            self._entries[video_id] = item
            raise
        return True

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temp.write_text(json.dumps({"version": 1, "items": self.all()},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self.path)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
