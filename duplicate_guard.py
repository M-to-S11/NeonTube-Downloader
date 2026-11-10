"""Offline duplicate detection for NeonTube Downloader.

Only completed, still-existing media files count as downloaded. A removed
history file must never prevent a new download. The UI decides whether to
explicitly allow a second copy; no files are removed or overwritten here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from collections.abc import Iterable, Mapping
import os

from youtube_api import video_id_from_url

ACTIVE_STATUSES = frozenset({
    "queued", "downloading", "processing", "retrying", "pausing", "paused",
})
VIDEO_EXTS = frozenset({".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"})
AUDIO_EXTS = frozenset({".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma"})


def content_key(url: str, *, playlist: bool = False) -> str:
    """Identify a video across youtube.com, youtu.be, shorts and music links.

    Playlists are a distinct target from their individual watch videos; a
    history entry for one playlist item is not proof a whole playlist finished.
    For non-YouTube downloads, compare the exact link without URL fragments.
    """
    url = str(url or "").strip()
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        is_youtube = host in {
            "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
            "youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com",
        }
        if is_youtube and parsed.scheme.lower() in ("http", "https"):
            playlist_id = parse_qs(parsed.query).get("list", [""])[0]
            is_playlist_link = parsed.path.rstrip("/") == "/playlist"
            if playlist_id and (playlist or is_playlist_link):
                return "youtube-playlist:" + playlist_id
        video_id = video_id_from_url(url)
        if video_id:
            return "youtube-video:" + video_id
        return url.split("#", 1)[0]
    except (ValueError, TypeError):
        return url


def media_key(mode: str, audio_format: str) -> str:
    """Separate MP4 videos from MP3/FLAC/etc audio conversions."""
    if str(mode) == "Nur Audio (MP3)":
        return "audio:" + str(audio_format or "MP3").lower()
    return "video"


def valid_file_path(path: object, *, mode: str, audio_format: str,
                    directory: str = "") -> Path | None:
    """Verify finished media is present (never mistake a .part for a download)."""
    if not isinstance(path, (str, os.PathLike)) or not path:
        return None
    try:
        candidate = Path(path)
        if not candidate.is_absolute() and directory:
            candidate = Path(directory) / candidate
        suffix = candidate.suffix.lower()
        valid_exts = VIDEO_EXTS if media_key(mode, audio_format) == "video" else AUDIO_EXTS
        if suffix not in valid_exts:
            return None
        if media_key(mode, audio_format).startswith("audio:"):
            preferred = "." + str(audio_format or "mp3").lower()
            if preferred in AUDIO_EXTS and suffix != preferred:
                return None
        return candidate if candidate.is_file() and candidate.stat().st_size > 0 else None
    except (OSError, ValueError):
        return None


def existing_media(record: object, *, video_id: str | None = None) -> Path | None:
    """Check stored output; recover from yt-dlp histories with a stale .part path.

    Older versions sometimes saved the pre-FFmpeg filename. Check the final
    [video-id].mp4 / .mp3 file in the original output directory in that case.
    """
    def get(name, default=""):
        return record.get(name, default) if isinstance(record, Mapping) else getattr(record, name, default)

    mode = str(get("mode") or "Video (MP4)")
    audio_format = str(get("audio_format") or "MP3")
    directory = str(get("output_dir") or "")
    path = valid_file_path(get("filename"), mode=mode,
                           audio_format=audio_format, directory=directory)
    if path is not None:
        return path
    if not video_id or not directory:
        return None
    # Only scan this folder, not the user's entire library. In the default
    # yt-dlp template the ID is enclosed in square brackets.
    try:
        root = Path(directory)
        if not root.is_dir():
            return None
        for pattern in ("*", "*/*"):
            for candidate in root.glob(pattern):
                if f"[{video_id}]" not in candidate.stem:
                    continue
                result = valid_file_path(candidate, mode=mode, audio_format=audio_format)
                if result:
                    return result
    except (OSError, ValueError):
        pass
    return None


@dataclass(frozen=True)
class DuplicateHit:
    url: str
    title: str
    filename: str


@dataclass
class DownloadPlan:
    # Ordered input with one classification per URL, preserving batch order.
    entries: list[tuple[str, str]]
    pending: list[str]
    downloaded: list[DuplicateHit]
    repeated: list[str]

    def accepted_urls(self, *, repeat_existing: bool = False) -> list[str]:
        return [url for url, status in self.entries
                if status == "new" or (repeat_existing and status == "downloaded")]


def build_download_plan(urls: Iterable[str], *, mode: str, audio_format: str,
                        playlist: bool, jobs: Iterable, history: Iterable) -> DownloadPlan:
    """Classify links without network requests and without modifying the queue.

    Status priority: already active in queue > existing file > new. Failed or
    cancelled jobs do not block new attempts. History without a real file does
    not block downloads. A playlist is never assumed complete from one file.
    """
    target_media = media_key(mode, audio_format)
    active_keys = set()
    finished_jobs = []
    for job in jobs:
        j_mode = getattr(job, "mode", "")
        if media_key(j_mode, getattr(job, "audio_format", "MP3")) != target_media:
            continue
        j_key = content_key(getattr(job, "url", ""), playlist=bool(getattr(job, "playlist", False)))
        if getattr(job, "status", "") in ACTIVE_STATUSES:
            active_keys.add(j_key)
        elif getattr(job, "status", "") == "finished":
            finished_jobs.append(job)

    # Scan only candidate matching records for file confirmation.
    records = list(history or ()) + finished_jobs
    entries = []
    pending = []
    downloaded = []
    repeated = []
    seen = set()
    for url in urls:
        key = content_key(url, playlist=playlist)
        if not url or key in seen:
            repeated.append(url)
            continue
        seen.add(key)
        if key in active_keys:
            entries.append((url, "pending"))
            pending.append(url)
            continue
        hit = None
        # No complete-playlist detection: the last file only proves a single
        # item was saved, not all videos in the playlist.
        if not key.startswith("youtube-playlist:"):
            video_id = key.split(":", 1)[1] if key.startswith("youtube-video:") else None
            for record in records:
                def get(prop, default=""):
                    return record.get(prop, default) if isinstance(record, Mapping) else getattr(record, prop, default)
                if media_key(get("mode"), get("audio_format", "MP3")) != target_media:
                    continue
                if content_key(get("url"), playlist=bool(get("playlist", False))) != key:
                    continue
                path = existing_media(record, video_id=video_id)
                if path is not None:
                    hit = DuplicateHit(url, str(get("title") or "Video"), str(path))
                    break
        if hit:
            entries.append((url, "downloaded"))
            downloaded.append(hit)
        else:
            entries.append((url, "new"))
    return DownloadPlan(entries, pending, downloaded, repeated)
