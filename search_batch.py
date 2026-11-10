"""Pure, offline selection of search results for NeonTube bulk queuing.

Only real 11-character YouTube video IDs from the *currently loaded* result
list are accepted. Never trust arbitrary URLs or stale checkbox IDs.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")


def selected_video_links(results: Iterable[Mapping], selected_ids: Iterable[str]) -> list[str]:
    """Return canonical unique links in displayed order, not click order."""
    selected = set(selected_ids)
    found: set[str] = set()
    links: list[str] = []
    for result in results:
        if not isinstance(result, Mapping):
            continue
        video_id = result.get("id")
        if (not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id)
                or video_id not in selected or video_id in found):
            continue
        found.add(video_id)
        links.append("https://www.youtube.com/watch?v=" + video_id)
    return links
