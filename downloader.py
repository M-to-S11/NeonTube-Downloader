"""Download engine for NeonTube Downloader.

All callbacks are sent to a Queue; no Tk widget is accessed from a worker thread.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Callable, Any
import os
import queue
import shutil
import re
import sys
import time
import uuid

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None


# A bounded number of complete retries, in addition to yt-dlp's built-in
# connection/fragment retries.  Never retry indefinitely or bypass access errors.
MAX_RECOVERY_ATTEMPTS = 3
RECOVERY_BACKOFF_SECONDS = (2, 5)

# Existing users remain on their original flat download layout until they opt in.
FOLDER_ORGANIZATIONS = (
    "Keine (wie bisher)", "Nach Kanal", "Nach Playlist", "Nach Dateiformat"
)


def normalize_folder_organization(value: str) -> str:
    """Normalize a persisted setting; old or malformed configs stay compatible."""
    return value if value in FOLDER_ORGANIZATIONS else FOLDER_ORGANIZATIONS[0]


def output_template(job: "DownloadJob") -> str:
    """Return a yt-dlp output template for a job's immutable folder layout.

    yt-dlp expands metadata and sanitizes individual path components under
    Windows. No post-download move: fragment resumption and ffmpeg are unaffected.
    """
    basename = "%(title).160B [%(id)s].%(ext)s"
    layout = normalize_folder_organization(job.folder_organization)
    if layout == "Nach Kanal":
        # Some extractors expose uploader but not channel; never make a NA dir.
        folder = "%(channel,uploader|Unbekannter Kanal).110S"
    elif layout == "Nach Playlist":
        # Single videos have no playlist; keep them in a predictable folder.
        folder = "%(playlist_title,playlist|Einzelvideos).110S" if job.playlist else "Einzelvideos"
    elif layout == "Nach Dateiformat":
        folder = (str(job.audio_format or "MP3").upper() if job.mode == "Nur Audio (MP3)" else "MP4")
        # Guard against corrupt or user-edited configuration (no traversal).
        if not re.fullmatch(r"[A-Za-z0-9]{1,10}", folder):
            folder = "Audio" if job.mode == "Nur Audio (MP3)" else "MP4"
    else:
        return os.path.join(job.output_dir, basename)
    return os.path.join(job.output_dir, folder, basename)


class DownloadPaused(Exception):
    pass


class DownloadCancelled(Exception):
    pass


@dataclass
class DownloadJob:
    url: str
    output_dir: str
    mode: str = "Video (MP4)"
    quality: str = "1080p"
    audio_format: str = "MP3"
    playlist: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = "Metadaten werden geladen …"
    channel: str = "YouTube"
    duration: int = 0
    thumbnail_url: str = ""
    thumbnail_path: str = ""
    status: str = "queued"
    progress: float = 0
    speed: float = 0
    eta: int | None = None
    downloaded: int = 0
    total: int = 0
    filename: str = ""
    error: str = ""
    pause_requested: bool = False
    cancel_requested: bool = False
    last_hook: float = 0.0
    # These fields are only session state; existing history/settings files stay
    # backward compatible and all current GUI cards keep their layout.
    retry_attempt: int = 0
    retry_wait: int = 0
    folder_organization: str = "Keine (wie bisher)"


class QuietLogger:
    def __init__(self, on_error: Callable[[str], None]):
        self.on_error = on_error

    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.on_error(str(msg))


def ffmpeg_path() -> str | None:
    """Prefer a complete, bundled FFmpeg/FFprobe pair for portable builds.

    The old source-start behavior is preserved: imageio-ffmpeg is still
    available if a bundled Windows runtime is not present.
    """
    roots = (Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)),
             Path(__file__).resolve().parent)
    for base in roots:
        for folder in (base / "ffmpeg", base / ".runtime" / "ffmpeg"):
            binary = folder / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
            if binary.is_file():
                return str(binary)
    if imageio_ffmpeg is not None:
        try:
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
    return None  # yt-dlp may also search FFmpeg in PATH.


def javascript_runtime_config() -> dict:
    """Use a locally installed/bundled Deno binary when possible.

    Current yt-dlp/YouTube uses yt-dlp-ejs plus a JavaScript runtime.
    """
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = [
        root / "deno" / "deno.exe",          # PyInstaller bundle
        root / ".runtime" / "deno.exe",      # First-run local installer
        Path(sys.executable).resolve().parent / "deno.exe",
        Path.home() / ".deno" / "bin" / "deno.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return {"js_runtimes": {"deno": {"path": str(candidate)}}}
    if shutil.which("deno"):
        return {"js_runtimes": {"deno": {"path": shutil.which("deno")}}}
    if shutil.which("node"):
        return {"js_runtimes": {"node": {"path": shutil.which("node")}}}
    return {}  # yt-dlp defaults to searching for Deno.


def quality_height(quality: str) -> int | None:
    match = re.search(r"(\d+)", quality)
    if quality.lower().startswith("beste"):
        return None
    if "4k" in quality.lower():
        return 2160
    return int(match.group(1)) if match else 1080


def is_transient_network_error(error: str) -> bool:
    """Classify retryable connection faults, never authorization/local errors.

    Intentionally conservative: a generic `DownloadError` is not enough to
    justify repeating a download. A 403/429 or bad certificate cannot be
    repaired by automatically retrying the same request.
    """
    lowered = str(error or "").lower()
    terminal = (
        "http error 400", "http error 401", "http error 403",
        "http error 404", "http error 410", "http error 429",
        "private video", "video unavailable", "copyright",
        "sign in to confirm", "sign in", "members-only", "drm",
        "not available in your country", "unsupported url",
        "requested format is not available", "permission denied",
        "access is denied", "no space left on device", "disk full",
        "ffmpeg not found", "certificate verify failed",
        "certificate_verify_failed",
        "certification verification failed", "invalid api key",
    )
    if any(pattern in lowered for pattern in terminal):
        return False
    transient = (
        "timed out", "timeout", "connection reset", "connection aborted",
        "connection broken", "connection refused", "remote end closed",
        "remote disconnected", "remotedisconnected", "unexpected eof",
        "incomplete read", "incompleteread",
        "decryption_failed_or_bad_record_mac",
        "ssl: bad record mac", "ssl: decryption failed", "ssleoferror",
        "temporary failure", "http error 408", "http error 500",
        "http error 502", "http error 503", "http error 504",
        "http error 520", "http error 522", "http error 524",
        "network is unreachable", "read timed out", "connecttimeout",
        "readtimeout", "broken pipe", "connection closed",
        "connection lost", "connection interrupted", "connection timed out",
        "connectionerror", "connection reset by peer", "server disconnected",
        "name resolution failed", "temporary failure in name resolution",
    )
    return any(pattern in lowered for pattern in transient)


def recovery_delay(attempt: int) -> int:
    """Seconds to wait before the next (1-based) full attempt."""
    return RECOVERY_BACKOFF_SECONDS[min(max(0, attempt - 2),
                                        len(RECOVERY_BACKOFF_SECONDS) - 1)]


def ydl_options(job: DownloadJob, cookiefile: str = "") -> dict:
    opts: dict[str, Any] = {
        "outtmpl": output_template(job),
        "noplaylist": not job.playlist,
        "quiet": True,
        "no_warnings": True,
        "continuedl": True,
        "nopart": False,
        "overwrites": False,
        "ignoreerrors": False,
        "windowsfilenames": True,
        "retries": 12,
        "fragment_retries": 12,
        "extractor_retries": 5,
        "file_access_retries": 5,
        # Fewer parallel connections reduce instability on some home networks.
        "concurrent_fragment_downloads": 2,
        "socket_timeout": 40,
        "logger": QuietLogger(lambda msg: setattr(job, "error", msg)),
    }
    opts.update(javascript_runtime_config())
    if cookiefile and Path(cookiefile).is_file():
        opts["cookiefile"] = cookiefile
    ffmpeg = ffmpeg_path()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    if job.mode == "Nur Audio (MP3)":
        opts["format"] = "bestaudio/best"
        codec = job.audio_format.lower()
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": codec,
             "preferredquality": "192" if codec == "mp3" else "0"}
        ]
    else:
        height = quality_height(job.quality)
        limit = f"[height<={height}]" if height else ""
        # Prefer MP4/M4A combinations, then gracefully fall back if not available.
        opts["format"] = (
            f"bv*{limit}[ext=mp4]+ba[ext=m4a]/"
            f"bv*{limit}+ba/"
            f"b{limit}/best"
        )
        opts["merge_output_format"] = "mp4"
    return opts


class DownloadManager:
    def __init__(self, events: queue.Queue, concurrency: int = 2,
                 cookiefile: str = ""):
        self.events = events
        self.max_concurrency = max(1, min(int(concurrency), 4))
        self.cookiefile = cookiefile
        self.jobs: OrderedDict[str, DownloadJob] = OrderedDict()
        self.pending: deque[str] = deque()
        self.active: set[str] = set()
        self.lock = Lock()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="neontube")
        self.closed = False

    def emit(self, kind: str, job_id: str = "", payload: Any = None):
        self.events.put((kind, job_id, payload))

    def add(self, job: DownloadJob):
        with self.lock:
            self.jobs[job.id] = job
            self.pending.append(job.id)
        self.emit("queue_changed")
        self._schedule()

    def _schedule(self):
        with self.lock:
            if self.closed:
                return
            while len(self.active) < self.max_concurrency and self.pending:
                job_id = self.pending.popleft()
                job = self.jobs.get(job_id)
                if not job or job.cancel_requested or job.pause_requested:
                    continue
                job.status = "downloading"
                self.active.add(job_id)
                self.pool.submit(self._worker, job)
                self.emit("queue_changed")

    def pause(self, job_id: str):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job.status in ("finished", "failed", "cancelled"):
                return
            job.pause_requested = True
            if job_id not in self.active:
                job.status = "paused"
                self.pending = deque(x for x in self.pending if x != job_id)
            else:
                job.status = "pausing"
        self.emit("queue_changed")

    def resume(self, job_id: str):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job.cancel_requested:
                return
            if job.status not in ("paused", "pausing", "failed"):
                return
            job.pause_requested = False
            job.error = ""
            if job_id not in self.active:
                job.status = "queued"
                self.pending.appendleft(job_id)
            else:
                job.status = "downloading"
        self.emit("queue_changed")
        self._schedule()

    def cancel(self, job_id: str):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            job.cancel_requested = True
            job.pause_requested = False
            job.status = "cancelled"
            self.pending = deque(x for x in self.pending if x != job_id)
        self.emit("queue_changed")

    def remove(self, job_id: str):
        self.cancel(job_id)
        with self.lock:
            self.jobs.pop(job_id, None)
        self.emit("queue_changed")

    def clear_done(self):
        with self.lock:
            ids = [k for k, j in self.jobs.items() if j.status in ("finished", "failed", "cancelled")]
            for k in ids:
                self.jobs.pop(k, None)
        self.emit("queue_changed")

    def clear_all(self):
        with self.lock:
            for job in self.jobs.values():
                job.cancel_requested = True
            self.pending.clear()
            self.jobs.clear()
        self.emit("queue_changed")

    def move(self, job_id: str, offset: int):
        with self.lock:
            keys = list(self.jobs.keys())
            if job_id not in keys:
                return
            i = keys.index(job_id)
            j = max(0, min(len(keys)-1, i+offset))
            if i == j:
                return
            keys.insert(j, keys.pop(i))
            self.jobs = OrderedDict((key, self.jobs[key]) for key in keys)
            queued = [k for k in keys if k in self.pending]
            self.pending = deque(queued)
        self.emit("queue_changed")

    def _progress_hook(self, job: DownloadJob, data: dict):
        if job.cancel_requested or self.closed:
            raise DownloadCancelled("Download abgebrochen")
        if job.pause_requested:
            raise DownloadPaused("Download pausiert")
        kind = data.get("status")
        if kind == "downloading":
            job.status = "downloading"
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            job.downloaded = int(done)
            job.total = int(total)
            job.speed = float(data.get("speed") or 0)
            job.eta = data.get("eta")
            job.progress = min(1.0, done / total) if total else 0.0
            job.filename = data.get("filename") or job.filename
            now = time.monotonic()
            if now - job.last_hook > 0.16:
                job.last_hook = now
                self.emit("progress", job.id)
        elif kind == "finished":
            job.status = "processing"
            job.progress = 1.0
            job.filename = data.get("filename") or job.filename
            self.emit("queue_changed")

    def _check_interrupted(self, job: DownloadJob):
        """Cooperative interrupts even while waiting for a network retry."""
        if job.cancel_requested or self.closed:
            raise DownloadCancelled("Abgebrochen")
        if job.pause_requested:
            raise DownloadPaused("Pausiert")

    def _wait_for_recovery(self, job: DownloadJob, seconds: int):
        """Short sleep steps keep Pause/Cancel responsive during backoff."""
        for tick in range(max(0, int(seconds)) * 10):
            self._check_interrupted(job)
            remaining = seconds - tick // 10
            if job.retry_wait != remaining:
                job.retry_wait = remaining
                self.emit("progress", job.id)
            time.sleep(0.1)
        self._check_interrupted(job)
        job.retry_wait = 0
        self.emit("progress", job.id)

    def _worker(self, job: DownloadJob):
        try:
            if yt_dlp is None:
                raise RuntimeError("yt-dlp ist nicht installiert. Bitte start_windows.bat ausführen.")
            Path(job.output_dir).mkdir(parents=True, exist_ok=True)
            base_options = ydl_options(job, self.cookiefile)
            base_options["progress_hooks"] = [lambda data: self._progress_hook(job, data)]
            base_options["postprocessor_hooks"] = [lambda data: self._post_hook(job, data)]

            # yt-dlp retries individual HTTP requests and fragments first.
            # A full retry happens only for an exhausted *transient* fault.
            # .part files are retained and continuedl stays enabled; no files
            # are deleted or needlessly restarted by our repair logic.
            result = None
            for attempt_index in range(MAX_RECOVERY_ATTEMPTS):
                self._check_interrupted(job)
                attempt = attempt_index + 1
                job.retry_attempt = attempt
                job.retry_wait = 0
                job.error = ""
                job.status = "downloading"
                self.emit("queue_changed")
                options = base_options.copy()
                if attempt > 1:
                    # Fewer parallel fragment requests are more robust on
                    # unstable connections and certain home networks.
                    options["concurrent_fragment_downloads"] = 1
                try:
                    with yt_dlp.YoutubeDL(options) as ydl:
                        result = ydl.extract_info(job.url, download=True)
                    break
                except Exception as exc:
                    self._check_interrupted(job)
                    raw_error = str(exc).strip() or job.error or "Unbekannter Fehler"
                    # yt-dlp may put the detailed HTTP/SSL reason in its
                    # logger and raise only a short wrapper exception.
                    combined_error = raw_error + " " + job.error
                    retryable = is_transient_network_error(combined_error)
                    if (attempt >= MAX_RECOVERY_ATTEMPTS or not retryable
                            or job.status == "processing"):
                        job.error = raw_error
                        raise
                    wait_seconds = recovery_delay(attempt + 1)
                    job.status = "retrying"
                    job.retry_attempt = attempt + 1
                    job.retry_wait = wait_seconds
                    job.speed = 0
                    job.eta = None
                    self.emit("download_retry", job.id,
                              f"Verbindungsproblem erkannt (Versuch {attempt}/"
                              f"{MAX_RECOVERY_ATTEMPTS}). Automatische Reparatur in "
                              f"{wait_seconds} s; vorhandene Teildateien bleiben erhalten.")
                    self.emit("queue_changed")
                    self._wait_for_recovery(job, wait_seconds)
            self._check_interrupted(job)
            if result:
                data = result
                if result.get("_type") in ("playlist", "multi_video"):
                    entries = [x for x in (result.get("entries") or []) if x]
                    if entries:
                        data = entries[-1]
                job.title = data.get("title") or job.title
                job.channel = data.get("uploader") or job.channel
                job.duration = int(data.get("duration") or job.duration)
                paths = data.get("requested_downloads") or []
                # A postprocessor may have already reported the final MP3/MP4.
                # Do not replace an existing converted file with an old .m4a
                # or .webm source path from requested_downloads.
                if not (job.filename and Path(job.filename).is_file()):
                    if paths:
                        job.filename = paths[0].get("filepath") or job.filename
                    if data.get("filepath"):
                        job.filename = data["filepath"]
                    # Some yt-dlp versions only report the pre-conversion file.
                    # Check for the expected output extension in its directory.
                    if job.mode == "Nur Audio (MP3)" and job.filename:
                        expected = Path(job.filename).with_suffix(
                            "." + job.audio_format.lower())
                        if expected.is_file():
                            job.filename = str(expected)
            self._check_interrupted(job)
            job.retry_wait = 0
            job.error = ""
            job.status = "finished"
            job.progress = 1.0
            self.emit("completed", job.id)
        except DownloadPaused:
            job.retry_wait = 0
            job.status = "paused" if not job.cancel_requested else "cancelled"
            self.emit("queue_changed")
        except DownloadCancelled:
            job.retry_wait = 0
            job.status = "cancelled"
            self.emit("queue_changed")
        except Exception as exc:
            job.retry_wait = 0
            if job.cancel_requested or self.closed:
                job.status = "cancelled"
            elif job.pause_requested:
                job.status = "paused"
            else:
                job.status = "failed"
                job.error = str(exc) or job.error or "Unbekannter Fehler"
            self.emit("queue_changed")
        finally:
            with self.lock:
                self.active.discard(job.id)
            self.emit("queue_changed")
            self._schedule()

    def _post_hook(self, job: DownloadJob, data: dict):
        if job.cancel_requested:
            raise DownloadCancelled("Abgebrochen")
        info = data.get("info_dict") or {}
        if data.get("status") == "finished" and info.get("filepath"):
            job.filename = info["filepath"]
        if data.get("status") == "started":
            job.status = "processing"
            self.emit("queue_changed")

    def set_concurrency(self, number: int):
        with self.lock:
            self.max_concurrency = max(1, min(int(number), 4))
        self._schedule()

    def close(self):
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                if job.status not in ("finished", "failed"):
                    job.cancel_requested = True
            self.pending.clear()
        self.pool.shutdown(wait=False, cancel_futures=True)
