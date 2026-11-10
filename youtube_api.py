"""Official YouTube Data API v3 integration for metadata and search only.

This module does NOT download media. It uses the user's own API key and keeps
Google API failures separate from the yt-dlp download engine.
"""
from __future__ import annotations

import json
from html import unescape
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests

API_ROOT = "https://www.googleapis.com/youtube/v3"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTubeAPIError(RuntimeError):
    pass


def video_id_from_url(url: str) -> str | None:
    """Accept real YouTube links, but never arbitrary domains resembling YouTube."""
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        path = parsed.path.strip("/").split("/")
        candidate = ""
        if host == "youtu.be":
            candidate = path[0]
        elif host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
                      "youtube-nocookie.com", "www.youtube-nocookie.com"):
            if path[0] == "watch":
                candidate = parse_qs(parsed.query).get("v", [""])[0]
            elif path[0] in ("shorts", "live", "embed", "v") and len(path) >= 2:
                candidate = path[1]
        return candidate if parsed.scheme in ("http", "https") and VIDEO_ID_RE.fullmatch(candidate) else None
    except (ValueError, IndexError):
        return None


def readable_duration(iso: str) -> str:
    match = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not match:
        return "–"
    days, hours, minutes, seconds = (int(x or 0) for x in match.groups())
    hours += days * 24
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def seconds_duration(iso: str) -> int:
    match = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not match:
        return 0
    d, h, m, s = (int(x or 0) for x in match.groups())
    return d * 86400 + h * 3600 + m * 60 + s


def api_request(endpoint: str, api_key: str, **params) -> dict:
    """Request bounded data, without including credentials in error messages."""
    if not api_key.strip():
        raise YouTubeAPIError("Bitte zuerst einen YouTube-API-Schlüssel in den Einstellungen speichern.")
    try:
        # Requests uses HTTPS and certificate verification by default.
        response = requests.get(f"{API_ROOT}/{endpoint}",
                                params={"key": api_key.strip(), **params},
                                timeout=(5, 15), headers={"Accept": "application/json"})
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError):
            data = {}
        if response.status_code != 200:
            err = data.get("error", {}) if isinstance(data, dict) else {}
            details = err.get("errors", []) if isinstance(err, dict) else []
            reason = details[0].get("reason", "") if details else ""
            if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"):
                raise YouTubeAPIError("YouTube-API-Limit erreicht. Bitte später erneut versuchen.")
            if reason in ("keyInvalid", "badRequest") or response.status_code == 400:
                raise YouTubeAPIError("API-Schlüssel oder Anfrage ungültig. Bitte Schlüssel in den Einstellungen prüfen.")
            if response.status_code in (401, 403):
                raise YouTubeAPIError("YouTube-API-Zugriff verweigert. API aktivieren und Schlüsselbeschränkungen prüfen.")
            raise YouTubeAPIError(f"YouTube-API antwortet mit HTTP {response.status_code}.")
        if not isinstance(data, dict):
            raise YouTubeAPIError("Unerwartete Antwort von der YouTube-API.")
        return data
    except YouTubeAPIError:
        raise
    except requests.RequestException as exc:
        # requests exceptions may include URLs/query strings containing the key.
        raise YouTubeAPIError(f"Netzwerkfehler beim Zugriff auf die YouTube-API ({type(exc).__name__}).") from None


def _thumb(snippet: dict) -> str:
    images = snippet.get("thumbnails") or {}
    for quality in ("medium", "high", "default", "standard", "maxres"):
        value = (images.get(quality) or {}).get("url", "")
        if value:
            return value
    return ""


