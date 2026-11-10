"""Passive YouTube clipboard detection for NeonTube Downloader.

Only authentic YouTube video and playlist URLs are considered. Clipboard text is
never persisted, sent to the API, or automatically queued for downloading.
"""
from __future__ import annotations

from hashlib import sha256
import re
from urllib.parse import parse_qs, urlsplit

from youtube_api import video_id_from_url

_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com",
          "music.youtube.com", "www.youtube-nocookie.com",
          "youtube-nocookie.com", "youtu.be", "www.youtu.be"}
_LIST_ID = re.compile(r"[a-zA-Z0-9_-]{2,200}\Z")


def extract_youtube_links(text: str, limit: int = 25) -> list[str]:
    """Extract distinct, supported YouTube videos/playlists, preserving order.

    Never infer YouTube membership by substring: 'youtube.com.evil.tld' or
    'youtube.com@evil.tld' must never trigger a clipboard offer.
    """
    if not isinstance(text, str) or len(text) > 8192 or limit < 1:
        return []
    selected = []
    seen = set()
    for m in _URL.finditer(text):
        link = m.group(0).rstrip('.,;:!?)]}')
        if len(link) > 2048:
            continue
        try:
            p = urlsplit(link)
            host = (p.hostname or '').lower().rstrip('.')
            if p.scheme not in ('http', 'https') or host not in _HOSTS:
                continue
            # Reject credentials and non-web ports in a purported YT link.
            if p.username is not None or p.password is not None or p.port not in (None, 80, 443):
                continue
            valid_video = bool(video_id_from_url(link))
            path = p.path.strip('/').lower()
            playlist = (host not in ('youtu.be', 'www.youtu.be')
                        and (path == 'playlist' or path == 'watch')
                        and any(_LIST_ID.fullmatch(x or '')
                                for x in parse_qs(p.query).get('list', [])))
            if not valid_video and not playlist:
                continue
        except (ValueError, TypeError):
            continue
        if link not in seen:
            seen.add(link)
            selected.append(link)
            if len(selected) >= limit:
                break
    return selected


def append_unique_links(existing: str, urls: list[str]) -> str:
    """Preserve the user's typed input; append only previously absent links."""
    existing = str(existing or '').strip()
    # Earlier text need not be a YouTube URL. Keep it intact, if present.
    known = {x.rstrip('.,;:!?)]}') for x in _URL.findall(existing)}
    new = []
    for link in urls:
        if link not in known:
            known.add(link)
            new.append(link)
    return (existing + ('  ' if existing and new else '') + '  '.join(new)).strip()


class ClipboardLinkWatcher:
    """Debounce clipboard changes; defer offers while the app is unfocused.

    SHA-256 signatures ensure arbitrary clipboard contents are not retained in
    memory by the watcher. Only recognized YouTube URLs are held temporarily.
    """
    def __init__(self, initial_text: str = ''):
        self.last_signature = self._signature(initial_text)
        self.pending: list[str] = []

    @staticmethod
    def _signature(text: str) -> bytes:
        return sha256(str(text or '').encode('utf-8')).digest()

    def dismiss(self, current_text: str) -> None:
        self.last_signature = self._signature(current_text)
        self.pending = []

    def observe(self, text: str, *, foreground: bool) -> list[str]:
        signature = self._signature(text)
        if signature != self.last_signature:
            self.last_signature = signature
            self.pending = extract_youtube_links(text)
        if foreground and self.pending:
            found = self.pending
            self.pending = []
            return found
        return []