def search_videos(query: str, key: str, *, page_token: str = "", max_results: int = 12) -> dict:
    q = query.strip()
    if not q:
        return {"items": [], "next_page_token": ""}
    params = {"part": "snippet", "q": q, "type": "video",
              "maxResults": max(1, min(max_results, 25)), "safeSearch": "moderate", "regionCode": "DE"}
    if page_token:
        params["pageToken"] = page_token
    data = api_request("search", key, **params)
    items = []
    for result in data.get("items", []):
        vid = (result.get("id") or {}).get("videoId", "")
        if not VIDEO_ID_RE.fullmatch(vid):
            continue
        snippet = result.get("snippet") or {}
        items.append({"id": vid, "url": f"https://www.youtube.com/watch?v={vid}",
                      "title": unescape(snippet.get("title") or "YouTube-Video"),
                      "channel": unescape(snippet.get("channelTitle") or "YouTube"),
                      "thumbnail": _thumb(snippet), "duration": "–", "duration_seconds": 0})
    # One batched videos.list call gives exact durations for every result.
    if items:
        details = api_request("videos", key, part="contentDetails", id=",".join(i["id"] for i in items))
        durations = {item.get("id"): (item.get("contentDetails") or {}).get("duration", "")
                     for item in details.get("items", [])}
        for item in items:
            iso = durations.get(item["id"], "")
            item["duration"] = readable_duration(iso)
            item["duration_seconds"] = seconds_duration(iso)
    return {"items": items, "next_page_token": data.get("nextPageToken", "")}


def get_video_metadata(url: str, key: str) -> dict | None:
    vid = video_id_from_url(url)
    if not vid or not key:
        return None
    data = api_request("videos", key, part="snippet,contentDetails,statistics", id=vid)
    videos = data.get("items", [])
    if not videos:
        return None
    video = videos[0]
    snippet = video.get("snippet") or {}
    return {"title": unescape(snippet.get("title") or "YouTube-Video"),
            "uploader": unescape(snippet.get("channelTitle") or "YouTube"),
            "duration": seconds_duration((video.get("contentDetails") or {}).get("duration", "")),
            "thumbnail": _thumb(snippet),
            "view_count": (video.get("statistics") or {}).get("viewCount")}


# The key is intentionally NEVER written into the source code or EXE bundle.
# On Windows it is encrypted to the current Windows account using DPAPI.
def _windows_dpapi(data: bytes, *, decrypt: bool) -> bytes:
    from ctypes import POINTER, Structure, WinDLL, byref, cast, create_string_buffer, c_char, c_void_p, c_ulong, sizeof, string_at

    class BLOB(Structure):
        _fields_ = [("cbData", c_ulong), ("pbData", POINTER(c_char))]

    source = create_string_buffer(data, max(1, len(data)))
    original = BLOB(len(data), cast(source, POINTER(c_char)))
    output = BLOB()
    crypt = WinDLL("crypt32", use_last_error=True)
    crypt.CryptProtectData.argtypes = [POINTER(BLOB), c_void_p, POINTER(BLOB), c_void_p, c_void_p, c_ulong, POINTER(BLOB)]
    crypt.CryptProtectData.restype = c_ulong
    crypt.CryptUnprotectData.argtypes = [POINTER(BLOB), c_void_p, POINTER(BLOB), c_void_p, c_void_p, c_ulong, POINTER(BLOB)]
    crypt.CryptUnprotectData.restype = c_ulong
    func = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    ok = func(byref(original), None, None, None, None, 0x01, byref(output))
    if not ok:
        raise OSError("Windows-DPAPI konnte den API-Schlüssel nicht verarbeiten.")
    try:
        return string_at(output.pbData, output.cbData)
    finally:
        kernel = WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [c_void_p]
        kernel.LocalFree(cast(output.pbData, c_void_p))


def read_api_key(data_dir: Path) -> str:
    # Environment injection is helpful for company-managed deployment.
    env = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if env:
        return env
    target = Path(data_dir) / "youtube_api_key.dat"
    try:
        raw = target.read_bytes()
        if sys.platform == "win32":
            raw = _windows_dpapi(raw, decrypt=True)
        return raw.decode("utf-8").strip()
    except (OSError, ValueError, UnicodeError):
        return ""


def write_api_key(data_dir: Path, key: str) -> None:
    target = Path(data_dir) / "youtube_api_key.dat"
    if not key.strip():
        target.unlink(missing_ok=True)
        return
    raw = key.strip().encode("utf-8")
    if sys.platform == "win32":
        raw = _windows_dpapi(raw, decrypt=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    if sys.platform != "win32":
        target.chmod(0o600)
