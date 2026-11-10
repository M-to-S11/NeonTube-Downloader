"""NeonTube Downloader — customtkinter desktop app.

Design based on the screenshot supplied by the user. Downloading is powered by
public yt-dlp interfaces. Supports queueing, multiple concurrent downloads,
playlist mode, metadata thumbnails, pause/resume and persistent history.
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tkinter import filedialog, messagebox
from urllib.parse import urlparse

try:
    import customtkinter as ctk
    from PIL import Image, ImageDraw, ImageTk, ImageFilter, ImageChops
    import requests
except ImportError as exc:
    raise SystemExit(
        f"Fehlendes Python-Paket: {exc}. Bitte 'start_windows.bat' starten."
    ) from exc

from downloader import (DownloadJob, DownloadManager, yt_dlp, ffmpeg_path,
                        javascript_runtime_config, MAX_RECOVERY_ATTEMPTS,
                        FOLDER_ORGANIZATIONS, normalize_folder_organization)
from favorites import FavoriteStore
from neontube_i18n import LanguageManager
from search_batch import selected_video_links
from clipboard_links import ClipboardLinkWatcher, append_unique_links
from youtube_api import (YouTubeAPIError, get_video_metadata, search_videos,
                         read_api_key, write_api_key, video_id_from_url)

APP_NAME = "NeonTube Downloader"
VERSION = "1.38.0"
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ASSETS = ROOT / "assets"
DATA = (Path(os.getenv("APPDATA", Path.home())) / "NeonTubeDownloader")
DATA.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA / "settings.json"
HISTORY_FILE = DATA / "history.json"
FAVORITES_FILE = DATA / "favorites.json"
THUMBS = DATA / "thumbnails"
THUMBS.mkdir(parents=True, exist_ok=True)

BG = "#070826"
PANEL = "#0d123b"
PANEL_DARK = "#090d2e"
PANEL_ALT = "#151c50"
BORDER = "#444ea0"
TEXT = "#f6f6ff"
MUTED = "#a7b8f1"
PURPLE = "#8b1cf4"
VIOLET = "#642dff"
PINK = "#ef1ccf"
GREEN = "#26eac4"
FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"

# Keep three compact queue cards fully inside the visible list area, above
# the footer controls. The whole right column remains the same height.
QUEUE_PANEL_HEIGHT = 342
QUEUE_LIST_TOP = 42
QUEUE_LIST_HEIGHT = 259
QUEUE_FOOTER_TOP = 305
QUEUE_FOOTER_HEIGHT = 29
QUEUE_CARD_HEIGHT = 76
QUEUE_ROW_GAP = 5
HISTORY_PANEL_HEIGHT = 230
HISTORY_LIST_HEIGHT = 174
# Four history preview entries now fit without hiding the fourth row.
# 4 * (39px card + 2px vertical padding) = 164px inside the 174px canvas.
HISTORY_ROW_HEIGHT = 39
HISTORY_ROW_PADY = 1


def img(name: str, size: tuple[int, int]):
    return ctk.CTkImage(light_image=Image.open(ASSETS / name).convert("RGBA"),
                        dark_image=Image.open(ASSETS / name).convert("RGBA"), size=size)


def load_json(filename: Path, default):
    try:
        return json.loads(filename.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def save_json(filename: Path, data):
    tmp = filename.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(filename)


def add_neon_halos(image: Image.Image, halos) -> Image.Image:
    """Blend blurred ambient light *into* an existing artwork bitmap.

    Each halo is (center_x, center_y, radius_x, radius_y, rgb, alpha, blur),
    where positions and radii are fractions of the artwork dimensions and
    blur is a fraction of its shorter edge. No overlay Tk widgets are added.
    """
    canvas = image.convert("RGBA")
    width, height = canvas.size
    if width < 2 or height < 2:
        return canvas
    for cx, cy, rx, ry, color, alpha, blur in halos:
        if not alpha or rx <= 0 or ry <= 0:
            continue
        mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(mask).ellipse(
            (round((cx - rx) * width), round((cy - ry) * height),
             round((cx + rx) * width), round((cy + ry) * height)),
            fill=max(0, min(255, int(alpha))))
        mask = mask.filter(ImageFilter.GaussianBlur(max(1, round(min(width, height) * blur))))
        glow = Image.new("RGBA", (width, height), tuple(color) + (0,))
        glow.putalpha(mask)
        canvas = Image.alpha_composite(canvas, glow)
    return canvas


def smooth_left_fade(width: int, height: int, fade_fraction: float = .33) -> Image.Image:
    """A smooth alpha fade for hero art; prevents a visible vertical seam.

    Uses smoothstep instead of a linear edge, so the artwork enters and
    leaves the transition without a sudden change in brightness. All work
    happens in the existing banner bitmap, never above Tk controls.
    """
    width = max(1, int(width))
    height = max(1, int(height))
    fade_width = max(1, round(width * max(.01, min(.95, fade_fraction))))
    row = []
    for x in range(width):
        t = min(1.0, x / fade_width)
        level = t * t * (3.0 - 2.0 * t)
        row.append(round(level * 255))
    mask = Image.new("L", (width, 1))
    mask.putdata(row)
    return mask.resize((width, height))


def bytes_text(number: float | int) -> str:
    if not number:
        return "0 MB"
    for suffix in ("B", "KB", "MB", "GB", "TB"):
        if abs(number) < 1024 or suffix == "TB":
            return f"{number:.1f} {suffix}" if suffix != "B" else f"{int(number)} B"
        number /= 1024
    return "0 MB"


def ellipsize_to_width(text: str, max_pixels: int, measure) -> str:
    """Shorten a title to the REAL widget width, keeping its beginning.

    `measure` is the current Tk font's measure(text) function. Keeping this
    pure makes resizing and Windows DPI behaviour easy to unit-test.
    """
    text = str(text or "")
    if not text or max_pixels <= 0:
        return ""
    if measure(text) <= max_pixels:
        return text
    ellipsis = "…"
    if measure(ellipsis) > max_pixels:
        return ""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = text[:mid].rstrip() + ellipsis
        if measure(candidate) <= max_pixels:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + ellipsis


def compact_job_metadata(job) -> str:
    """Compact, trustworthy format/quality/size line for a queue card."""
    video = getattr(job, "mode", "") == "Video (MP4)"
    codec = "MP4" if video else str(getattr(job, "audio_format", "MP3") or "MP3").upper()
    quality = str(getattr(job, "quality", "") or "") if video else "Audio"
    pieces = [codec]
    if quality:
        pieces.append(quality)
    size = getattr(job, "total", 0) or getattr(job, "downloaded", 0) or 0
    if size > 0:
        pieces.append(bytes_text(size))
    return " · ".join(pieces)


def compact_history_metadata(entry: dict) -> str:
    """Summarize historical results without relying on optional older fields."""
    video = entry.get("mode") == "Video (MP4)"
    codec = "MP4" if video else str(entry.get("audio_format") or "MP3").upper()
    pieces = [codec]
    quality = str(entry.get("quality") or "") if video else ""
    if quality:
        pieces.append(quality)
    try:
        size = float(entry.get("size") or 0)
        if size > 0:
            pieces.append(bytes_text(size))
    except (ValueError, TypeError):
        pass
    stamp = str(entry.get("date") or "")
    if stamp:
        try:
            parsed = datetime.fromisoformat(stamp)
            pieces.append(parsed.strftime("%d.%m. %H:%M"))
        except ValueError:
            pieces.append(stamp[:16])
    return " · ".join(pieces)



def format_view_count(value) -> str:
    """Show YouTube Data API string counts and yt-dlp numeric counts safely.

    The YouTube Data API returns statistics.viewCount as a decimal *string*.
    yt-dlp generally returns an integer; either source may omit the field.
    """
    if isinstance(value, bool) or value is None:
        return "Videovorschau"
    if isinstance(value, str):
        raw = value.strip()
        # Accept plain decimal strings and correctly grouped thousands.
        if re.fullmatch(r"[0-9]+", raw):
            pass
        elif re.fullmatch(r"[0-9]{1,3}(?:[.,][0-9]{3})+", raw):
            raw = raw.replace(".", "").replace(",", "")
        else:
            return "Videovorschau"
        # Counts beyond this length are not realistic and should not be
        # converted/displayed as an unbounded integer.
        if len(raw) > 20:
            return "Videovorschau"
        value = raw
    try:
        count = int(value)
    except (ValueError, TypeError, OverflowError):
        return "Videovorschau"
    if count < 0:
        return "Videovorschau"
    return f"{count:,}".replace(",", ".") + " Aufrufe"


def clock_text(seconds: int | float | None) -> str:
    if seconds is None or seconds < 0:
        return "--:--:--"
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{(seconds // 60) % 60:02d}:{seconds % 60:02d}"


def open_path(path: str):
    if not path:
        return
    p = Path(path)
    if not p.exists():
        return
    if sys.platform == "win32":
        os.startfile(str(p))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])


def desktop_downloads():
    folder = Path.home() / "Downloads"
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


def make_label(parent, text: str, size=13, color=TEXT, bold=False, **kwargs):
    return ctk.CTkLabel(parent, text=text, text_color=color,
                        font=ctk.CTkFont(family=FONT, size=size,
                                         weight="bold" if bold else "normal"),
                        **kwargs)


def regular_button(parent, text, command, fg=PANEL_ALT, hover="#202e66",
                   width=80, height=38, font_size=13, icon_kind=None, **kwargs):
    button = ctk.CTkButton(parent, text=text, command=command,
                           fg_color=fg, hover_color=hover,
                           border_color=BORDER, border_width=1,
                           corner_radius=12, text_color=TEXT,
                           width=width, height=height,
                           font=ctk.CTkFont(family=FONT, size=font_size),
                           **kwargs)
    if icon_kind:
        set_button_icon(button, icon_kind)
    return button


def set_button_icon(button, kind: str, size: int = 16, color: str = "#dcdfff"):
    """Use painted icons rather than platform-dependent pause/cancel glyphs.

    Refreshing progress can happen several times per second; don't recreate
    images while an unchanged pause or resume icon is already displayed.
    """
    key = (kind, size, color)
    if getattr(button, "_neon_icon_kind", None) == key:
        return
    art = outline_icon(kind, size, color)
    photo = ctk.CTkImage(light_image=art, dark_image=art, size=(size, size))
    button.configure(image=photo, compound="left")
    button._neon_icon_kind = key
    button._neon_icon_reference = photo


def outline_icon(kind: str, size: int = 24, color: str = "#d7d6ff") -> Image.Image:
    """Small antialiased line icons; no system emoji/font fallback is required.

    PIL drawings are independent from CustomTkinter internals. They avoid
    missing-character boxes on Windows when Segoe UI lacks a glyph.
    """
    scale = 4
    canvas = Image.new("RGBA", (32 * scale, 32 * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    c = color
    px = lambda v: round(v * scale)
    xy = lambda *v: tuple(px(a) for a in v)
    def line(points, width=2.25):
        d.line([xy(*pt) for pt in points], fill=c, width=px(width), joint="curve")
    def arc(bounds, begin, end, width=2.25):
        d.arc(xy(*bounds), begin, end, fill=c, width=px(width))
    def ellipse(bounds, width=2.25):
        d.ellipse(xy(*bounds), outline=c, width=px(width))
    def round_rect(bounds, r=3, width=2):
        d.rounded_rectangle(xy(*bounds), radius=px(r), outline=c, width=px(width))

    if kind in ("download", "queue"):
        line([(16, 4), (16, 22)], 2.7)
        line([(9, 16), (16, 23), (23, 16)], 2.7)
        line([(6, 24), (6, 28), (26, 28), (26, 24)], 2.4)
    elif kind == "search":
        ellipse((5, 5, 22, 22), 2.4)
        line([(21, 21), (28, 28)], 3.0)
    elif kind in ("favorite", "favorite-filled"):
        # Draw the heart ourselves to avoid missing emoji glyphs on Windows.
        import math
        points = []
        for i in range(121):
            t = math.pi * 2 * i / 120
            x = 16 + 0.67 * (16 * math.sin(t) ** 3)
            y = 15 - 0.67 * (13 * math.cos(t) - 5 * math.cos(2 * t)
                             - 2 * math.cos(3 * t) - math.cos(4 * t))
            points.append(xy(x, y))
        if kind == "favorite-filled":
            d.polygon(points, fill=c)
        else:
            d.line(points, fill=c, width=px(2.5), joint="curve")
    elif kind in ("history", "clock"):
        arc((4, 4, 28, 28), -85, 250, 2.6)
        line([(6, 4), (5, 11), (12, 10)], 2.4)
        line([(16, 10), (16, 17), (22, 20)], 2.5)
    elif kind == "settings":
        # Solid eight-tooth cog: at small DPI-scaled sizes the old icon
        # resembled a sun rather than the reference screenshot's gear.
        import math
        teeth = []
        for i in range(8):
            mid = (i * 45 - 90) * math.pi / 180
            for offset, radius in ((-22.5, 10.7), (-16.0, 14.0),
                                   (16.0, 14.0), (22.5, 10.7)):
                angle = mid + offset * math.pi / 180
                teeth.append(xy(16 + math.cos(angle) * radius,
                                16 + math.sin(angle) * radius))
        d.polygon(teeth, fill=c)
        d.ellipse(xy(12.0, 12.0, 20.0, 20.0), fill=(0, 0, 0, 0))
    elif kind in ("profiles", "person"):
        ellipse((11, 4, 21, 14), 2.2)
        arc((5, 13, 27, 31), 185, 355, 2.6)
    elif kind == "info":
        ellipse((4, 4, 28, 28), 2.3)
        d.ellipse(xy(14.4, 9, 17.6, 12.2), fill=c)
        line([(16, 15), (16, 23)], 2.7)
    elif kind == "video":
        round_rect((4, 7, 28, 25), 4, 2.4)
        d.polygon([xy(13, 11), xy(13, 21), xy(22, 16)], fill=c)
    elif kind == "music":
        line([(18, 7), (18, 23)], 2.4)
        line([(18, 7), (27, 5), (27, 20)], 2.3)
        d.ellipse(xy(9, 20, 18, 27), fill=c)
        d.ellipse(xy(18, 17, 27, 24), fill=c)
    elif kind == "link":
        arc((3, 10, 19, 27), 40, 305, 2.5)
        arc((13, 5, 29, 22), 220, 485, 2.5)
        line([(11, 21), (21, 11)], 2.4)
    elif kind == "progress":
        round_rect((4, 7, 28, 25), 3, 2.5)
        d.rounded_rectangle(xy(8, 13, 20, 19), radius=px(2), fill=c)
    elif kind == "speed":
        arc((4, 5, 28, 29), 185, 355, 2.5)
        line([(16, 19), (22, 10)], 2.7)
        d.ellipse(xy(13.8, 16.8, 18.2, 21.2), fill=c)
        line([(6, 25), (26, 25)], 2.2)
    elif kind == "storage":
        line([(7, 4), (20, 4), (26, 10), (26, 28), (7, 28), (7, 4)], 2.2)
        line([(20, 4), (20, 10), (26, 10)], 2.0)
        line([(11, 20), (22, 20)], 2.1)
    elif kind == "folder":
        line([(4, 11), (4, 26), (28, 26), (28, 13), (16, 13), (13, 9), (4, 9)], 2.4)
    elif kind == "pause":
        d.rounded_rectangle(xy(8, 6, 13, 26), radius=px(1.6), fill=c)
        d.rounded_rectangle(xy(19, 6, 24, 26), radius=px(1.6), fill=c)
    elif kind == "resume":
        d.polygon([xy(10, 5), xy(10, 27), xy(27, 16)], fill=c)
    elif kind == "cancel":
        ellipse((4, 4, 28, 28), 2.3)
        line([(12, 12), (20, 20)], 2.3)
        line([(20, 12), (12, 20)], 2.3)
    elif kind == "success":
        ellipse((4, 4, 28, 28), 2.3)
        line([(10, 16), (14, 20), (23, 11)], 2.7)
    elif kind == "warning":
        line([(16, 4), (29, 27), (3, 27), (16, 4)], 2.4)
        line([(16, 11), (16, 19)], 2.4)
        d.ellipse(xy(14.7, 22, 17.3, 24.7), fill=c)
    elif kind == "error":
        ellipse((4, 4, 28, 28), 2.3)
        line([(11, 11), (21, 21)], 2.5)
        line([(21, 11), (11, 21)], 2.5)
    else:
        ellipse((6, 6, 26, 26), 2.5)
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def small_icon_label(parent, kind: str, size: int = 20, color: str = "#c2b4ff"):
    """Create a CTk widget holding a high-resolution vector-like icon."""
    picture = outline_icon(kind, size, color)
    photo = ctk.CTkImage(light_image=picture, dark_image=picture,
                         size=(size, size))
    widget = ctk.CTkLabel(parent, image=photo, text="", width=size, height=size,
                          fg_color="transparent")
    widget._neon_icon_reference = photo
    return widget


class HoverTooltip:
    """Show the original title on hover, without resizing download cards.

    A plain Tk top-level is used only as a temporary popup; it never sits
    over the entry, progress widgets or normal UI controls.
    """

    def __init__(self, widget, text: str, delay_ms: int = 550):
        self.widget = widget
        self.text = str(text or "")
        self.delay_ms = delay_ms
        self._timer = None
        self._window = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Button-1>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._hide()
        if self.text:
            try:
                self._timer = self.widget.after(self.delay_ms, self._show)
            except Exception:
                self._timer = None

    def _show(self):
        self._timer = None
        try:
            if not self.widget.winfo_exists() or not self.text:
                return
            import tkinter as tk
            window = tk.Toplevel(self.widget)
            window.withdraw()
            window.overrideredirect(True)
            frame = tk.Frame(window, bg="#8b69e8", bd=0)
            frame.pack()
            tk.Label(frame, text=self.text, bg="#191a49", fg="#f6f3ff",
                     justify="left", wraplength=440, padx=13, pady=9,
                     font=(FONT, 11)).pack(padx=1, pady=1)
            window.update_idletasks()
            x = min(self.widget.winfo_pointerx() + 14,
                    self.widget.winfo_screenwidth() - window.winfo_reqwidth() - 12)
            y = min(self.widget.winfo_pointery() + 16,
                    self.widget.winfo_screenheight() - window.winfo_reqheight() - 12)
            window.geometry(f"+{max(0, x)}+{max(0, y)}")
            window.deiconify()
            self._window = window
        except Exception:
            self._window = None

    def _hide(self, _event=None):
        if self._timer is not None:
            try:
                self.widget.after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None


class NeonGlassPanel(ctk.CTkFrame):
    """Stable tinted-glass card: a subtle rounded border, no overlay canvas.

    The V1.5/V1.6 canvas light streak was visible as a hard horizontal stripe
    at the top of each card. Drawing the frame natively also guarantees there
    are no overlapping layers obscuring entries or clickable controls.
    """
    def __init__(self, parent, *, height=100, corner_radius=19, accent="violet"):
        # Native CustomTkinter border only: unlike the V1.5 glass overlay,
        # this does not cover text, input fields or button click targets.
        edges = {
            "violet": "#4a4d92",  # calm lavender
            "blue": "#42639d",    # cooler edge for media/list panels
            "pink": "#70458e",    # subtle warm edge for the download options
        }
        color = edges.get(accent, edges["violet"])
        super().__init__(parent, height=height, corner_radius=corner_radius,
                         fg_color=PANEL, border_color=color, border_width=1)


class GradientButton(ctk.CTkFrame):
    """A rounded, interactive image gradient hosted by a CTk widget."""
    def __init__(self, parent, text: str, command, gradient="gradient_hot.png",
                 height=61, font_size=17, icon="⇩", width=180):
        super().__init__(parent, fg_color="transparent", corner_radius=14,
                         height=height, width=width)
        self.text, self.icon, self.command = text, icon, command
        self.font_size = font_size
        self.height_px = height
        self.gradient = Image.open(ASSETS / gradient).convert("RGB")
        import tkinter as tk
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                bg=PANEL_DARK, cursor="hand2", height=height)
        self.canvas.pack(fill="both", expand=True)
        self._bitmap = None
        self.hovered = False
        self.canvas.configure(takefocus=1)
        self.canvas.bind("<Configure>", self.redraw)
        self.canvas.bind("<Button-1>", self._activate)
        self.canvas.bind("<KeyRelease-Return>", lambda _event: self.command())
        self.canvas.bind("<KeyRelease-space>", lambda _event: self.command())
        self.canvas.bind("<Enter>", self._hover_enter)
        self.canvas.bind("<Leave>", self._hover_leave)
        self.canvas.bind("<FocusIn>", self.redraw)
        self.canvas.bind("<FocusOut>", self.redraw)

    def _activate(self, _event=None):
        self.canvas.focus_set()
        self.command()

    def _hover_enter(self, _event=None):
        self.hovered = True
        self.redraw()

    def _hover_leave(self, _event=None):
        self.hovered = False
        self.redraw()

    def redraw(self, _event=None):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 3 or h < 3:
            return
        blend = self.gradient.resize((w, h), Image.Resampling.BICUBIC).convert("RGBA")
        mask = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(mask)
        d.rounded_rectangle((0, 0, w-1, h-1), radius=15, fill=255)
        rounded = Image.new("RGBA", (w, h), PANEL_DARK)
        rounded.paste(blend, (0, 0), mask)
        # Narrow glass reflection along the top; drawn into the image so no
        # overlay widget can intercept button clicks.
        sheen = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        sheen_pixels = ImageDraw.Draw(sheen, "RGBA")
        sheen_pixels.rounded_rectangle(
            (2, 2, w - 3, max(4, round(h * .44))),
            radius=13, fill=(255, 255, 255, 19))
        rounded = Image.alpha_composite(rounded, sheen)
        if self.hovered:
            halo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(halo, "RGBA").rounded_rectangle(
                (1, 1, w - 2, h - 2), radius=14,
                fill=(255, 255, 255, 15))
            rounded = Image.alpha_composite(rounded, halo)
        border = ImageDraw.Draw(rounded, "RGBA")
        border.rounded_rectangle((1, 1, w - 2, h - 2), radius=14,
                                 outline=(255, 231, 255, 175 if self.hovered else 100), width=1)
        self._bitmap = ImageTk.PhotoImage(rounded)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._bitmap)
        title = f"{self.icon}  {self.text}" if self.icon else self.text
        self.canvas.create_text(w / 2, h / 2 + 1, text=title,
                                fill="#58206e", font=(FONT, self.font_size, "bold"))
        self.canvas.create_text(w / 2, h / 2, text=title,
                                fill="white", font=(FONT, self.font_size, "bold"))


class NeonSelectionButton(ctk.CTkFrame):
    """Canvas button with screenshot-style purple gradient selection.

    Used for both sidebar navigation and video/audio mode tabs.  All drawing
    is pixel based, so Windows display scaling does not change the layout.
    """

    def __init__(self, parent, text: str, command, *, icon="", height=60,
                 font_size=16, centered=False, width=264):
        super().__init__(parent, fg_color="transparent", corner_radius=0,
                         height=height, width=width)
        import tkinter as tk
        self.text = text
        self.command = command
        self.icon = icon
        self.font_size = font_size
        self.centered = centered
        self.selected = False
        self.hovered = False
        self.gradient = Image.open(ASSETS / "gradient_purple.png").convert("RGB")
        icon_size = 20 if centered else 27
        self._nav_icon_size = icon_size
        self._nav_icon_bitmap = ImageTk.PhotoImage(
            outline_icon(self.icon, icon_size, "#f1eeff")) if self.icon else None
        self.canvas = tk.Canvas(self, bg="#100d3d" if not centered else PANEL,
                                highlightthickness=0, bd=0, height=height,
                                cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.configure(takefocus=1)
        self.canvas.bind("<Configure>", self.redraw)
        self.canvas.bind("<Enter>", self._enter)
        self.canvas.bind("<Leave>", self._leave)
        self.canvas.bind("<Button-1>", self._activate)
        self.canvas.bind("<KeyRelease-Return>", self._activate)
        self.canvas.bind("<KeyRelease-space>", self._activate)
        self.canvas.bind("<FocusIn>", self.redraw)
        self.canvas.bind("<FocusOut>", self.redraw)

    def _activate(self, _event=None):
        self.canvas.focus_set()
        self.command()

    def _enter(self, _event):
        self.hovered = True
        self.redraw()

    def _leave(self, _event):
        self.hovered = False
        self.redraw()

    def set_selected(self, selected: bool):
        if self.selected != selected:
            self.selected = selected
            self.redraw()

    def redraw(self, _event=None):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w <= 3 or h <= 3:
            return
        bg = PANEL if self.centered else "#100d3d"
        layer = Image.new("RGB", (w, h), bg)
        if self.selected:
            active = self.gradient.resize((w, h), Image.Resampling.BICUBIC)
            mask = Image.new("L", (w, h), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.rounded_rectangle((1, 1, w - 2, h - 2), radius=15, fill=255)
            layer.paste(active, (0, 0), mask)
            # The upper edge highlights the translucent, glassy look.
            line = ImageDraw.Draw(layer, "RGBA")
            line.rounded_rectangle((1, 1, w - 2, h - 2), radius=15,
                                   outline=(241, 182, 255, 145), width=1)
            line.rounded_rectangle((3, 3, w - 4, max(4, int(h * .40))), radius=11,
                                   fill=(255, 255, 255, 24))
            if not self.centered:
                line.rounded_rectangle((2, 7, 5, h - 8), radius=2,
                                       fill=(255, 228, 255, 178))
        elif self.hovered or self.centered:
            draw = ImageDraw.Draw(layer, "RGBA")
            color = ((30, 33, 84, 220) if self.hovered and not self.centered
                     else (23, 36, 89, 220))
            draw.rounded_rectangle((1, 1, w - 2, h - 2), radius=15,
                                   fill=color, outline=(64, 82, 173, 190), width=1)
        # Focus outline is painted into the same bitmap, not a new overlay.
        if self.canvas.focus_get() == self.canvas:
            ImageDraw.Draw(layer).rounded_rectangle(
                (2, 2, w - 3, h - 3), radius=13,
                outline="#e1baff", width=2)
        self._bitmap = ImageTk.PhotoImage(layer)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._bitmap)
        weight = "bold" if self.selected else "normal"
        if self.centered:
            if self._nav_icon_bitmap:
                # Center the icon AND title as one group, using Tk's actual
                # font metrics rather than hard-coded offsets or glyphs.
                import tkinter.font as tk_font
                font = tk_font.Font(family=FONT, size=self.font_size, weight=weight)
                text_width = font.measure(self.text)
                group_width = self._nav_icon_size + 8 + text_width
                start_x = max(7, (w - group_width) / 2)
                self.canvas.create_image(start_x + self._nav_icon_size / 2,
                                         h / 2, image=self._nav_icon_bitmap)
                self.canvas.create_text(start_x + self._nav_icon_size + 8,
                                        h / 2, text=self.text, fill=TEXT,
                                        font=font, anchor="w")
            else:
                self.canvas.create_text(w // 2, h // 2, text=self.text,
                                        fill=TEXT, font=(FONT, self.font_size, weight))
        else:
            if self._nav_icon_bitmap:
                self.canvas.create_image(43, h // 2, image=self._nav_icon_bitmap,
                                         anchor="center")
            self.canvas.create_text(77, h // 2, text=self.text, fill=TEXT,
                                    font=(FONT, self.font_size, weight), anchor="w")


class NeonGradientProgress(ctk.CTkFrame):
    """Progress bar with the magenta-to-sunset gradient in the reference."""

    def __init__(self, parent, *, height=23):
        super().__init__(parent, fg_color="transparent", height=height)
        import tkinter as tk
        self.value = 0.0
        self.gradient = Image.open(ASSETS / "gradient_hot.png").convert("RGB")
        self.canvas = tk.Canvas(self, height=height, bg=PANEL,
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._draw_progress)

    def set(self, value):
        try:
            self.value = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            self.value = 0.0
        self._draw_progress()

    def _draw_progress(self, _event=None):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 4 or h < 4:
            return
        radius = min(12, h // 2)
        layer = Image.new("RGB", (w, h), PANEL)
        draw = ImageDraw.Draw(layer)
        draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius,
                               fill="#1b245f", outline="#2d347d", width=1)
        fill_w = min(w, max(0, round(w * self.value)))
        if fill_w > 0:
            # A softly blurred leading-edge glow is composited into the
            # progress bitmap itself, not placed over other CTk widgets.
            glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(glow, "RGBA").ellipse(
                (fill_w - 21, -8, fill_w + 9, h + 7),
                fill=(237, 56, 213, 88))
            glow = glow.filter(ImageFilter.GaussianBlur(8))
            layer = Image.alpha_composite(layer.convert("RGBA"), glow).convert("RGB")
            # Resize from the full gradient: colors advance naturally as
            # progress increases, just like in the reference design.
            gradient = self.gradient.resize((max(1, w), h), Image.Resampling.BILINEAR)
            mask = Image.new("L", (w, h), 0)
            md = ImageDraw.Draw(mask)
            md.rounded_rectangle((0, 0, max(1, fill_w - 1), h - 1),
                                 radius=min(radius, max(1, fill_w // 2)), fill=255)
            layer.paste(gradient, (0, 0), mask)
        self._bitmap = ImageTk.PhotoImage(layer)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._bitmap)


class NeonHero(ctk.CTkFrame):
    """Full-width responsive header, blending the supplied neon wave artwork.

    All drawing is done on an ordinary Tk canvas, not CustomTkinter's private
    ``_draw`` method. Keeping the banner independent from framework internals
    prevents the regression seen in the earlier progress-bar implementation.
    """

    def __init__(self, parent, height=132):
        super().__init__(parent, height=height, fg_color="transparent", corner_radius=0)
        import tkinter as tk
        self.artwork = Image.open(ASSETS / "hero_art.png").convert("RGBA")
        self.canvas = tk.Canvas(self, bg=BG, bd=0, highlightthickness=0)
        self.canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.canvas.bind("<Configure>", self._paint_banner)
        self._banner_bitmap = None
        self._banner_size = None
        self.heading = make_label(self, APP_NAME, 35, TEXT, True, anchor="w")
        self.heading.place(x=24, y=21)
        self.subtitle = make_label(
            self, "Videos und Audio einfach und schnell herunterladen.",
            16, "#e4e7ff", anchor="w")
        self.subtitle.place(x=25, y=76)

    def _paint_banner(self, _event=None):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 20 or h < 20 or self._banner_size == (w, h):
            return
        self._banner_size = (w, h)
        layer = Image.new("RGB", (w, h), BG)
        # Diffuse violet/pink light gently connects the banner to the dark UI.
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        brush = ImageDraw.Draw(glow, "RGBA")
        brush.ellipse((int(w * .42), -h * 2, int(w * .95), h * 2),
                      fill=(94, 21, 204, 92))
        brush.ellipse((int(w * .68), -h, int(w * 1.1), h * 1.8),
                      fill=(240, 24, 192, 56))
        # An additional cool halo echoes the blue-violet edge of the
        # reference banner; it remains inside the existing image bitmap.
        brush.ellipse((int(w * .54), -h // 3, int(w * .82), h * 1.5),
                      fill=(59, 83, 239, 28))
        glow = glow.filter(ImageFilter.GaussianBlur(max(12, h // 4)))
        layer.paste(glow, (0, 0), glow.getchannel("A"))
        target_w = min(max(int(w * .71), 580), 1180)
        target_h = max(1, round(target_w * self.artwork.height / self.artwork.width))
        resized = self.artwork.resize((target_w, target_h), Image.Resampling.LANCZOS)
        # V1.23: smoothstep blends the art into the header instead of a
        # linear fade with a visible edge at some Windows DPI settings.
        fade = smooth_left_fade(target_w, target_h, .33)
        alpha = ImageChops.multiply(resized.getchannel("A"), fade)
        resized.putalpha(alpha)
        artwork_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        artwork_layer.paste(resized, (w - target_w, (h - target_h) // 2), resized)
        layer.paste(artwork_layer, (0, 0), artwork_layer.getchannel("A"))
        # V1.22: ambient light becomes part of the artwork itself. Keep the
        # left-hand headline zone untouched; no new Tk canvas or CTk overlay.
        layer = add_neon_halos(layer, [
            (.72, .46, .17, .64, (111, 42, 255), 29, .22),
            (.91, .65, .18, .58, (246, 38, 176), 38, .18),
            (.57, .93, .24, .22, (70, 96, 232), 24, .12),
            # Very soft pink rim around the play symbol; no hard edge.
            (.82, .22, .14, .32, (255, 87, 191), 19, .20),
        ]).convert("RGB")
        # Low-opacity edge illumination is composited into the HERO bitmap,
        # never placed on top of the heading or link entry as a separate UI.
        bottom_light = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        trace = ImageDraw.Draw(bottom_light, "RGBA")
        trace.line((int(w * .45), h - 3, w - 5, h - 3),
                   fill=(115, 65, 255, 68), width=2)
        trace.line((int(w * .76), h - 2, w - 5, h - 2),
                   fill=(249, 37, 213, 60), width=1)
        bottom_light = bottom_light.filter(ImageFilter.GaussianBlur(2))
        layer = Image.alpha_composite(layer.convert("RGBA"), bottom_light).convert("RGB")
        self._banner_bitmap = ImageTk.PhotoImage(layer)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._banner_bitmap, anchor="nw")


def log_scroll_top_fraction(content_height: float, viewport_height: float,
                            bottom_gap: float) -> float:
    """Keep the same older messages visible when new cards appear above them.

    Tk Canvas.yview_moveto expects a fraction of the *entire* scrollregion.
    `bottom_gap` is the distance between the visible window and the end of
    the content, in pixels, before the list was updated.
    """
    content_height = max(0.0, float(content_height))
    viewport_height = max(0.0, float(viewport_height))
    bottom_gap = max(0.0, float(bottom_gap))
    if content_height <= viewport_height or content_height <= 0:
        return 0.0
    return max(0.0, min(1.0, (content_height - viewport_height - bottom_gap)
                        / content_height))


class NeonTubeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title(APP_NAME)
        self.configure(fg_color=BG)
        try:
            self.iconbitmap(str(ASSETS / "app.ico"))
        except Exception:
            pass
        width = min(1536, max(1180, self.winfo_screenwidth() - 80))
        height = min(1024, max(760, self.winfo_screenheight() - 70))
        self.geometry(f"{width}x{height}")
        self.minsize(1130, 700)

        self.config_data = load_json(CONFIG_FILE, {})
        self.i18n = LanguageManager(DATA, self.config_data.get("language", "de"))
        self.config_data.setdefault("download_dir", desktop_downloads())
        self.config_data["folder_organization"] = normalize_folder_organization(
            self.config_data.get("folder_organization", ""))
        self.config_data.setdefault("concurrent", 2)
        self.config_data.setdefault("cookiefile", "")
        self.config_data.setdefault("profiles", {
            "Standard": {"mode": "Video (MP4)", "quality": "1080p",
                         "audio_format": "MP3", "playlist": True}
        })
        self.youtube_api_key = read_api_key(DATA)
        self.search_counter = 0
        # A generation changes only when the result set is replaced, not on
        # pagination. First-page thumbnails can finish during 'load more'.
        self.search_generation = 0
        self.search_cache = {}
        self.search_results = []
        self.search_next_page = ""
        self.search_result_labels = {}
        self.search_result_cards = []
        self.search_result_titles = []
        self.search_favorite_buttons = {}
        # Selected search videos are only kept in memory for the current query.
        # The selection survives "Weitere Ergebnisse laden", not a new search.
        self.search_selected_ids = set()
        self.search_select_vars = {}
        self.search_result_frames = {}
        self._search_layout_columns = 0
        self._search_last_wrap = 0
        self.search_query_text = ""
        self.favorites = FavoriteStore(FAVORITES_FILE)
        self.favorite_result_cards = []
        self.favorite_result_titles = []
        self.favorite_result_labels = {}
        self.favorite_generation = 0
        self._favorite_layout_columns = 0
        self._favorite_last_wrap = 0
        self.history = load_json(HISTORY_FILE, [])
        if not isinstance(self.history, list):
            self.history = []
        self.ui_events: queue.Queue = queue.Queue()
        self.manager = DownloadManager(self.ui_events,
                                       self.config_data.get("concurrent", 2),
                                       self.config_data.get("cookiefile", ""))
        self.current_job_id = ""
        self.current_meta = {}
        self.metadata_counter = 0
        self.thumbnail_cache = {}
        self.queue_widgets = {}
        self._queue_rendered_ids = ()
        self.history_widgets = []
        self.nav_buttons = {}
        self.active_page = "download"
        self.mode = ctk.StringVar(value="Video (MP4)")
        self.quality = ctk.StringVar(value="1080p")
        self.audio_format = ctk.StringVar(value="MP3")
        self.playlist = ctk.BooleanVar(value=True)
        self.output_dir = ctk.StringVar(value=self.config_data["download_dir"])
        self.profile_name = ctk.StringVar(value="Standard")
        self._preview_after = None
        # Log-Daten bleiben nur während dieser Sitzung im Speicher.
        # Weder Download-Engine noch persistenter Verlauf werden verändert.
        self.log_entries = []
        self.log_filter = "Alle Ereignisse"
        self._log_seen_states = {}
        self._log_progress_deciles = {}
        self._log_render_pending = False
        # Neueste Meldungen stehen oben. Nach manuellem Scrollen zu älteren
        # Meldungen bleibt der Ausschnitt stabil, bis man wieder oben ist.
        self._log_auto_follow = True
        self._log_scroll_restoring = False
        self._log_scroll_generation = 0
        # Keep all clipboard detection transient (no clipboard data is saved).
        # Initially ignore a link that was already copied before app launch.
        self._clipboard_watcher = None
        self._clipboard_watch_after = None
        self._build_header()
        self._build_body()
        self._build_download_page()
        self._build_search_page()
        self._build_favorites_page()
        self._build_secondary_pages()
        self._build_log_page()
        self._apply_profile("Standard")
        self._switch_page("download")
        self._render_queue()
        self._render_history_summary()
        self._refresh_progress()
        self._log_event("info", "Download-System bereit. Noch kein Download gestartet.")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(180, self._poll_events)
        self._start_clipboard_watch()
        self.after(120, self._refresh_translated_ui)

    def _refresh_translated_ui(self):
        """Translate static interface labels, including newly created cards."""
        try:
            self.i18n.collect()
            self.i18n.refresh_widgets(self)
            self.after(950, self._refresh_translated_ui)
        except Exception:
            # UI translation is optional and must never stop downloading.
            self.after(1500, self._refresh_translated_ui)

    def _choose_language(self, label):
        """Persist the selected UI language without changing download settings."""
        code = self.i18n.languages.get(label)
        if code is None or not self.i18n.set_language(code):
            return
        self.config_data["language"] = code
        try:
            save_json(CONFIG_FILE, self.config_data)
        except OSError:
            pass
        self.i18n.refresh_widgets(self)

    # ----------------------------------------------------- Primary layout
    def _build_header(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        bar = ctk.CTkFrame(self, fg_color="#08072e", corner_radius=0, height=83)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)
        # A restrained 1px divider separates the title area from the app.
        # Native CTkFrame: no canvas overlay over interactive controls.
        ctk.CTkFrame(bar, height=1, corner_radius=0,
                     fg_color="#282257").place(relx=.02, rely=1.0,
                                               relwidth=.96, anchor="sw")
        self.brand_logo = img("neontube_logo.png", (44, 44))
        ctk.CTkLabel(bar, text="", image=self.brand_logo, width=58).grid(
            row=0, column=0, rowspan=2, padx=(25, 8), pady=(16, 4))
        make_label(bar, APP_NAME, 21, TEXT, True,
                   anchor="w").grid(row=0, column=1, sticky="sw", pady=(19, 0))
        make_label(bar, "Videos und Audio einfach und schnell herunterladen.",
                   12, "#dfe2ff", anchor="w").grid(row=1, column=1,
                                                       sticky="nw", pady=(0, 13))
        # Kein Zahnrad oben rechts: Einstellungen bleiben über den
        # entsprechenden Menüpunkt in der linken Seitenleiste erreichbar.
        # Unter Windows übernimmt die native Titelleiste weiterhin die
        # Steuerung zum Minimieren, Maximieren und Schließen.
        if sys.platform != "win32":
            controls = ctk.CTkFrame(bar, fg_color="transparent")
            controls.grid(row=0, column=2, rowspan=2, padx=(0, 20), sticky="e")
            header_actions = [("—", self.iconify),
                              ("□", self._toggle_maximize),
                              ("×", self.on_close)]
            for symbol, callback in header_actions:
                b = ctk.CTkButton(controls, text=symbol, command=callback, width=45,
                                  height=40, fg_color="transparent",
                                  hover_color="#29205b", corner_radius=10,
                                  text_color="#b9c4ff",
                                  font=ctk.CTkFont(family=FONT, size=23))
                b.pack(side="left", padx=3)

    def _toggle_maximize(self):
        if self.state() == "zoomed":
            self.state("normal")
        else:
            try:
                self.state("zoomed")
            except Exception:
                self.attributes("-zoomed", not bool(self.attributes("-zoomed")))

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(0, minsize=300)
        self.sidebar = ctk.CTkFrame(body, fg_color="#100d3d", border_width=1,
                                    border_color="#33348b", corner_radius=18, width=284)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(12, 3), pady=(17, 18))
        self.sidebar.grid_propagate(False)
        self.sidebar.bind("<Configure>", self._resize_sidebar_art)
        self.sidebar_art = ctk.CTkLabel(self.sidebar, text="")
        self.sidebar_art.place(x=1, y=481)
        self._art_height = None
        items = [("download", "download", "Download"),
                 ("search", "search", "YouTube-Suche"),
                 ("favorites", "favorite", "Favoriten"),
                 ("history", "history", "Verlauf"),
                 ("settings", "settings", "Einstellungen"),
                 ("profiles", "profiles", "Profile"),
                 ("about", "info", "Über")]
        for idx, (key, ico, label) in enumerate(items):
            b = NeonSelectionButton(
                self.sidebar, label,
                command=lambda k=key: self._switch_page(k),
                icon=ico, height=60, font_size=16, width=264)
            b.place(x=7, y=11 + idx * 61)
            self.nav_buttons[key] = b

        self.main = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew", padx=(10, 22), pady=(8, 15))
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(0, weight=1)
        self.download_page = ctk.CTkScrollableFrame(
            self.main, fg_color="transparent", corner_radius=0,
            scrollbar_button_color="#252061", scrollbar_button_hover_color=PURPLE)
        self.search_page = ctk.CTkScrollableFrame(
            self.main, fg_color="transparent", corner_radius=0,
            scrollbar_button_color="#252061", scrollbar_button_hover_color=PURPLE)
        self.favorites_page = ctk.CTkScrollableFrame(
            self.main, fg_color="transparent", corner_radius=0,
            scrollbar_button_color="#252061", scrollbar_button_hover_color=PURPLE)
        self.history_page = ctk.CTkScrollableFrame(
            self.main, fg_color="transparent", corner_radius=0,
            scrollbar_button_color="#252061", scrollbar_button_hover_color=PURPLE)
        self.profiles_page = ctk.CTkScrollableFrame(
            self.main, fg_color="transparent", corner_radius=0)
        self.settings_page = ctk.CTkScrollableFrame(
            self.main, fg_color="transparent", corner_radius=0)
        self.log_page = ctk.CTkFrame(self.main, fg_color="transparent", corner_radius=0)
        self.about_page = ctk.CTkScrollableFrame(
            self.main, fg_color="transparent", corner_radius=0)
        for page in (self.download_page, self.search_page, self.favorites_page,
                     self.history_page,
                     self.profiles_page, self.settings_page, self.log_page,
                     self.about_page):
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_remove()

    def _resize_sidebar_art(self, event=None):
        height = self.sidebar.winfo_height() - 481
        if height < 125:
            self.sidebar_art.place_forget()
            return
        height = min(587, height)
        if self._art_height == height:
            return
        self._art_height = height
        picture = Image.open(ASSETS / "sidebar_art.png").convert("RGBA")
        picture = picture.resize((282, int(height)), Image.Resampling.LANCZOS)
        # Warm sunset and cool lake reflections: image pixels only, so the
        # navigation and its keyboard/mouse handling are never obscured.
        picture = add_neon_halos(picture, [
            (.12, .50, .48, .27, (245, 42, 144), 31, .075),
            (.91, .72, .40, .27, (143, 49, 246), 29, .095),
            (.55, .96, .54, .13, (180, 39, 240), 22, .06),
            # Keep the lake reflection luminous but softly integrated.
            (.40, .80, .29, .16, (115, 75, 237), 16, .12),
        ])
        self._side_ctk_image = ctk.CTkImage(light_image=picture,
                                            dark_image=picture, size=(282, int(height)))
        self.sidebar_art.configure(image=self._side_ctk_image)
        self.sidebar_art.place(x=0, y=481)

    def _switch_page(self, key):
        if key == "settings":
            self.open_settings()
            return
        self.active_page = key
        pages = {"download": self.download_page, "search": self.search_page,
                 "favorites": self.favorites_page, "history": self.history_page,
                 "profiles": self.profiles_page, "settings": self.settings_page,
                 "log": self.log_page, "about": self.about_page}
        for name, page in pages.items():
            if name == key:
                page.grid()
            else:
                page.grid_remove()
        for name, b in self.nav_buttons.items():
            b.set_selected(name == key)
        if key == "favorites":
            self._render_favorites()
        elif key == "history":
            self._render_full_history()
        elif key == "profiles":
            self._render_full_profiles()
        elif key == "log":
            # Nach dem Zurückkehren auch die in der Zwischenzeit entstandenen
            # Meldungen anzeigen und direkt zum neuesten Eintrag springen.
            self._render_log_entries(reset_scroll=True)

    # ------------------------------------------------------- Download page
    def _build_download_page(self):
        parent = self.download_page
        parent.grid_columnconfigure(0, weight=1)
        hero = NeonHero(parent, height=132)
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 9))
        hero.grid_propagate(False)
        self.hero = hero

        link_panel = NeonGlassPanel(parent, height=46, corner_radius=14,
                                    accent="blue")
        link_panel.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        link_panel.grid_propagate(False)
        link_panel.grid_columnconfigure(1, weight=1)
        small_icon_label(link_panel, "link", 20, "#e4e0ff").grid(
            row=0, column=0, padx=(16, 7), pady=5)
        # CTk's built-in placeholder may disappear on some Windows versions
        # after programmatic delete()/focus changes. A non-editable visual hint
        # bound to the StringVar stays visible whenever the input is empty.
        self.url_text = ctk.StringVar(value="")
        self.url_input = ctk.CTkEntry(
            link_panel, textvariable=self.url_text,
            fg_color="transparent", border_width=0, height=36,
            text_color=TEXT, font=ctk.CTkFont(family=FONT, size=12))
        self.url_input.grid(row=0, column=1, sticky="ew", pady=4)
        self.url_hint = make_label(
            self.url_input, "YouTube-Link einfügen … (mehrere Links möglich)",
            12, "#9aafff", anchor="w")
        self.url_hint.bind("<Button-1>", lambda _e: self.url_input.focus_set())
        self.url_text.trace_add("write", self._on_url_text_changed)
        self._update_url_hint()
        self.url_input.bind("<Return>", lambda _e: self.start_downloads())
        GradientButton(link_panel, "Link einfügen", self.paste_link,
                       gradient="gradient_purple.png", icon="", width=145,
                       height=42, font_size=13).grid(
                           row=0, column=2, padx=(4, 4), sticky="ew")

        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.grid(row=2, column=0, sticky="ew")
        grid.grid_columnconfigure(0, weight=17, uniform="split")
        grid.grid_columnconfigure(1, weight=10, uniform="split")
        left = ctk.CTkFrame(grid, fg_color="transparent")
        right = ctk.CTkFrame(grid, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        right.grid(row=0, column=1, sticky="nsew", padx=(11, 0))
        left.grid_columnconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self._build_options(left)
        self._build_preview(left)
        self._build_progress(left)
        self._build_queue(right)
        self._build_history_summary(right)


    # --------------------------------------------------------- YouTube search
    def _build_search_page(self):
        page = self.search_page
        page.grid_columnconfigure(0, weight=1)
        make_label(page, "YouTube-Suche", 30, TEXT, True).grid(
            row=0, column=0, sticky="w", pady=(23, 6))
        make_label(page, "Videos finden und direkt in deine Download-Warteschlange übernehmen.",
                   13, MUTED).grid(row=1, column=0, sticky="w", pady=(0, 16))

        bar = NeonGlassPanel(page, height=68, corner_radius=15, accent="blue")
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        bar.grid_columnconfigure(1, weight=1)
        small_icon_label(bar, "search", 25, "#d5c8ff").grid(
            row=0, column=0, padx=(15, 9), pady=14)
        self.search_text = ctk.StringVar()
        self.search_input = ctk.CTkEntry(
            bar, textvariable=self.search_text, height=39,
            font=ctk.CTkFont(family=FONT, size=14),
            fg_color="#0d143e", border_width=1, border_color="#464b91",
            placeholder_text="Titel, Künstler oder Thema suchen …")
        self.search_input.grid(row=0, column=1, sticky="ew", pady=12)
        self.search_input.bind("<Return>", lambda _e: self._search_start())
        regular_button(bar, "Suchen", self._search_start, fg="#7727cc", hover=PURPLE,
                       width=104, height=39, font_size=13).grid(
                           row=0, column=2, padx=(9, 15), pady=12)
        make_label(bar, "Treffer:", 12, MUTED, anchor="e").grid(
            row=0, column=3, padx=(0, 7), pady=12)
        configured_count = str(self.config_data.get("search_page_size", 12))
        if configured_count not in ("6", "12", "24"):
            configured_count = "12"
        self.search_page_size = ctk.StringVar(value=configured_count)
        self.search_page_count_menu = ctk.CTkOptionMenu(
            bar, values=["6", "12", "24"], variable=self.search_page_size,
            command=self._search_size_changed,
            width=74, height=38, corner_radius=10,
            fg_color="#17205a", button_color="#5923a8",
            button_hover_color=PURPLE, text_color=TEXT,
            font=ctk.CTkFont(family=FONT, size=12))
        self.search_page_count_menu.grid(row=0, column=4, padx=(0, 14), pady=12)

        self.search_status = make_label(
            page, "Bitte einen API-Schlüssel unter Einstellungen eintragen, um zu suchen."
            if not self.youtube_api_key else "Gib einen Suchbegriff ein und klicke auf Suchen.",
            12, MUTED, anchor="w")
        self.search_status.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        # Compact selection toolbar; same dark-neon styling as the existing UI.
        selection_bar = ctk.CTkFrame(page, fg_color="#101743", corner_radius=12,
                                     border_width=1, border_color="#42498e", height=45)
        selection_bar.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        selection_bar.grid_columnconfigure(0, weight=1)
        self.search_selected_count = make_label(
            selection_bar, "0 Videos ausgewählt", 12, MUTED, anchor="w")
        self.search_selected_count.grid(row=0, column=0, sticky="w", padx=(14, 6), pady=6)
        self.search_select_all_button = regular_button(
            selection_bar, "Alle auswählen", self._select_all_search_results,
            width=117, height=30, font_size=11)
        self.search_select_all_button.grid(row=0, column=1, padx=(4, 3), pady=6)
        self.search_clear_button = regular_button(
            selection_bar, "Auswahl aufheben", self._clear_search_selection,
            width=129, height=30, font_size=11)
        self.search_clear_button.grid(row=0, column=2, padx=3, pady=6)
        self.search_batch_button = regular_button(
            selection_bar, "Zur Warteschlange (0)", self._enqueue_selected_search_results,
            width=185, height=30, font_size=11, fg="#711cbd", hover=PURPLE)
        self.search_batch_button.grid(row=0, column=3, padx=(4, 10), pady=6)
        self._update_search_selection_controls()
        self.search_list = ctk.CTkFrame(page, fg_color="transparent")
        self.search_list.grid(row=5, column=0, sticky="ew")
        # Reflow existing cards when the user resizes/maximizes the window.
        self.search_list.bind("<Configure>", self._search_list_resized, add="+")
        self.search_more = regular_button(
            page, "Weitere Ergebnisse laden", self._search_next,
            width=215, height=39, font_size=12)
        self.search_more.grid(row=6, column=0, sticky="w", pady=(13, 20))
        self.search_more.grid_remove()

    @staticmethod
    def _search_grid_columns(width):
        """Use the space efficiently without squeezing titles/buttons."""
        if width >= 1290:
            return 3
        if width >= 880:
            return 2
        return 1

    def _search_list_resized(self, event=None):
        if self.search_result_cards:
            self._reflow_search_cards(getattr(event, "width", None))

    def _reflow_search_cards(self, width=None):
        width = max(1, int(width or self.search_list.winfo_width()))
        if width < 100:
            width = max(width, self.search_page.winfo_width() - 18)
        cols = self._search_grid_columns(width)
        card_width = max(250, (width - cols * 12) // cols)
        wrap = max(158, card_width - 205)
        if (cols, wrap) == (self._search_layout_columns, self._search_last_wrap):
            return
        self._search_layout_columns = cols
        self._search_last_wrap = wrap
        for col in range(3):
            self.search_list.grid_columnconfigure(
                col, weight=1 if col < cols else 0,
                uniform="results" if col < cols else "", minsize=0)
        # Approximate text width in every card, with some room for card padding.
        for idx, frame in enumerate(self.search_result_cards):
            frame.grid(row=idx // cols, column=idx % cols,
                       sticky="nsew", padx=(0, 10), pady=6)
            self.search_result_titles[idx].configure(wraplength=wrap)

    def _search_size_changed(self, value):
        try:
            self.config_data["search_page_size"] = int(value)
            save_json(CONFIG_FILE, self.config_data)
        except (ValueError, OSError):
            pass  # A read-only settings file must not break the search.
        if self.search_text.get().strip() and self.youtube_api_key:
            self._search_start()

    def _search_start(self):
        self._search_execute(page_token="")

    def _search_next(self):
        if self.search_next_page:
            self._search_execute(page_token=self.search_next_page)

    def _search_execute(self, page_token=""):
        term = self.search_text.get().strip()
        if not term:
            self.search_status.configure(text="Bitte zuerst einen Suchbegriff eingeben.",
                                         text_color="#ffb0be")
            self.search_input.focus_set()
            return
        if not self.youtube_api_key:
            self.search_status.configure(
                text="API-Schlüssel fehlt. Bitte unter Einstellungen speichern.",
                text_color="#ffb0be")
            return
        if page_token and term != self.search_query_text:
            page_token = ""
        self.search_query_text = term
        self.search_counter += 1
        seq = self.search_counter
        self.search_status.configure(text=f"Suche nach „{term}“ läuft …", text_color=MUTED)
        self.search_more.grid_remove()
        if not page_token:
            # Clear selection only for a genuinely new query. Pagination
            # extends the current results without losing marked videos.
            if hasattr(self, "search_selected_ids"):
                self._clear_search_selection()
            self.search_generation += 1
            self.search_next_page = ""
            for child in self.search_list.winfo_children():
                child.destroy()
            self.search_result_labels.clear()
            self.search_favorite_buttons.clear()
            if hasattr(self, "search_select_vars"):
                self.search_select_vars.clear()
                self.search_result_frames.clear()
            self.search_results = []
            self.search_result_cards.clear()
            self.search_result_titles.clear()
            self._search_layout_columns = 0
            self._search_last_wrap = 0
        threading.Thread(target=self._search_worker,
                         args=(seq, term, page_token, self.youtube_api_key,
                               int(self.search_page_size.get())), daemon=True).start()

    def _search_worker(self, seq, term, page_token, api_key, count):
        try:
            data = search_videos(term, api_key, page_token=page_token, max_results=count)
            self.ui_events.put(("search_results", "", (seq, term, page_token, data)))
        except YouTubeAPIError as exc:
            self.ui_events.put(("search_error", "", (seq, str(exc))))
        except Exception as exc:
            self.ui_events.put(("search_error", "",
                                (seq, f"Unerwarteter Fehler: {type(exc).__name__}")))

    def _display_search_results(self, term, page_token, data):
        self.search_next_page = data.get("next_page_token", "")
        seen_ids = {video.get("id") for video in self.search_results}
        results = []
        for item in data.get("items", []):
            video_id = item.get("id")
            if video_id and video_id not in seen_ids:
                results.append(item)
                seen_ids.add(video_id)
        self.search_results.extend(results)
        for item in results:
            frame = ctk.CTkFrame(self.search_list, fg_color="#101743", border_width=1,
                                 border_color="#42498e", corner_radius=14)
            frame.grid_columnconfigure(1, weight=1)
            self.search_result_frames[item["id"]] = frame
            # Wide 16:9 preview instead of the old tiny 118x76 thumbnail.
            placeholder = ctk.CTkLabel(
                frame, text="▶", width=160, height=90,
                fg_color="#191d4b", text_color="#b783fa", corner_radius=9,
                font=ctk.CTkFont(size=28))
            placeholder.grid(row=0, column=0, rowspan=3,
                             padx=(12, 12), pady=12, sticky="w")
            self.search_result_labels[item["id"]] = placeholder

            title = ctk.CTkLabel(
                frame, text=self._truncate_title(item.get("title", "YouTube-Video"), 100),
                font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
                text_color=TEXT, justify="left", anchor="w", height=52,
                wraplength=245)
            title.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(10, 0))
            HoverTooltip(title, item.get("title", ""))
            favorite_button = regular_button(
                frame, "", lambda video=item: self._toggle_favorite(video),
                fg="#202455", hover="#492668", width=35, height=32)
            favorite_button.grid(row=0, column=2, sticky="ne",
                                 padx=(0, 10), pady=(10, 0))
            self.search_favorite_buttons[item["id"]] = favorite_button
            self._style_favorite_button(favorite_button, item["id"])
            HoverTooltip(favorite_button, "Als Favorit speichern / Favorit entfernen")
            # A small checkbox under the heart preserves the original card
            # height, thumbnail size and both per-video action buttons.
            selected = ctk.BooleanVar(value=item["id"] in self.search_selected_ids)
            self.search_select_vars[item["id"]] = selected
            checkbox = ctk.CTkCheckBox(
                frame, text="", variable=selected, width=25, height=25,
                checkbox_width=21, checkbox_height=21, border_width=2,
                border_color="#8584c5", fg_color="#8b1cf4", hover_color=PURPLE,
                command=lambda video_id=item["id"]: self._toggle_search_selection(video_id))
            checkbox.grid(row=1, column=2, sticky="ne", padx=(0, 11), pady=(1, 0))
            HoverTooltip(checkbox, "Video für Mehrfachdownload auswählen")
            channel = self._truncate_title(item.get("channel", "YouTube"), 37)
            make_label(frame, f"{channel}   •   {item.get('duration', '–')}",
                       11, MUTED, anchor="w").grid(
                           row=1, column=1, sticky="ew", padx=(0, 12), pady=(2, 3))
            actions = ctk.CTkFrame(frame, fg_color="transparent")
            actions.grid(row=2, column=1, sticky="w", pady=(0, 10), padx=(0, 10))
            regular_button(
                actions, "Link übernehmen",
                lambda link=item["url"]: self._use_search_link(link),
                width=119, height=30, font_size=11).pack(side="left", padx=(0, 5))
            regular_button(
                actions, "Starten",
                lambda link=item["url"]: self._use_search_link(link, download=True),
                fg="#711cbd", hover=PURPLE, width=73, height=30,
                font_size=11).pack(side="left")
            self.search_result_cards.append(frame)
            self.search_result_titles.append(title)

        self._search_layout_columns = 0
        self._search_last_wrap = 0
        self._reflow_search_cards()
        self.search_more.grid() if self.search_next_page else self.search_more.grid_remove()
        self._update_search_selection_controls()
        self.search_status.configure(
            text=f"{len(self.search_results)} Ergebnisse für „{term}“. "
                 + ("Weitere Treffer verfügbar." if self.search_next_page else ""),
            text_color=GREEN)
        if results:
            threading.Thread(target=self._fetch_search_thumbnails,
                             args=(self.search_generation, results), daemon=True).start()

    def _fetch_search_thumbnails(self, generation, results):
        # Background requests only: all CTk updates happen in _poll_events.
        for item in results:
            if generation != self.search_generation:
                return
            url = item.get("thumbnail", "")
            if not url:
                continue
            target = THUMBS / f"ytsearch_{item['id']}.jpg"
            try:
                if not target.is_file():
                    response = requests.get(url, timeout=(4, 8),
                                            headers={"User-Agent": "NeonTubeDownloader/1.30"})
                    response.raise_for_status()
                    if len(response.content) > 2_000_000:
                        continue
                    picture = Image.open(BytesIO(response.content)).convert("RGB")
                    picture.thumbnail((480, 270))
                    picture.save(target, quality=87)
                self.ui_events.put(("search_thumbnail", item["id"], (generation, str(target))))
            except Exception:
                pass  # A failed thumbnail must not hide the video result.

    # --------------------------------------------------------- Search multi-select
    def _toggle_search_selection(self, video_id):
        """Update the in-memory selection from one card's checkbox."""
        var = self.search_select_vars.get(video_id)
        if var is None:
            return
        if bool(var.get()):
            self.search_selected_ids.add(video_id)
        else:
            self.search_selected_ids.discard(video_id)
        self._update_search_selection_controls()

    def _select_all_search_results(self):
        """Select all currently loaded results, including paginated pages."""
        self.search_selected_ids.update(
            item["id"] for item in self.search_results if item.get("id"))
        self._update_search_selection_controls()

    def _clear_search_selection(self):
        self.search_selected_ids.clear()
        self._update_search_selection_controls()

    def _update_search_selection_controls(self):
        # Never count selections which aren't part of the current query.
        visible_ids = {item.get("id") for item in self.search_results}
        self.search_selected_ids.intersection_update(visible_ids)
        count = len(self.search_selected_ids)
        self.search_selected_count.configure(text=f"{count} Videos ausgewählt",
                                             text_color=GREEN if count else MUTED)
        self.search_batch_button.configure(text=f"Zur Warteschlange ({count})",
                                           state="normal" if count else "disabled")
        self.search_select_all_button.configure(
            state="normal" if visible_ids else "disabled")
        self.search_clear_button.configure(state="normal" if count else "disabled")
        # Keep checkboxes, selected borders and counter synchronized when the
        # user clicks Select All, Clear, or toggles a single result.
        for video_id, variable in self.search_select_vars.items():
            selected = video_id in self.search_selected_ids
            if bool(variable.get()) != selected:
                variable.set(selected)
            card = self.search_result_frames.get(video_id)
            if card is not None and card.winfo_exists():
                card.configure(border_color="#9c4cf4" if selected else "#42498e")

    def _enqueue_selected_search_results(self):
        """Send exactly the marked, loaded videos through the existing queue."""
        links = selected_video_links(self.search_results, self.search_selected_ids)
        if not links:
            self._update_search_selection_controls()
            return
        # start_downloads() handles all links and honors the existing format,
        # quality, directory and parallel-download settings. Don't make any
        # extra API requests and don't bypass DownloadManager/retry logic.
        self._use_search_link("  ".join(links), download=True)
        self._clear_search_selection()

    def _use_search_link(self, link, download=False):
        # The search action uses the existing validated download queue pathway.
        self.url_text.set(link)
        self._switch_page("download")
        self._url_edited()
        if download:
            self.start_downloads()

    # --------------------------------------------------------- Local favorites
    def _style_favorite_button(self, button, video_id):
        saved = self.favorites.has(video_id)
        button.configure(fg_color="#472156" if saved else "#202455")
        set_button_icon(button, "favorite-filled" if saved else "favorite",
                        size=17, color="#ff8fcc" if saved else "#d4c3ff")

    def _refresh_search_favorite_buttons(self):
        for video_id, button in tuple(self.search_favorite_buttons.items()):
            if button.winfo_exists():
                self._style_favorite_button(button, video_id)

    def _toggle_favorite(self, video):
        try:
            if self.favorites.has(video["id"]):
                self.favorites.remove(video["id"])
            else:
                self.favorites.add(video)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Favoriten", f"Favorit konnte nicht gespeichert werden:\n{exc}")
            return
        self._refresh_search_favorite_buttons()
        if self.active_page == "favorites":
            self._render_favorites()

    def _remove_favorite(self, video_id):
        try:
            self.favorites.remove(video_id)
        except OSError as exc:
            messagebox.showerror("Favoriten", f"Favorit konnte nicht entfernt werden:\n{exc}")
            return
        self._refresh_search_favorite_buttons()
        self._render_favorites()

    def _build_favorites_page(self):
        page = self.favorites_page
        page.grid_columnconfigure(0, weight=1)
        make_label(page, "Favoriten", 30, TEXT, True).grid(
            row=0, column=0, sticky="w", pady=(23, 6))
        make_label(page, "Gemerkte Videos jederzeit ohne erneute YouTube-Suche aufrufen.",
                   13, MUTED).grid(row=1, column=0, sticky="w", pady=(0, 13))
        self.favorites_status = make_label(page, "", 12, GREEN, anchor="w")
        self.favorites_status.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.favorites_list = ctk.CTkFrame(page, fg_color="transparent")
        self.favorites_list.grid(row=3, column=0, sticky="ew")
        self.favorites_list.bind("<Configure>", self._favorites_list_resized, add="+")

    def _favorites_list_resized(self, event=None):
        if self.favorite_result_cards:
            self._reflow_favorites(getattr(event, "width", None))

    def _reflow_favorites(self, width=None):
        width = max(1, int(width or self.favorites_list.winfo_width()))
        if width < 100:
            width = max(width, self.favorites_page.winfo_width() - 18)
        cols = self._search_grid_columns(width)
        card_width = max(250, (width - cols * 12) // cols)
        wrap = max(158, card_width - 205)
        if (cols, wrap) == (self._favorite_layout_columns, self._favorite_last_wrap):
            return
        self._favorite_layout_columns, self._favorite_last_wrap = cols, wrap
        for col in range(3):
            self.favorites_list.grid_columnconfigure(
                col, weight=1 if col < cols else 0,
                uniform="favorites" if col < cols else "", minsize=0)
        for idx, frame in enumerate(self.favorite_result_cards):
            frame.grid(row=idx // cols, column=idx % cols,
                       sticky="nsew", padx=(0, 10), pady=6)
            self.favorite_result_titles[idx].configure(wraplength=wrap)

    def _render_favorites(self):
        self.favorite_generation += 1
        generation = self.favorite_generation
        for child in self.favorites_list.winfo_children():
            child.destroy()
        self.favorite_result_cards = []
        self.favorite_result_titles = []
        self.favorite_result_labels = {}
        self._favorite_layout_columns = 0
        self._favorite_last_wrap = 0
        # Newest saved videos first, without changing persistent JSON order.
        items = list(reversed(self.favorites.all()))
        self.favorites_status.configure(
            text=f"{len(items)} gespeicherte Videos" if items else "Noch keine Favoriten gespeichert.",
            text_color=GREEN if items else MUTED)
        if not items:
            make_label(self.favorites_list,
                       "Klicke in der YouTube-Suche auf das Herz neben einem Video.",
                       14, MUTED).grid(row=0, column=0, sticky="w", pady=(20, 14))
            regular_button(self.favorites_list, "Zur YouTube-Suche",
                           lambda: self._switch_page("search"),
                           fg="#711cbd", hover=PURPLE, width=185, height=38).grid(
                               row=1, column=0, sticky="w")
            return
        for item in items:
            frame = ctk.CTkFrame(self.favorites_list, fg_color="#101743",
                                 border_width=1, border_color="#42498e", corner_radius=14)
            frame.grid_columnconfigure(1, weight=1)
            label = ctk.CTkLabel(
                frame, text="▶", width=160, height=90, fg_color="#191d4b",
                text_color="#b783fa", corner_radius=9,
                font=ctk.CTkFont(size=28))
            label.grid(row=0, column=0, rowspan=3,
                       padx=(12, 12), pady=12, sticky="w")
            self.favorite_result_labels[item["id"]] = label
            title = ctk.CTkLabel(
                frame, text=self._truncate_title(item["title"], 100),
                font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
                text_color=TEXT, justify="left", anchor="w", height=52,
                wraplength=245)
            title.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(10, 0))
            HoverTooltip(title, item["title"])
            remove_button = regular_button(
                frame, "", lambda vid=item["id"]: self._remove_favorite(vid),
                fg="#472156", hover="#612c6d", width=35, height=32)
            set_button_icon(remove_button, "favorite-filled", size=17, color="#ff8fcc")
            HoverTooltip(remove_button, "Aus Favoriten entfernen")
            remove_button.grid(row=0, column=2, sticky="ne", padx=(0, 10), pady=(10, 0))
            channel = self._truncate_title(item["channel"], 37)
            make_label(frame, f"{channel}   •   {item['duration']}", 11,
                       MUTED, anchor="w").grid(
                           row=1, column=1, sticky="ew", padx=(0, 12), pady=(2, 3))
            actions = ctk.CTkFrame(frame, fg_color="transparent")
            actions.grid(row=2, column=1, sticky="w", pady=(0, 10), padx=(0, 10))
            regular_button(
                actions, "Link übernehmen",
                lambda link=item["url"]: self._use_search_link(link),
                width=119, height=30, font_size=11).pack(side="left", padx=(0, 5))
            regular_button(
                actions, "Starten",
                lambda link=item["url"]: self._use_search_link(link, download=True),
                fg="#711cbd", hover=PURPLE, width=73, height=30,
                font_size=11).pack(side="left")
            self.favorite_result_cards.append(frame)
            self.favorite_result_titles.append(title)
        self._reflow_favorites()
        threading.Thread(target=self._fetch_favorite_thumbnails,
                         args=(generation, items), daemon=True).start()

    def _fetch_favorite_thumbnails(self, generation, items):
        """Load cached thumbnails first; network never blocks the GUI thread."""
        for item in items:
            if generation != self.favorite_generation:
                return
            video_id = item["id"]
            target = THUMBS / f"ytsearch_{video_id}.jpg"
            try:
                if not target.is_file():
                    url = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
                    response = requests.get(url, timeout=(4, 8),
                                            headers={"User-Agent": "NeonTubeDownloader/1.31"})
                    response.raise_for_status()
                    if len(response.content) > 2_000_000:
                        continue
                    picture = Image.open(BytesIO(response.content)).convert("RGB")
                    picture.thumbnail((480, 270))
                    picture.save(target, quality=87)
                self.ui_events.put(("favorite_thumbnail", video_id, (generation, str(target))))
            except Exception:
                continue

    def panel(self, parent, height, row, bottom=14, *, accent="violet"):
        panel = NeonGlassPanel(parent, height=height)
        # Vary the single native border tint without another drawing layer.
        if accent != "violet":
            panel.configure(border_color={"blue": "#42639d", "pink": "#70458e"}.get(accent, "#4a4d92"))
        panel.grid(row=row, column=0, sticky="ew", pady=(0, bottom))
        panel.grid_propagate(False)
        return panel

    def _build_options(self, parent):
        p = self.panel(parent, 234, 0, 16, accent="pink")
        top = ctk.CTkFrame(p, height=43, fg_color="transparent")
        top.place(x=12, y=13, relwidth=.966)
        top.grid_columnconfigure(0, weight=1)
        top.grid_columnconfigure(1, weight=1)
        self.video_btn = NeonSelectionButton(
            top, "Video (MP4)", lambda: self._set_mode("Video (MP4)"),
            icon="video", width=177, height=42, font_size=13, centered=True)
        self.audio_btn = NeonSelectionButton(
            top, "Nur Audio (MP3)", lambda: self._set_mode("Nur Audio (MP3)"),
            icon="music", width=176, height=42, font_size=13, centered=True)
        self.video_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.audio_btn.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self.playlist_box = ctk.CTkCheckBox(
            p, text="Playlist herunterladen", variable=self.playlist,
            width=154, checkbox_width=17, checkbox_height=17,
            fg_color=PURPLE, hover_color=PURPLE,
            font=ctk.CTkFont(family=FONT, size=12), text_color=TEXT)
        self.playlist_box.place(relx=.72, y=25)
        # On smaller widths, right playlist overlaps tabs; reserve space with
        # appropriately sized column frame.
        top.place(relwidth=.65)

        fields = ctk.CTkFrame(p, fg_color="transparent", height=68)
        fields.place(x=12, y=80, relwidth=.954)
        fields.grid_columnconfigure(0, weight=33, uniform="fields")
        fields.grid_columnconfigure(1, weight=28, uniform="fields")
        fields.grid_columnconfigure(2, weight=39, uniform="fields")
        for col, text in enumerate(("Qualität", "Audioformat", "Speicherort")):
            make_label(fields, text, 12, TEXT, True, anchor="w").grid(
                row=0, column=col, sticky="ew", padx=(3, 7), pady=(0, 4))
        self.quality_menu = ctk.CTkOptionMenu(
            fields, values=["Beste Qualität", "4K (2160p)", "1440p", "1080p",
                            "720p", "480p", "360p"], variable=self.quality,
            fg_color="#111b50", button_color="#172257",
            button_hover_color="#272b72", text_color=TEXT,
            corner_radius=9, height=36,
            font=ctk.CTkFont(family=FONT, size=12))
        self.quality_menu.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self.audio_menu = ctk.CTkOptionMenu(
            fields, values=["MP3", "M4A", "WAV"], variable=self.audio_format,
            fg_color="#111b50", button_color="#172257",
            button_hover_color="#272b72", corner_radius=10,
            height=36, font=ctk.CTkFont(family=FONT, size=12))
        self.audio_menu.grid(row=1, column=1, sticky="ew", padx=(0, 8))
        folder = ctk.CTkFrame(fields, fg_color="#131d50", corner_radius=10, height=36)
        folder.grid(row=1, column=2, sticky="ew")
        folder.grid_propagate(False)
        folder.grid_columnconfigure(0, weight=1)
        self.folder_label = make_label(folder, self._truncate(self.output_dir.get(), 29), 11,
                                       "#dce1ff", anchor="w")
        self.folder_label.grid(row=0, column=0, sticky="ew", padx=7, pady=4)
        regular_button(folder, "▱  Durchsuchen", self.select_folder,
                       width=93, height=32, font_size=11).grid(
            row=0, column=1, padx=1, pady=2)
        self.folder_label.bind("<Button-1>", lambda _e: self.select_folder())
        controls = ctk.CTkFrame(p, fg_color="transparent", height=53)
        controls.place(x=12, y=164, relwidth=.954)
        controls.grid_columnconfigure(0, weight=5)
        controls.grid_columnconfigure(1, weight=2)
        controls.grid_columnconfigure(2, weight=2)
        self.start_button = GradientButton(controls, "Download starten",
                                           self.start_downloads, height=52, font_size=15)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        self.pause_button = regular_button(controls, "Pausieren",
                                            self.pause_selected,
                                            width=109, height=51, font_size=12,
                                            icon_kind="pause")
        self.pause_button.grid(row=0, column=1, sticky="ew", padx=(7, 7))
        self.cancel_button = regular_button(controls, "Abbrechen",
                                             self.cancel_selected,
                                             width=109, height=51, font_size=12,
                                             icon_kind="cancel")
        self.cancel_button.grid(row=0, column=2, sticky="ew", padx=(7, 0))
        self._set_mode(self.mode.get())

    def _set_mode(self, mode):
        self.mode.set(mode)
        if hasattr(self, "video_btn"):
            self.video_btn.set_selected(mode == "Video (MP4)")
            self.audio_btn.set_selected(mode == "Nur Audio (MP3)")
            self.quality_menu.configure(state="normal" if mode == "Video (MP4)" else "disabled")

    def _build_preview(self, parent):
        p = self.panel(parent, 133, 1, 15, accent="blue")
        self.preview_backplate = ctk.CTkFrame(
            p, width=166, height=106, corner_radius=13,
            fg_color="#161e55", border_color="#493c9c", border_width=1)
        self.preview_backplate.place(x=17, y=14)
        self.preview_image = ctk.CTkLabel(p, text="", width=160, height=100)
        self.preview_image.place(x=20, y=17)
        self.preview_photo = self._thumb_image("", (160, 100))
        self.preview_image.configure(image=self.preview_photo)
        self.preview_title = make_label(p, "Noch kein Video ausgewählt", 18,
                                        TEXT, True, anchor="w")
        # Reserve the right edge for the HD/quality badge.  The visible title
        # is fitted to the label's measured width whenever the panel resizes.
        self.preview_title.place(x=200, y=22, relwidth=.60)
        self._preview_full_title = "Noch kein Video ausgewählt"
        self.preview_title.bind("<Configure>", self._layout_preview_title)
        self.preview_channel = make_label(p, "Füge einen YouTube-Link ein.", 15,
                                          "#d9e0ff", anchor="w")
        self.preview_channel.place(x=201, y=53, relwidth=.65)
        self.preview_details = make_label(p, "Vorschau und Videoinformationen", 14,
                                          MUTED, anchor="w")
        self.preview_details.place(x=201, y=82, relwidth=.65)
        self.preview_quality = ctk.CTkLabel(
            p, text="HD", font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
            width=43, height=28, corner_radius=10, fg_color="#26154f",
            text_color="#e5a4ff")
        self.preview_quality.place(relx=.97, y=21, anchor="ne")
        self.preview_duration = make_label(p, "--:--", 11, "#b8c5ff")
        self.preview_duration.place(relx=.96, y=69, anchor="e")

    def _build_progress(self, parent):
        p = self.panel(parent, 192, 2, 0)
        small_icon_label(p, "progress", 19, "#cbbcff").place(x=20, y=17)
        make_label(p, "Fortschritt", 17, TEXT, True).place(x=48, y=15)
        regular_button(p, "Log", lambda: self._switch_page("log"), width=52,
                       height=31, font_size=12).place(relx=.97, y=16, anchor="ne")
        self.progress_bar = NeonGradientProgress(p, height=23)
        self.progress_bar.place(x=22, y=57, relwidth=.78)
        self.progress_bar.set(0)
        self.progress_percent = make_label(p, "0%", 19, TEXT, True)
        self.progress_percent.place(relx=.9, y=53)
        stats = ctk.CTkFrame(p, fg_color="transparent", height=74)
        stats.place(x=17, y=105, relwidth=.96)
        stats.grid_rowconfigure(0, weight=1)
        for col in range(3):
            stats.grid_columnconfigure(col, weight=1, uniform="stats")
        self.stats_speed = self._stat(stats, 0, "Aktuelle Geschwindigkeit", "0 MB/s", "speed")
        self.stats_eta = self._stat(stats, 1, "Restzeit", "--:--:--", "clock")
        self.stats_size = self._stat(stats, 2, "Heruntergeladen", "0 MB / 0 MB", "storage")

    def _stat(self, parent, col, name, value, symbol="progress"):
        # Consistent vector icons rather than special Unicode glyphs that may
        # appear as boxes on Windows. Native CTk cards retain proper layering.
        frame = ctk.CTkFrame(parent, fg_color="#111944", corner_radius=11,
                             border_width=1, border_color="#34437e", height=65)
        frame.grid(row=0, column=col, sticky="nsew", padx=4, pady=3)
        small_icon_label(frame, symbol, 16, "#b4acff").place(x=10, y=10)
        make_label(frame, name, 12, MUTED, anchor="w", height=20).place(
            x=33, y=8, relwidth=.83)
        label = make_label(frame, value, 16, TEXT, anchor="w", height=23)
        label.place(x=10, y=34, relwidth=.90)
        return label

    def _build_queue(self, parent):
        p = self.panel(parent, QUEUE_PANEL_HEIGHT, 0, 13, accent="blue")
        self.queue_card = p
        small_icon_label(p, "queue", 18, "#cbbcff").place(x=14, y=12)
        make_label(p, "Download-Warteschlange", 17, TEXT, True).place(x=40, y=10)
        self.queue_count = ctk.CTkLabel(
            p, text="0", width=27, height=23, corner_radius=10,
            fg_color="#271648", text_color="#e8a2ff",
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"))
        self.queue_count.place(relx=.975, y=7, anchor="ne")
        self.queue_scroll = ctk.CTkScrollableFrame(
            p, fg_color="transparent", scrollbar_button_color="#24215d",
            corner_radius=0, height=QUEUE_LIST_HEIGHT)
        self.queue_scroll.place(x=9, y=QUEUE_LIST_TOP, relwidth=.97)
        self.queue_scroll.grid_columnconfigure(0, weight=1)
        regular_button(p, "Auswahl entfernen", self.remove_selected,
                       width=128, height=QUEUE_FOOTER_HEIGHT, font_size=11).place(x=11, y=QUEUE_FOOTER_TOP)
        regular_button(p, "Ordner öffnen", self.open_selected_download_folder,
                       width=111, height=QUEUE_FOOTER_HEIGHT, font_size=11).place(relx=.54, y=QUEUE_FOOTER_TOP, anchor="n")
        regular_button(p, "Leeren", self.clear_queue,
                       width=65, height=QUEUE_FOOTER_HEIGHT, font_size=11).place(relx=.96, y=QUEUE_FOOTER_TOP, anchor="ne")

    def _build_history_summary(self, parent):
        p = self.panel(parent, HISTORY_PANEL_HEIGHT, 1, 13)
        small_icon_label(p, "history", 18, "#cbbcff").place(x=14, y=13)
        make_label(p, "Verlauf", 17, TEXT, True).place(x=40, y=11)
        # A small counter, as in the download queue, shows that entries are
        # still stored even when the current queue is empty.
        self.history_count = ctk.CTkLabel(
            p, text="0", width=27, height=23, corner_radius=10,
            fg_color="#271648", text_color="#e8a2ff",
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"))
        self.history_count.place(x=116, y=7)
        regular_button(p, "Alle anzeigen", lambda: self._switch_page("history"),
                       fg="transparent", hover="#211b61", width=103,
                       height=28, font_size=11).place(relx=.98, y=7, anchor="ne")
        self.history_preview_scroll = ctk.CTkScrollableFrame(
            p, fg_color="transparent", corner_radius=0, height=HISTORY_LIST_HEIGHT,
            scrollbar_button_color="#22205c")
        self.history_preview_scroll.place(x=9, y=43, relwidth=.97)
        self.history_preview_scroll.grid_columnconfigure(0, weight=1)

    # ----------------------------------------------------- Clipboard watcher
    def _clipboard_text_safely(self):
        """Read clipboard only in the Tk UI thread; ignore non-text contents."""
        try:
            text = self.clipboard_get()
            return text if isinstance(text, str) and len(text) <= 8192 else ""
        except Exception:  # No text selection/clipboard (TclError, OS denial)
            return ""

    def _start_clipboard_watch(self):
        # Seed current clipboard to avoid prompting for an old, stale copy.
        self._clipboard_watcher = ClipboardLinkWatcher(self._clipboard_text_safely())
        self._clipboard_watch_after = self.after(1400, self._clipboard_watch_tick)

    def _clipboard_watch_tick(self):
        self._clipboard_watch_after = None
        try:
            if self._clipboard_watcher is None:
                return
            current = self._clipboard_text_safely()
            # While a browser or another app has focus, remember only the new
            # valid URLs and defer the offer until NeonTube becomes active.
            foreground = self.state() != "iconic" and self.focus_get() is not None
            found = self._clipboard_watcher.observe(current, foreground=foreground)
            if found:
                lines = "\n".join(f"• {url[:100]}" for url in found[:3])
                extra = f"\n… und {len(found)-3} weitere" if len(found) > 3 else ""
                question = (
                    f"{len(found)} YouTube-Link(s) in der Zwischenablage erkannt:\n\n"
                    f"{lines}{extra}\n\n"
                    "Möchtest du diese Links in das Eingabefeld übernehmen?\n"
                    "Es wird kein Download automatisch gestartet."
                )
                if messagebox.askyesno("YouTube-Link erkannt", question, parent=self):
                    self._switch_page("download")
                    combined = append_unique_links(self.url_input.get(), found)
                    if combined != self.url_input.get():
                        self.url_text.set(combined)
                    self.url_input.focus_set()
        except Exception:
            # Clipboard access and window-focus behavior vary across Windows
            # versions. An issue here must not affect downloads or other UI.
            pass
        finally:
            try:
                if self.winfo_exists():
                    self._clipboard_watch_after = self.after(1400, self._clipboard_watch_tick)
            except Exception:
                pass

    # --------------------------------------------------------- Queue / preview
    def paste_link(self):
        try:
            raw_content = self.clipboard_get()
            content = raw_content.strip()
        except Exception:
            messagebox.showinfo("Zwischenablage", "In der Zwischenablage ist kein Text.")
            return
        if not content:
            return
        # The user already chose manual paste, so do not offer the same
        # clipboard contents again in a second automatic prompt.
        if self._clipboard_watcher is not None:
            self._clipboard_watcher.dismiss(raw_content)
        # Tk Entry is single-line: preserve all pasted links using spaces.
        content = re.sub(r"\s+", " ", content)
        old = self.url_input.get().strip()
        self.url_input.delete(0, "end")
        self.url_input.insert(0, (old + "  " + content).strip() if old else content)
        self._url_edited()

    def _update_url_hint(self):
        """Display a stable placeholder even after paste/delete/focus changes."""
        if self.url_text.get():
            self.url_hint.place_forget()
        else:
            self.url_hint.place(x=8, rely=.5, anchor="w")

    def _on_url_text_changed(self, *_args):
        self._update_url_hint()
        self._url_edited()

    def _url_edited(self, _event=None):
        if self._preview_after:
            self.after_cancel(self._preview_after)
        self._preview_after = self.after(950, self._fetch_link_preview)

    def _parse_links(self, text):
        links = re.findall(r"https?://[^\s,;<>\"']+", text)
        return list(dict.fromkeys(x.rstrip(".)]") for x in links))

    def _fetch_link_preview(self):
        self._preview_after = None
        links = self._parse_links(self.url_input.get())
        if not links:
            return
        self.metadata_counter += 1
        seq = self.metadata_counter
        self._set_preview_title("Videoinformationen werden geladen …")
        threading.Thread(target=self._metadata_worker,
                         args=(links[0], "preview", seq), daemon=True).start()

    def _metadata_worker(self, url, job_id, seq=0):
        try:
            meta = None
            if self.youtube_api_key and video_id_from_url(url):
                try:
                    meta = get_video_metadata(url, self.youtube_api_key)
                except YouTubeAPIError:
                    # Search/metadata API must never prevent a legitimate yt-dlp download.
                    meta = None
            if meta is None:
                if yt_dlp is None:
                    raise RuntimeError("Ohne API-Daten ist yt-dlp für die Vorschau erforderlich.")
                opts = {"quiet": True, "skip_download": True, "no_warnings": True,
                        "noplaylist": True, "extract_flat": False, "socket_timeout": 20,
                        "retries": 5, "extractor_retries": 4}
                opts.update(javascript_runtime_config())
                cookie = self.config_data.get("cookiefile", "")
                if cookie and Path(cookie).is_file():
                    opts["cookiefile"] = cookie
                with yt_dlp.YoutubeDL(opts) as ydl:
                    result = ydl.extract_info(url, download=False)
                    if not result:
                        raise RuntimeError("Keine Videoinformationen gefunden")
                    meta = {
                        "title": result.get("title", "YouTube-Video"),
                        "uploader": result.get("uploader") or result.get("channel") or "YouTube",
                        "duration": result.get("duration") or 0,
                        "thumbnail": result.get("thumbnail", ""),
                        "view_count": result.get("view_count"),
                    }
            local_thumbnail = ""
            if meta["thumbnail"]:
                try:
                    response = requests.get(meta["thumbnail"], timeout=10,
                                            headers={"User-Agent": "Mozilla/5.0"})
                    response.raise_for_status()
                    picture = Image.open(BytesIO(response.content)).convert("RGB")
                    picture.thumbnail((800, 600))
                    slug = re.sub(r"[^a-zA-Z0-9]", "_", job_id)
                    target = THUMBS / f"{slug}.jpg"
                    picture.save(target, quality=85)
                    local_thumbnail = str(target)
                except Exception:
                    pass
            meta["thumbnail_path"] = local_thumbnail
            self.ui_events.put(("metadata", job_id, (seq, meta)))
        except Exception as exc:
            self.ui_events.put(("metadata_error", job_id, (seq, str(exc))))

    def select_folder(self):
        folder = filedialog.askdirectory(title="Download-Ordner auswählen",
                                          initialdir=self.output_dir.get())
        if folder:
            self.output_dir.set(folder)
            self.folder_label.configure(text=self._truncate(folder, 29))
            self.config_data["download_dir"] = folder
            save_json(CONFIG_FILE, self.config_data)

    @staticmethod
    def _truncate(s, n=42):
        """Keep the end of a filesystem path (used for folder labels)."""
        s = str(s or "")
        return s if len(s) <= n else "…" + s[-n+1:]

    @staticmethod
    def _truncate_title(s, n=42):
        """Keep the beginning of a video title so artists/names stay visible."""
        s = str(s or "")
        if n <= 1:
            return "…" if s else ""
        return s if len(s) <= n else s[:n-1].rstrip() + "…"

    def start_downloads(self):
        urls = self._parse_links(self.url_input.get())
        if not urls:
            messagebox.showwarning("Kein YouTube-Link", "Bitte mindestens einen gültigen http(s)-Link einfügen.")
            self.url_input.focus_set()
            return
        if yt_dlp is None:
            messagebox.showerror("yt-dlp fehlt", "Bitte das Programm über start_windows.bat installieren.")
            return
        directory = self.output_dir.get().strip()
        try:
            Path(directory).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Speicherort", f"Ordner nicht verfügbar:\n{exc}")
            return

        # This check is offline and applies equally to pasted links, search
        # results, multiple selections and favorite cards. It checks active
        # jobs first; a completed download only counts if its file still
        # exists. Never change or delete the original file.
        from duplicate_guard import build_download_plan
        plan = build_download_plan(
            urls, mode=self.mode.get(), audio_format=self.audio_format.get(),
            playlist=self.playlist.get(),
            jobs=list(getattr(self.manager, "jobs", {}).values()),
            history=getattr(self, "history", []))
        repeat_existing = False
        if plan.downloaded:
            names = "\n".join(f"• {hit.title[:66]}" for hit in plan.downloaded[:4])
            extra = (f"\n… und {len(plan.downloaded)-4} weitere" if len(plan.downloaded) > 4 else "")
            repeat_existing = messagebox.askyesno(
                "Bereits heruntergeladen",
                f"{len(plan.downloaded)} Video(s) sind bereits als Datei gespeichert:\n\n"
                f"{names}{extra}\n\n"
                "Möchtest du sie trotzdem erneut zur Warteschlange hinzufügen?\n"
                "Bereits gespeicherte Dateien werden nicht automatisch überschrieben.")
        accepted_urls = plan.accepted_urls(repeat_existing=repeat_existing)
        skipped_count = len(plan.pending) + len(plan.repeated) + (0 if repeat_existing else len(plan.downloaded))
        if skipped_count:
            self._log_event("info", f"Duplikatschutz: {skipped_count} doppelte(s) Video(s) nicht eingereiht."
                            if not repeat_existing else
                            f"Duplikatschutz: {skipped_count} bereits wartende oder wiederholte Links übersprungen.")
        if not accepted_urls:
            if plan.pending or plan.repeated or plan.downloaded:
                messagebox.showinfo(
                    "Doppelte Downloads",
                    "Keine neuen Downloads eingereiht.\n"
                    f"Bereits in Warteschlange: {len(plan.pending)}\n"
                    f"Bereits heruntergeladen: {len(plan.downloaded)}\n"
                    f"In der Eingabe doppelt: {len(plan.repeated)}")
            return

        for link in accepted_urls:
            host = urlparse(link).hostname or ""
            if not host:
                continue
            job = DownloadJob(
                url=link, output_dir=directory, mode=self.mode.get(),
                quality=self.quality.get(), audio_format=self.audio_format.get(),
                playlist=self.playlist.get(), title="Video wird vorbereitet …",
                folder_organization=getattr(self, "config_data", {}).get(
                    "folder_organization", "Keine (wie bisher)"))
            self.current_job_id = job.id
            self._log_event(
                "download", f"Zur Warteschlange hinzugefügt: {job.mode}, "
                f"{job.quality if job.mode == 'Video (MP4)' else job.audio_format}.",
                job.id)
            self.manager.add(job)
            threading.Thread(target=self._metadata_worker,
                             args=(link, job.id), daemon=True).start()
        self.url_input.delete(0, "end")
        # The StringVar observer restores the visible hint immediately.
        # Move focus back to the window so the next link can be pasted cleanly.
        self.after_idle(self.focus_set)
        self._switch_page("download")
        self._refresh_progress()
        if plan.pending or plan.repeated:
            messagebox.showinfo(
                "Duplikatschutz aktiv",
                f"{len(accepted_urls)} Video(s) eingereiht.\n"
                f"{len(plan.pending)} bereits wartende und "
                f"{len(plan.repeated)} doppelte Links übersprungen.")

    def _thumb_image(self, path, size=(64, 58)):
        key = (path, size)
        if key not in self.thumbnail_cache:
            source = Path(path) if path and Path(path).is_file() else ASSETS / "preview_mountain.png"
            try:
                picture = Image.open(source).convert("RGBA")
                width, height = picture.size
                aspect = size[0] / size[1]
                if width / height > aspect:
                    new_width = int(height * aspect)
                    picture = picture.crop(((width-new_width)//2, 0, (width+new_width)//2, height))
                else:
                    new_height = int(width / aspect)
                    picture = picture.crop((0, (height-new_height)//2, width, (height+new_height)//2))
                output = picture.resize(size, Image.Resampling.LANCZOS)
                clip = Image.new("L", size, 0)
                ImageDraw.Draw(clip).rounded_rectangle(
                    (0, 0, size[0] - 1, size[1] - 1),
                    radius=max(6, min(size) // 8), fill=255)
                output.putalpha(clip)
                self.thumbnail_cache[key] = ctk.CTkImage(
                    light_image=output, dark_image=output, size=size)
            except Exception:
                self.thumbnail_cache[key] = img("preview_mountain.png", size)
        return self.thumbnail_cache[key]

    def _empty_state(self, parent, symbol, title, subtitle, *, top=35, grid=False):
        # Real data only: calm, decorative empty states, never fake queue jobs.
        content = ctk.CTkFrame(
            parent, fg_color="#111947", corner_radius=16,
            border_width=1, border_color="#384a92")
        if grid:
            content.grid(row=0, column=0, sticky="ew", padx=8, pady=(top, 3))
        else:
            content.pack(fill="x", padx=8, pady=(top, 3))
        emblem = ctk.CTkFrame(content, fg_color="#29175e", corner_radius=22,
                              width=43, height=43, border_color="#6847be", border_width=1)
        emblem.pack(pady=(13, 7))
        emblem.pack_propagate(False)
        small_icon_label(emblem, symbol, 23, "#e6b8ff").pack(expand=True)
        make_label(content, title, 15, TEXT, True).pack(pady=(0, 5))
        make_label(content, subtitle, 13, MUTED,
                   justify="center").pack(padx=8, pady=(0, 14))
        return content

    def _reset_queue_scroll(self):
        """New queue membership starts at row one, not a stale scroll offset.

        CTkScrollableFrame wraps its contents in a canvas. This is deliberately
        guarded for older CustomTkinter versions and for already closed views.
        """
        try:
            canvas = getattr(self.queue_scroll, "_parent_canvas", None)
            if canvas is not None and canvas.winfo_exists():
                canvas.yview_moveto(0.0)
        except Exception:
            pass

    def _render_queue(self):
        jobs = list(self.manager.jobs.values())
        new_ids = tuple(job.id for job in jobs)
        membership_changed = new_ids != self._queue_rendered_ids
        self._queue_rendered_ids = new_ids
        for widget in self.queue_scroll.winfo_children():
            widget.destroy()
        self.queue_widgets.clear()
        self.queue_count.configure(text=str(len(jobs)))
        if membership_changed:
            # Wait for the scroll canvas to measure the new rows before moving.
            self.after(60, self._reset_queue_scroll)
        if not jobs:
            self._empty_state(self.queue_scroll, "download", "Deine Warteschlange ist leer",
                              "Füge oben einen YouTube-Link ein,\num deinen ersten Download zu starten.",
                              top=30, grid=True)
            return
        for i, job in enumerate(jobs):
            selected = job.id == self.current_job_id
            # Three information levels, as in the reference design: a title,
            # format/size metadata, and live progress plus a distinct status.
            frame = ctk.CTkFrame(
                self.queue_scroll, fg_color="#171348" if selected else "#101641",
                border_width=1,
                border_color="#9b37ed" if selected else "#303c80",
                corner_radius=11, height=QUEUE_CARD_HEIGHT)
            frame.grid(row=i, column=0, sticky="ew", pady=(0, QUEUE_ROW_GAP), padx=(1, 1))
            frame.grid_propagate(False)
            frame.grid_columnconfigure(1, weight=1)
            picture = ctk.CTkLabel(
                frame, text="", width=64, height=58,
                image=self._thumb_image(job.thumbnail_path, (64, 58)))
            picture.grid(row=0, column=0, rowspan=4, padx=(5, 7), pady=5)
            title = make_label(frame, self._truncate_title(job.title, 22), 13,
                               TEXT, True, anchor="w", width=1, height=18)
            title.grid(row=0, column=1, sticky="ew", pady=(3, 0))
            title.bind("<Configure>",
                       lambda _event, w=title, j=job: self._fit_title_label(w, j.title, 32))
            HoverTooltip(title, job.title)
            meta = make_label(frame, compact_job_metadata(job), 12, "#c0caff",
                              anchor="w", width=1, height=15)
            meta.grid(row=1, column=1, sticky="w", pady=(0, 0))
            bar = ctk.CTkProgressBar(
                frame, height=8, corner_radius=5, width=90,
                fg_color="#20255e", progress_color="#b72cff")
            bar.grid(row=2, column=1, sticky="ew", padx=(0, 5), pady=(2, 0))
            bar.set(job.progress)
            detail = make_label(frame, self._job_short_status(job), 11,
                                GREEN if job.status == "finished" else MUTED,
                                anchor="w", width=1, height=17)
            detail.grid(row=3, column=1, sticky="w", pady=(0, 3))
            buttons = ctk.CTkFrame(frame, fg_color="transparent")
            buttons.grid(row=0, column=2, rowspan=4, padx=(3, 4), pady=5)
            actions = (("↑", lambda k=job.id: self.manager.move(k, -1)),
                       ("↓", lambda k=job.id: self.manager.move(k, 1)),
                       ("✓" if job.status == "finished" else
                        "▶" if job.status in ("paused", "failed") else "Ⅱ",
                        lambda k=job.id: self._toggle_job_pause(k)),
                       ("×", lambda k=job.id: self.manager.remove(k)))
            for index, (symbol, action) in enumerate(actions):
                button = regular_button(buttons, symbol, action, width=29,
                                        height=26, font_size=14)
                if index == 2 and job.status in ("finished", "cancelled"):
                    button.configure(state="disabled")
                button.grid(row=index // 2, column=index % 2, padx=2, pady=2)
            for widget in (frame, picture, title, meta, bar, detail):
                widget.bind("<Button-1>", lambda _e, k=job.id: self.select_job(k))
                widget.bind("<Double-Button-1>",
                            lambda _e, k=job.id: self.open_job_download_folder(k))
            self.queue_widgets[job.id] = {
                "bar": bar, "title": title, "meta": meta, "detail": detail,
                "frame": frame, "shown_title": job.title}
            self.after_idle(lambda w=title, j=job: self._fit_if_visible(w, j.title, 32))

    def _fit_title_label(self, label, text, fallback_chars=32):
        """Fit the visible prefix to the *available pixels*, not a fixed char count.

        CTkLabel width changes with display scaling and when the window is
        resized. Only update when the displayed string actually changes.
        """
        text = str(text or "")
        available = label.winfo_width() - 8
        if available < 60:
            # Tk has not yet laid out the card: keep its small initial label.
            return
        try:
            fitted = ellipsize_to_width(text, available, label.cget("font").measure)
        except (AttributeError, TypeError):
            fitted = self._truncate_title(text, fallback_chars)
        if label.cget("text") != fitted:
            label.configure(text=fitted)

    def _fit_if_visible(self, label, title, fallback_chars=32):
        """Idle callbacks may outlive a rebuilt download card."""
        try:
            if label.winfo_exists():
                self._fit_title_label(label, title, fallback_chars)
        except Exception:
            pass

    def _job_short_status(self, job):
        if job.status in ("downloading", "processing", "pausing"):
            if job.status == "processing":
                return "Konvertierung / Verarbeitung …"
            if job.status == "pausing":
                return "Pausieren …"
            return f"{bytes_text(job.speed)}/s · {int(job.progress*100)}% · {bytes_text(job.downloaded)}"
        if job.status == "retrying":
            return (f"↻ Reparatur {job.retry_attempt}/{MAX_RECOVERY_ATTEMPTS}"
                    f" · {job.retry_wait} s")
        return {"queued": "◷ Wartet …", "paused": "Ⅱ Pausiert",
                "finished": "✓ Abgeschlossen", "failed": "⚠ Fehler – zum Anzeigen auswählen",
                "cancelled": "× Abgebrochen"}.get(job.status, job.status)

    def _update_queue_progress(self):
        for job_id, refs in list(self.queue_widgets.items()):
            job = self.manager.jobs.get(job_id)
            if job:
                try:
                    refs["bar"].set(job.progress)
                    refs["detail"].configure(
                        text=self._job_short_status(job),
                        text_color=GREEN if job.status == "finished" else MUTED)
                    refs["meta"].configure(text=compact_job_metadata(job))
                    if refs.get("shown_title") != job.title:
                        refs["shown_title"] = job.title
                        try:
                            self._fit_title_label(refs["title"], job.title, 32)
                        except (AttributeError, TypeError):
                            refs["title"].configure(text=self._truncate_title(job.title, 32))
                except Exception:
                    pass

    def select_job(self, job_id):
        self.current_job_id = job_id
        # Restyle the existing cards in place instead of rebuilding them.
        # Preserving widget identity also makes double-click actions reliable.
        for key, refs in self.queue_widgets.items():
            selected = key == job_id
            refs["frame"].configure(
                fg_color="#171348" if selected else "#101641",
                border_width=1,
                border_color="#9b37ed" if selected else "#303c80")
        self._refresh_preview()
        self._refresh_progress()

    def _selected_job(self):
        if self.current_job_id in self.manager.jobs:
            return self.manager.jobs[self.current_job_id]
        for job in reversed(list(self.manager.jobs.values())):
            if job.status in ("downloading", "processing", "pausing", "paused", "retrying"):
                return job
        return next(reversed(self.manager.jobs.values()), None) if self.manager.jobs else None

    def _toggle_job_pause(self, job_id):
        job = self.manager.jobs.get(job_id)
        if not job:
            return
        if job.status in ("paused", "failed"):
            self.manager.resume(job_id)
        elif job.status not in ("finished", "cancelled"):
            self.manager.pause(job_id)

    def pause_selected(self):
        job = self._selected_job()
        if job:
            self._toggle_job_pause(job.id)
        else:
            messagebox.showinfo("Pausieren", "Kein Download ausgewählt.")

    def cancel_selected(self):
        job = self._selected_job()
        if job:
            self.manager.cancel(job.id)
        else:
            messagebox.showinfo("Abbrechen", "Kein Download ausgewählt.")

    def remove_selected(self):
        job = self._selected_job()
        if job:
            self.manager.remove(job.id)
            self.current_job_id = ""
            self._refresh_progress()
        else:
            messagebox.showinfo("Warteschlange", "Kein Eintrag ausgewählt.")

    def clear_queue(self):
        if self.manager.jobs and messagebox.askyesno(
                "Warteschlange leeren", "Alle Einträge entfernen und aktive Downloads abbrechen?"):
            self.manager.clear_all()
            self.current_job_id = ""
            self._refresh_progress()

    @staticmethod
    def _record_folder(record):
        """Prefer a job's real completed location to its selected root folder."""
        def get(key):
            return record.get(key, "") if isinstance(record, dict) else getattr(record, key, "")
        base = str(get("output_dir") or "")
        filename = str(get("filename") or "")
        if filename:
            candidate = Path(filename)
            if not candidate.is_absolute() and base:
                candidate = Path(base) / candidate
            if candidate.is_file():
                return str(candidate.parent)
            # During an active transfer the .part file may not yet exist.
            if candidate.parent.is_dir() and candidate.parent != Path(base):
                return str(candidate.parent)
        return base

    def open_job_download_folder(self, job_id):
        """Open the destination of a queue item, regardless of job status."""
        job = self.manager.jobs.get(job_id)
        if job:
            self._open_download_directory(self._record_folder(job))

    def open_selected_download_folder(self):
        """Queue footer action: use the selection or the current save folder."""
        job = self._selected_job()
        self._open_download_directory(self._record_folder(job) if job else self.output_dir.get())

    def _open_download_directory(self, directory):
        if directory and Path(directory).is_dir():
            open_path(directory)
        else:
            messagebox.showinfo("Speicherort", "Dieser Download-Ordner ist nicht mehr vorhanden.")

    def _set_preview_title(self, title):
        self._preview_full_title = str(title or "")
        self._layout_preview_title()

    def _layout_preview_title(self, _event=None):
        """Prevent long video names from being painted under the quality badge."""
        label = self.preview_title
        available = label.winfo_width() - 12
        full = getattr(self, "_preview_full_title", "")
        if available > 60:
            try:
                text = ellipsize_to_width(full, available, label.cget("font").measure)
            except (AttributeError, TypeError):
                text = self._truncate_title(full, 35)
        else:
            text = self._truncate_title(full, 35)
        if label.cget("text") != text:
            label.configure(text=text)

    def _bind_preview_title_tooltip(self, title):
        tooltip = getattr(self, "_preview_title_tooltip", None)
        if tooltip is None:
            tooltip = HoverTooltip(self.preview_title, title)
            self._preview_title_tooltip = tooltip
        else:
            tooltip.text = str(title or "")

    def _refresh_preview(self):
        job = self._selected_job()
        if job:
            self._set_preview_title(self._truncate_title(job.title, 150))
            self.preview_channel.configure(text=self._truncate_title(job.channel, 49))
            self._bind_preview_title_tooltip(job.title)
            self.preview_details.configure(text=f"{job.mode} · {job.quality} · {self._job_short_status(job)}")
            self.preview_duration.configure(text=clock_text(job.duration)[3:])
            self.preview_quality.configure(text=job.quality if job.mode == "Video (MP4)" else job.audio_format)
            self.preview_photo = self._thumb_image(job.thumbnail_path, (160, 100))
            self.preview_image.configure(image=self.preview_photo)
        elif self.current_meta:
            meta = self.current_meta
            self._set_preview_title(self._truncate_title(meta.get("title", "YouTube-Video"), 150))
            self.preview_channel.configure(text=self._truncate_title(meta.get("uploader", "YouTube"), 49))
            self._bind_preview_title_tooltip(meta.get("title", "YouTube-Video"))
            self.preview_details.configure(text=format_view_count(meta.get("view_count")))
            self.preview_duration.configure(text=clock_text(meta.get("duration", 0))[3:])
            self.preview_photo = self._thumb_image(meta.get("thumbnail_path"), (160, 100))
            self.preview_image.configure(image=self.preview_photo)
        else:
            self._bind_preview_title_tooltip("")
            self._set_preview_title("Noch kein Video ausgewählt")
            self.preview_channel.configure(text="Füge einen YouTube-Link ein.")
            self.preview_details.configure(text="Vorschau und Videoinformationen")
            self.preview_photo = self._thumb_image("", (160, 100))
            self.preview_image.configure(image=self.preview_photo)

    def _refresh_progress(self):
        job = self._selected_job()
        if not job:
            self.progress_bar.set(0)
            self.progress_percent.configure(text="0%")
            self.stats_speed.configure(text="0 MB/s")
            self.stats_eta.configure(text="--:--:--")
            self.stats_size.configure(text="0 MB / 0 MB")
            set_button_icon(self.pause_button, "pause", color="#8995c0")
            set_button_icon(self.cancel_button, "cancel", color="#8995c0")
            self.pause_button.configure(text="Pausieren", state="disabled")
            self.cancel_button.configure(state="disabled")
            return
        self.progress_bar.set(job.progress)
        self.progress_percent.configure(text=f"{int(job.progress * 100)}%")
        if job.status == "finished":
            self.stats_speed.configure(text="—")
            self.stats_eta.configure(text="Abgeschlossen")
        elif job.status == "retrying":
            self.stats_speed.configure(text="0 MB/s")
            self.stats_eta.configure(text=f"Neustart in {job.retry_wait} s")
        else:
            self.stats_speed.configure(text=f"{bytes_text(job.speed)}/s")
            self.stats_eta.configure(text=clock_text(job.eta))
        self.stats_size.configure(text=f"{bytes_text(job.downloaded)} / {bytes_text(job.total)}")
        can_resume = job.status in ("paused", "failed")
        done = job.status in ("finished", "cancelled")
        icon_color = "#8995c0" if done else "#dcdfff"
        set_button_icon(self.pause_button, "resume" if can_resume else "pause", color=icon_color)
        set_button_icon(self.cancel_button, "cancel", color=icon_color)
        self.pause_button.configure(text="Fortsetzen" if can_resume else "Pausieren",
                                    state="disabled" if done else "normal")
        self.cancel_button.configure(state="disabled" if done else "normal")

    def _poll_events(self):
        rebuild = False
        progress = False
        history_changed = False
        for _ in range(200):
            try:
                kind, job_id, payload = self.ui_events.get_nowait()
            except queue.Empty:
                break
            if kind == "search_results":
                seq, term, page_token, data = payload
                if seq == self.search_counter:
                    self._display_search_results(term, page_token, data)
            elif kind == "search_error":
                seq, error = payload
                if seq == self.search_counter:
                    self.search_status.configure(text=error, text_color="#ffadbd")
                    self.search_more.grid() if self.search_next_page else self.search_more.grid_remove()
            elif kind == "search_thumbnail":
                generation, thumb_path = payload
                if generation == self.search_generation and job_id in self.search_result_labels:
                    try:
                        photo = self._thumb_image(thumb_path, (160, 90))
                        label = self.search_result_labels[job_id]
                        label.configure(image=photo, text="")
                        label._neon_thumb = photo
                    except (OSError, ValueError):
                        pass
            elif kind == "favorite_thumbnail":
                generation, thumb_path = payload
                if generation == self.favorite_generation and job_id in self.favorite_result_labels:
                    try:
                        photo = self._thumb_image(thumb_path, (160, 90))
                        label = self.favorite_result_labels[job_id]
                        label.configure(image=photo, text="")
                        label._neon_thumb = photo
                    except (OSError, ValueError):
                        pass
            elif kind == "download_retry":
                self._log_event("warning", str(payload), job_id)
            elif kind == "queue_changed":
                rebuild = True
            elif kind == "progress":
                progress = True
            elif kind == "completed":
                rebuild, history_changed = True, True
                job = self.manager.jobs.get(job_id)
                if job:
                    if job.total > 0:
                        self._log_progress_event(job, 100)
                    self._log_event("success", f"Erfolgreich heruntergeladen: {job.title}", job.id)
                    self._log_seen_states[job.id] = "finished"
                    self._add_history(job)
            elif kind == "metadata":
                seq, meta = payload
                if job_id == "preview":
                    if seq == self.metadata_counter:
                        self.current_meta = meta
                        self.current_job_id = ""
                        self._refresh_preview()
                else:
                    job = self.manager.jobs.get(job_id)
                    if job:
                        job.title = meta["title"]
                        job.channel = meta["uploader"]
                        job.duration = int(meta.get("duration") or 0)
                        job.thumbnail_path = meta.get("thumbnail_path", "")
                        job.thumbnail_url = meta.get("thumbnail", "")
                        self._log_event("info", f"Videoinformationen geladen: {job.title}", job.id)
                        rebuild = True
            elif kind == "metadata_error":
                seq, error = payload
                if job_id == "preview" and seq == self.metadata_counter:
                    self._set_preview_title("Vorschau nicht verfügbar")
                    self.preview_channel.configure(text=self._truncate(error, 58))
                    self._log_event("warning", f"Videovorschau nicht verfügbar: {error}")
                elif job_id in self.manager.jobs:
                    self._log_event("warning", f"Metadaten nicht verfügbar: {error}", job_id)
        if rebuild or progress:
            self._collect_job_log_events()
        if rebuild:
            self._render_queue()
        elif progress:
            self._update_queue_progress()
        if rebuild or progress:
            self._refresh_progress()
            self._refresh_preview()
        if history_changed:
            self._render_history_summary()
            if self.active_page == "history":
                self._render_full_history()
        # Die Scrollposition beobachten: Maus, Touchpad, Tastatur und Ziehen
        # des Scrollbalkens funktionieren ohne globale Tk-Bindings.
        if self.active_page == "log":
            self._track_log_scroll()
        self.after(185, self._poll_events)

    def _add_history(self, job):
        entry = {
            "id": job.id, "title": job.title, "mode": job.mode,
            "quality": job.quality, "audio_format": job.audio_format,
            "date": datetime.now().isoformat(timespec="minutes"),
            "output_dir": job.output_dir, "filename": job.filename,
            "playlist": job.playlist, "folder_organization": job.folder_organization,
            "thumbnail_path": job.thumbnail_path, "url": job.url,
            "size": job.total,
        }
        self.history.insert(0, entry)
        self.history = self.history[:300]
        save_json(HISTORY_FILE, self.history)

    def _reset_history_preview_scroll(self):
        """Show newest history items at the top after a completed download.

        CustomTkinter stores the scroll offset on a parent canvas; guard
        access because the window may have closed before this callback fires.
        """
        try:
            canvas = getattr(self.history_preview_scroll, "_parent_canvas", None)
            if canvas is not None and canvas.winfo_exists():
                canvas.yview_moveto(0.0)
        except Exception:
            pass

    def _render_history_summary(self):
        self.history_count.configure(text=str(len(self.history)))
        for w in self.history_preview_scroll.winfo_children():
            w.destroy()
        # Rebuilding the summary should never strand the newest entry above
        # the canvas when the previous scroll position was further down.
        self.after(65, self._reset_history_preview_scroll)
        if not self.history:
            self._empty_state(self.history_preview_scroll, "history", "Noch kein Verlauf",
                              "Abgeschlossene Downloads\nwerden hier angezeigt.", top=28)
            return
        for entry in self.history[:4]:
            row = ctk.CTkFrame(self.history_preview_scroll,
                               fg_color="transparent", height=HISTORY_ROW_HEIGHT)
            row.pack(fill="x", pady=HISTORY_ROW_PADY)
            row.pack_propagate(False)
            pic = ctk.CTkLabel(
                row, text="", width=46, height=34,
                image=self._thumb_image(entry.get("thumbnail_path"), (46, 34)))
            pic.pack(side="left", padx=(0, 7))
            # Reserve the completion marker before the expanding title frame.
            # This prevents long metadata from pushing it outside the card.
            make_label(row, "✓", 16, GREEN, True, width=17).pack(side="right", padx=(1, 2))
            text_frame = ctk.CTkFrame(row, fg_color="transparent")
            text_frame.pack(side="left", fill="both", expand=True)
            title_text = entry.get("title", "Download")
            title_widget = make_label(text_frame, self._truncate_title(title_text, 30),
                                      12, TEXT, True, anchor="w", width=1, height=16)
            title_widget.pack(fill="x", anchor="w")
            title_widget.bind("<Configure>",
                              lambda _e, w=title_widget, t=title_text: self._fit_title_label(w, t, 35))
            HoverTooltip(title_widget, title_text)
            for clickable in (pic, title_widget):
                clickable.bind("<Double-Button-1>",
                               lambda _e, d=entry: self._open_download_directory(d.get("output_dir", "")))
            make_label(text_frame, compact_history_metadata(entry),
                       11, "#becbff", anchor="w", width=1, height=15).pack(
                           fill="x", anchor="w")

    # ------------------------------------------------------------ Profiles
    def _apply_profile(self, name):
        self.profile_name.set(name)
        profile = self.config_data["profiles"].get(name)
        if not profile:
            return
        self._set_mode(profile.get("mode", "Video (MP4)"))
        self.quality.set(profile.get("quality", "1080p"))
        self.audio_format.set(profile.get("audio_format", "MP3"))
        self.playlist.set(bool(profile.get("playlist", True)))

    def _get_current_profile(self):
        return {"mode": self.mode.get(), "quality": self.quality.get(),
                "audio_format": self.audio_format.get(), "playlist": self.playlist.get()}

    def add_profile(self):
        dialog = ctk.CTkInputDialog(text="Name für das neue Download-Profil:",
                                    title="Profil erstellen")
        name = (dialog.get_input() or "").strip()
        if not name:
            return
        if name in self.config_data["profiles"]:
            messagebox.showerror("Profil", "Dieses Profil existiert bereits.")
            return
        self.config_data["profiles"][name] = self._get_current_profile()
        self.profile_name.set(name)
        save_json(CONFIG_FILE, self.config_data)
        if self.active_page == "profiles":
            self._render_full_profiles()

    def save_profile(self):
        name = self.profile_name.get()
        self.config_data["profiles"][name] = self._get_current_profile()
        save_json(CONFIG_FILE, self.config_data)
        messagebox.showinfo("Profil", f"Profil „{name}“ wurde gespeichert.")

    # --------------------------------------------------------- Other pages
    def _build_secondary_pages(self):
        for page in (self.history_page, self.profiles_page,
                     self.settings_page, self.about_page):
            page.grid_columnconfigure(0, weight=1)
        head = make_label(self.about_page, "Über NeonTube Downloader", 29, TEXT, True)
        head.grid(row=0, column=0, sticky="w", pady=(26, 25))
        panel = ctk.CTkFrame(self.about_page, fg_color=PANEL, border_color=BORDER,
                             border_width=1, corner_radius=18)
        panel.grid(row=1, column=0, sticky="ew")
        logo_image = img("neontube_logo.png", (100, 70))
        self.about_logo = logo_image
        ctk.CTkLabel(panel, text="", image=logo_image).pack(pady=(25, 10))
        for text, size, color in [
            (f"NeonTube Downloader {VERSION}", 23, TEXT),
            ("Videos und Audiodateien herunterladen.", 14, MUTED),
            ("Oberfläche: customtkinter • Download-Engine: yt-dlp", 13, MUTED),
            ("Benötigt Internetzugang; manche Videos sind regional oder technisch gesperrt.", 12, MUTED),
            ("Bitte nur Inhalte herunterladen, für die du die entsprechenden Rechte hast.", 12, MUTED)
        ]:
            make_label(panel, text, size, color).pack(pady=7)
        make_label(panel, f"Einstellungen und Verlauf: {DATA}", 10, MUTED).pack(pady=(9, 25))

    def _render_full_history(self):
        for child in self.history_page.winfo_children():
            child.destroy()
        make_label(self.history_page, "Download-Verlauf", 30, TEXT, True).grid(
            row=0, column=0, sticky="w", pady=(25, 5))
        make_label(
            self.history_page,
            f"{len(self.history)} abgeschlossene Downloads" if self.history
            else "Noch keine abgeschlossenen Downloads",
            14, MUTED).grid(row=1, column=0, sticky="w", pady=(0, 19))
        buttons = ctk.CTkFrame(self.history_page, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="w", pady=(0, 15))
        regular_button(buttons, "Download-Ordner öffnen", lambda: open_path(self.output_dir.get()),
                       width=189).pack(side="left", padx=(0, 10))
        regular_button(buttons, "Verlauf löschen", self.clear_history,
                       width=120).pack(side="left")
        if not self.history:
            make_label(self.history_page, "Noch keine abgeschlossenen Downloads.",
                       17, MUTED).grid(row=3, column=0, pady=55)
            return
        for idx, entry in enumerate(self.history):
            # V1.15: place every history element directly in the card. The
            # previous transparent intermediary CTkFrame could be painted with
            # a darker parent color on Windows, producing a rectangular band
            # across the middle of each history row.
            p = ctk.CTkFrame(
                self.history_page, fg_color=PANEL,
                border_color=BORDER, border_width=1,
                corner_radius=14, height=86)
            p.grid(row=idx + 3, column=0, sticky="ew", pady=5)
            p.grid_propagate(False)
            p.grid_columnconfigure(1, weight=1, minsize=90)
            p.grid_rowconfigure(0, weight=1)
            p.grid_rowconfigure(1, weight=1)
            picture = ctk.CTkLabel(
                p, text="", fg_color=PANEL,
                image=self._thumb_image(entry.get("thumbnail_path"), (95, 65)),
                width=95, height=65)
            picture.grid(row=0, column=0, rowspan=2,
                         padx=(12, 13), pady=8, sticky="w")
            full_title = str(entry.get("title") or "Download")
            history_title = make_label(
                p, self._truncate_title(full_title, 32),
                14, TEXT, True, anchor="w", width=1, fg_color=PANEL)
            history_title.grid(row=0, column=1, sticky="ew",
                               padx=(0, 12), pady=(12, 0))
            history_title.bind(
                "<Configure>",
                lambda _event, w=history_title, value=full_title:
                    self._fit_title_label(w, value, 32))
            self.after_idle(
                lambda w=history_title, value=full_title:
                    self._fit_if_visible(w, value, 32))
            HoverTooltip(history_title, full_title)
            history_info = make_label(
                p, compact_history_metadata(entry), 11, MUTED,
                anchor="w", width=1, fg_color=PANEL)
            history_info.grid(row=1, column=1, sticky="ew",
                              padx=(0, 12), pady=(0, 11))
            # Double-click on the picture/text opens that entry's real output
            # directory. Keep the existing button for single-click access.
            for target in (p, history_title, history_info, picture):
                target.bind(
                    "<Double-Button-1>",
                    lambda _event, item=entry:
                        self._open_download_directory(self._record_folder(item)))
            regular_button(
                p, "Ordner öffnen",
                lambda e=entry: self._open_download_directory(self._record_folder(e)),
                width=118, height=37).grid(
                    row=0, column=2, rowspan=2,
                    padx=(6, 11), pady=10, sticky="e")

    def clear_history(self):
        if not self.history:
            return
        if messagebox.askyesno("Verlauf löschen", "Gesamten Verlauf löschen? Dateien bleiben erhalten."):
            self.history.clear()
            save_json(HISTORY_FILE, self.history)
            self._render_full_history()
            self._render_history_summary()

    def _render_full_profiles(self):
        for child in self.profiles_page.winfo_children():
            child.destroy()
        make_label(self.profiles_page, "Download-Profile", 30, TEXT, True).grid(
            row=0, column=0, sticky="w", pady=(25, 5))
        make_label(self.profiles_page, "Deine bevorzugten Qualitäts- und Audioeinstellungen",
                   14, MUTED).grid(row=1, column=0, sticky="w", pady=(0, 15))
        regular_button(self.profiles_page, "+ Neues Profil", self.add_profile,
                       width=155).grid(row=2, column=0, sticky="w", pady=(0, 18))
        for idx, (name, profile) in enumerate(self.config_data["profiles"].items()):
            p = ctk.CTkFrame(self.profiles_page, fg_color=PANEL,
                             corner_radius=14, border_color=BORDER, border_width=1, height=87)
            p.grid(row=idx+3, column=0, sticky="ew", pady=6)
            p.grid_propagate(False)
            t = ctk.CTkFrame(p, fg_color="transparent")
            t.pack(side="left", padx=18, pady=14, fill="both", expand=True)
            make_label(t, name, 17, TEXT, True).pack(anchor="w")
            make_label(t, f"{profile.get('mode','')} · {profile.get('quality','')} · {profile.get('audio_format','')}",
                       12, MUTED).pack(anchor="w", pady=5)
            regular_button(p, "Verwenden",
                           lambda n=name: (self._apply_profile(n), self._switch_page("download")),
                           width=115).pack(side="right", padx=(5, 10))
            if name != "Standard":
                regular_button(p, "Löschen", lambda n=name: self._delete_profile(n),
                               width=80).pack(side="right")

    def _delete_profile(self, name):
        if not messagebox.askyesno("Profil löschen", f"Profil „{name}“ löschen?"):
            return
        self.config_data["profiles"].pop(name, None)
        if self.profile_name.get() == name:
            self._apply_profile("Standard")
        save_json(CONFIG_FILE, self.config_data)
        self._render_full_profiles()

    # ------------------------------------------------------------ Settings
    def open_settings(self):
        """Navigate to the settings section, without a separate popup window."""
        self.active_page = "settings"
        for name, page in {
            "download": self.download_page,
            "search": self.search_page,
            "favorites": self.favorites_page,
            "history": self.history_page,
            "profiles": self.profiles_page,
            "settings": self.settings_page,
            "log": self.log_page,
            "about": self.about_page,
        }.items():
            if name == "settings":
                page.grid()
            else:
                page.grid_remove()
        for name, button in self.nav_buttons.items():
            button.set_selected(name == "settings")
        self._render_settings_page()

    def _render_settings_page(self):
        """Inline settings page styled like the full-width profile page."""
        page = self.settings_page
        for child in page.winfo_children():
            child.destroy()

        make_label(page, "Einstellungen", 30, TEXT, True).grid(
            row=0, column=0, sticky="w", pady=(25, 5))
        make_label(page, "Download-Verwaltung und Speicherorte anpassen",
                   14, MUTED).grid(row=1, column=0, sticky="w", pady=(0, 20))

        card = NeonGlassPanel(page, corner_radius=16, accent="blue")
        card.grid(row=2, column=0, sticky="ew", pady=(0, 18))
        card.grid_columnconfigure(1, weight=1)
        card.grid_columnconfigure(0, minsize=245)

        concurrency = ctk.StringVar(value=str(self.manager.max_concurrency))
        folder = ctk.StringVar(value=self.output_dir.get())
        cookies = ctk.StringVar(value=self.config_data.get("cookiefile", ""))
        organization = ctk.StringVar(value=normalize_folder_organization(
            self.config_data.get("folder_organization", "")))

        make_label(card, "Parallele Downloads", 14, TEXT, True,
                   anchor="w").grid(row=0, column=0, sticky="w",
                                     padx=(20, 12), pady=(24, 12))
        ctk.CTkOptionMenu(
            card, variable=concurrency, values=["1", "2", "3", "4"],
            fg_color="#162158", button_color="#253478",
            button_hover_color="#343b88", corner_radius=10,
            width=140, height=38,
            font=ctk.CTkFont(family=FONT, size=13)).grid(
                row=0, column=1, sticky="w", padx=(0, 14), pady=(24, 12))

        make_label(card, "Standard-Downloadordner", 14, TEXT, True,
                   anchor="w").grid(row=1, column=0, sticky="w",
                                     padx=(20, 12), pady=12)
        ctk.CTkEntry(
            card, textvariable=folder, fg_color="#11194a", height=38,
            border_color=BORDER, font=ctk.CTkFont(family=FONT, size=13)).grid(
                row=1, column=1, sticky="ew", padx=(0, 10), pady=12)
        regular_button(
            card, "Durchsuchen", lambda: self._choose_setting_folder(folder),
            width=110, height=37, font_size=12).grid(
                row=1, column=2, padx=(0, 20), pady=12)

        make_label(card, "Downloads sortieren", 14, TEXT, True,
                   anchor="w").grid(row=2, column=0, sticky="w",
                                     padx=(20, 12), pady=12)
        ctk.CTkOptionMenu(
            card, variable=organization, values=list(FOLDER_ORGANIZATIONS),
            fg_color="#162158", button_color="#253478",
            button_hover_color="#343b88", corner_radius=10,
            width=238, height=38,
            font=ctk.CTkFont(family=FONT, size=13)).grid(
                row=2, column=1, sticky="w", padx=(0, 14), pady=12)

        make_label(card, "Cookies-Datei (optional)", 14, TEXT, True,
                   anchor="w").grid(row=3, column=0, sticky="w",
                                     padx=(20, 12), pady=12)
        ctk.CTkEntry(
            card, textvariable=cookies, fg_color="#11194a", height=38,
            border_color=BORDER, font=ctk.CTkFont(family=FONT, size=13),
            placeholder_text="Netscape-Cookies als .txt-Datei").grid(
                row=3, column=1, sticky="ew", padx=(0, 10), pady=12)
        regular_button(
            card, "Durchsuchen", lambda: self._choose_cookiefile(cookies),
            width=110, height=37, font_size=12).grid(
                row=3, column=2, padx=(0, 20), pady=12)

        language = ctk.StringVar(value=self.i18n.selected_name())
        make_label(card, "Sprache / Language", 14, TEXT, True,
                   anchor="w").grid(row=8, column=0, sticky="w",
                                    padx=(20, 12), pady=(12, 7))
        ctk.CTkOptionMenu(
            card, variable=language, values=list(self.i18n.languages),
            command=self._choose_language,
            fg_color="#162158", button_color="#253478",
            button_hover_color="#343b88", corner_radius=10,
            width=238, height=38,
            font=ctk.CTkFont(family=FONT, size=13)).grid(
                row=8, column=1, sticky="w", padx=(0, 14), pady=(12, 7))
        make_label(
            card, "Die Sprache wird sofort gespeichert. Für weitere Sprachen werden Oberflächentexte online übersetzt und lokal gespeichert.",
            11, MUTED, anchor="w", wraplength=680).grid(
                row=9, column=0, columnspan=3, sticky="w",
                padx=20, pady=(0, 8))

        api_key = ctk.StringVar(value=self.youtube_api_key)
        make_label(card, "YouTube Data API v3", 14, TEXT, True,
                   anchor="w").grid(row=4, column=0, sticky="w", padx=(20, 12), pady=12)
        api_entry = ctk.CTkEntry(
            card, textvariable=api_key, show="•", fg_color="#11194a",
            height=38, border_color=BORDER,
            placeholder_text="Eigenen YouTube-API-Schlüssel eintragen",
            font=ctk.CTkFont(family=FONT, size=13))
        api_entry.grid(row=4, column=1, sticky="ew", padx=(0, 10), pady=12)
        def toggle_api_key():
            api_entry.configure(show="" if api_entry.cget("show") else "•")
        regular_button(card, "Anzeigen", toggle_api_key, width=110,
                       height=37, font_size=12).grid(row=4, column=2, padx=(0, 20), pady=12)
        make_label(card, "Schlüssel wird nur für dieses Windows-Konto verschlüsselt gespeichert (DPAPI).",
                   11, MUTED, anchor="w").grid(
                       row=5, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 5))
        ctk.CTkFrame(card, height=1, fg_color="#31386e",
                     corner_radius=0).grid(
            row=6, column=0, columnspan=3, sticky="ew", padx=20, pady=(14, 5))
        make_label(
            card,
            "FFmpeg: " + ("verfügbar" if ffmpeg_path() else "muss im PATH liegen")
            + "   |   Deno: " + ("gefunden" if javascript_runtime_config() else "nicht gefunden"),
            12, MUTED, anchor="w").grid(
                row=7, column=0, columnspan=3, sticky="w",
                padx=20, pady=(9, 24))

        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="w")
        notice = make_label(actions, "", 12, GREEN, anchor="w")

        def save_settings():
            concurrent = int(concurrency.get())
            self.manager.set_concurrency(concurrent)
            self.config_data["concurrent"] = concurrent
            self.config_data["download_dir"] = folder.get()
            self.config_data["cookiefile"] = cookies.get()
            self.config_data["folder_organization"] = normalize_folder_organization(
                organization.get())
            self.manager.cookiefile = cookies.get()
            self.output_dir.set(folder.get())
            self.folder_label.configure(text=self._truncate(folder.get(), 29))
            try:
                save_json(CONFIG_FILE, self.config_data)
                write_api_key(DATA, api_key.get())
                self.youtube_api_key = api_key.get().strip()
            except OSError as exc:
                notice.configure(text=f"Speichern fehlgeschlagen: {exc}",
                                 text_color="#ff8a9c")
                return
            notice.configure(text="Einstellungen gespeichert.", text_color=GREEN)

        regular_button(
            actions, "Einstellungen speichern", save_settings,
            fg="#7e14e4", hover="#a21bed", width=213,
            height=42, font_size=14).pack(side="left")
        notice.pack(side="left", padx=(18, 0))

    @staticmethod
    def _choose_setting_folder(var):
        folder = filedialog.askdirectory(title="Ordner auswählen", initialdir=var.get())
        if folder:
            var.set(folder)

    @staticmethod
    def _choose_cookiefile(var):
        path = filedialog.askopenfilename(title="Cookies-Datei auswählen",
                                           filetypes=[("Textdateien", "*.txt"), ("Alle Dateien", "*.*")])
        if path:
            var.set(path)

    # -------------------------------------------------- Integriertes Log
    def _log_canvas(self):
        """Underlying Tk canvas of CTkScrollableFrame (when already built)."""
        return getattr(getattr(self, "log_list", None), "_parent_canvas", None)

    def _log_canvas_geometry(self):
        """Return canvas, current yview and pixel size without raising on resize."""
        canvas = self._log_canvas()
        if canvas is None:
            return None
        try:
            first, last = canvas.yview()
            region = canvas.bbox("all")
            viewport = max(1, canvas.winfo_height())
            extent = max(viewport, region[3] - region[1]) if region else viewport
            return canvas, first, last, extent, viewport
        except Exception:
            return None

    def _track_log_scroll(self):
        """Manual scrolling down pauses following; returning to top resumes."""
        if self._log_scroll_restoring or self.active_page != "log":
            return
        metrics = self._log_canvas_geometry()
        if metrics is None:
            return
        _, first, _, extent, viewport = metrics
        following = (extent <= viewport + 2 or first <= 0.006)
        if following != self._log_auto_follow:
            self._log_auto_follow = following
            self._update_log_scroll_indicator()

    def _update_log_scroll_indicator(self):
        status = getattr(self, "log_scroll_status", None)
        if status is not None:
            status.configure(
                text="Auto-Scroll aktiv" if self._log_auto_follow
                     else "Auto-Scroll pausiert · nach oben scrollen",
                text_color=GREEN if self._log_auto_follow else MUTED)

    def _restore_log_scroll(self, generation: int, bottom_gap):
        """Restore after CustomTkinter has measured the new scrollregion."""
        if generation != self._log_scroll_generation:
            return
        try:
            metrics = self._log_canvas_geometry()
            if metrics is None or self.active_page != "log":
                return
            canvas, _, _, extent, viewport = metrics
            if self._log_auto_follow or bottom_gap is None:
                canvas.yview_moveto(0.0)
            else:
                canvas.yview_moveto(log_scroll_top_fraction(
                    extent, viewport, bottom_gap))
        finally:
            self._log_scroll_restoring = False
            self._update_log_scroll_indicator()

    def _schedule_log_scroll_restore(self, bottom_gap):
        if self.active_page != "log":
            return
        self._log_scroll_restoring = True
        self._log_scroll_generation += 1
        generation = self._log_scroll_generation
        # Frame/canvas resize and scrollregion updates settle after geometry.
        self.after(65, lambda: self._restore_log_scroll(generation, bottom_gap))

    def _log_event(self, level: str, message: str, job_id: str = ""):
        """Log nur im Tk-Hauptthread schreiben; keine sensiblen URLs erfassen."""
        if level not in ("info", "download", "success", "warning", "error"):
            level = "info"
        cleaned = re.sub(r"https?://\S+", "[URL]", " ".join(str(message).split()))[:650]
        self.log_entries.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": level, "message": cleaned, "job_id": job_id,
        })
        # Speicher begrenzen. Keine automatische Protokolldatei anlegen.
        if len(self.log_entries) > 500:
            del self.log_entries[:-500]
        if getattr(self, "active_page", "") == "log" and not self._log_render_pending:
            # Bei vielen Fragmenten nicht jedes Mal alle 100 Karten neu zeichnen.
            self._log_render_pending = True
            self.after(130, self._flush_log_render)

    def _log_progress_event(self, job, percentage: int):
        """Update exactly one progress record per job; never spam the log list.

        Keep full titles in the data so copy/export and hover remain lossless.
        If the oldest progress record has already been trimmed, create one anew.
        """
        job_id = job.id
        percentage = max(0, min(100, int(percentage)))
        if percentage <= self._log_progress_deciles.get(job_id, 0):
            return
        self._log_progress_deciles[job_id] = percentage
        message = re.sub(r"https?://\S+", "[URL]",
                         f"Download bei {percentage}%: {job.title}")[:650]
        event = next((item for item in reversed(self.log_entries)
                      if item.get("kind") == "progress" and item.get("job_id") == job_id), None)
        if event is None:
            self.log_entries.append({
                "time": datetime.now().strftime("%H:%M:%S"), "level": "download",
                "message": message, "job_id": job_id, "kind": "progress",
            })
            if len(self.log_entries) > 500:
                del self.log_entries[:-500]
        else:
            event["time"] = datetime.now().strftime("%H:%M:%S")
            event["message"] = message
        if getattr(self, "active_page", "") == "log" and not self._log_render_pending:
            self._log_render_pending = True
            self.after(130, self._flush_log_render)

    def _flush_log_render(self):
        self._log_render_pending = False
        if self.active_page == "log":
            self._render_log_entries()

    def _collect_job_log_events(self):
        """Statuswechsel und Fortschritt aus den vorhandenen Manager-Events ableiten."""
        labels = {
            "queued": ("info", "Wartet in der Warteschlange"),
            "downloading": ("download", "Download läuft"),
            "processing": ("download", "Datei wird verarbeitet / zusammengeführt"),
            "retrying": ("warning", "Automatische Download-Reparatur läuft"),
            "pausing": ("info", "Download wird pausiert"),
            "paused": ("warning", "Download pausiert"),
            "cancelled": ("warning", "Download abgebrochen"),
            "finished": ("success", "Download abgeschlossen"),
            "failed": ("error", "Download fehlgeschlagen"),
        }
        for job_id, job in tuple(self.manager.jobs.items()):
            status = job.status
            if self._log_seen_states.get(job_id) != status:
                self._log_seen_states[job_id] = status
                level, label = labels.get(status, ("info", status))
                detail = f": {job.title}" if job.title else ""
                if status == "failed" and job.error:
                    detail += f" — {job.error}"
                self._log_event(level, label + detail, job_id)
            if status == "downloading" and job.total > 0:
                # Eine einzige Karte pro Download: in 10-%-Schritten aktualisieren.
                percentage = min(90, int(job.progress * 10) * 10)
                if percentage >= 10:
                    self._log_progress_event(job, percentage)
            elif status == "finished" and job.total > 0:
                self._log_progress_event(job, 100)
        # Entfernte Downloads aus den Status-Caches lösen.
        remaining = set(self.manager.jobs)
        for job_id in list(self._log_seen_states):
            if job_id not in remaining:
                del self._log_seen_states[job_id]
                self._log_progress_deciles.pop(job_id, None)

    def _filtered_log_entries(self):
        if self.log_filter == "Downloads":
            return [e for e in self.log_entries if e["level"] in ("download", "success")]
        if self.log_filter == "Fehler":
            return [e for e in self.log_entries if e["level"] in ("warning", "error")]
        return list(self.log_entries)

    def _log_as_text(self):
        entries = self._filtered_log_entries()
        header = f"NeonTube Downloader {VERSION} – Download-Protokoll"
        return "\n".join([header, ""] + [
            f"[{event['time']}] {event['level'].upper()}: {event['message']}"
            for event in entries
        ]) + "\n"

    def _build_log_page(self):
        """Log wie Einstellungen/Profile als Seite – nie als CTkToplevel."""
        page = self.log_page
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(3, weight=1)
        heading = ctk.CTkFrame(page, fg_color="transparent")
        heading.grid(row=0, column=0, sticky="ew", pady=(21, 4))
        small_icon_label(heading, "progress", 30, "#bf8aff").pack(side="left", padx=(4, 10))
        make_label(heading, "Download-Protokoll", 29, TEXT, True).pack(side="left")
        regular_button(heading, "Zurück zum Download",
                       lambda: self._switch_page("download"), width=160,
                       height=36, font_size=12).pack(side="right", padx=(0, 5))
        make_label(page, "Live-Ereignisse, Downloads und Fehlermeldungen",
                   14, MUTED).grid(row=1, column=0, sticky="w", pady=(0, 15), padx=4)

        panel = NeonGlassPanel(page, corner_radius=16, accent="violet")
        panel.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        toolbar = ctk.CTkFrame(panel, fg_color="transparent")
        toolbar.pack(fill="x", padx=15, pady=13)
        self.log_filter_buttons = {}
        for label in ("Alle Ereignisse", "Downloads", "Fehler"):
            btn = regular_button(
                toolbar, label, lambda value=label: self._set_log_filter(value),
                width=140 if label == "Alle Ereignisse" else 112,
                height=36, font_size=12)
            btn.pack(side="left", padx=(0, 8))
            self.log_filter_buttons[label] = btn
        self.log_count_label = make_label(toolbar, "", 12, MUTED)
        self.log_count_label.pack(side="right", padx=(8, 4))
        self.log_scroll_status = make_label(toolbar, "", 11, GREEN)
        self.log_scroll_status.pack(side="right", padx=(12, 8))
        self._update_log_scroll_indicator()

        self.log_list = ctk.CTkScrollableFrame(
            page, fg_color="#090d2a", border_width=1, border_color="#323d79",
            corner_radius=16, scrollbar_button_color="#302468",
            scrollbar_button_hover_color=PURPLE)
        self.log_list.grid(row=3, column=0, sticky="nsew")

        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", pady=(14, 12))
        regular_button(actions, "Kopieren", self._copy_log, width=113, height=38,
                       icon_kind="storage").pack(side="left", padx=(0, 10))
        regular_button(actions, "Speichern", self._save_log, width=113,
                       height=38, icon_kind="folder").pack(side="left", padx=(0, 10))
        regular_button(actions, "Leeren", self._clear_log, fg="#54245e",
                       hover="#732c7c", width=110, height=38,
                       icon_kind="cancel").pack(side="left")
        self.log_notice = make_label(actions, "", 12, GREEN)
        self.log_notice.pack(side="right", padx=(8, 4))
        self._highlight_log_filter()
        self._render_log_entries()

    def _set_log_filter(self, value):
        self.log_filter = value
        self._highlight_log_filter()
        self._render_log_entries(reset_scroll=True)

    def _highlight_log_filter(self):
        for label, btn in self.log_filter_buttons.items():
            selected = label == self.log_filter
            btn.configure(fg_color="#7926cf" if selected else PANEL_ALT,
                          hover_color="#9340e7" if selected else "#202e66")

    def _render_log_entries(self, *, reset_scroll=False):
        if not hasattr(self, "log_list"):
            return
        if reset_scroll:
            self._log_auto_follow = True
        elif not self._log_scroll_restoring:
            # A scroll may have occurred since the previous ~185ms poll.
            self._track_log_scroll()
        bottom_gap = None
        metrics = self._log_canvas_geometry()
        if (metrics is not None and self.active_page == "log"
                and not self._log_auto_follow):
            _, _, last, extent, _ = metrics
            bottom_gap = max(0.0, (1.0 - last) * extent)
        for child in self.log_list.winfo_children():
            child.destroy()
        matches = self._filtered_log_entries()
        self.log_count_label.configure(text=f"{len(matches)} Ereignisse")
        # Die jüngsten 100 sind sichtbar; Export/Kopieren enthalten alle Treffer.
        view = matches[-100:]
        if not view:
            make_label(self.log_list, "Keine Ereignisse in dieser Ansicht.",
                       14, MUTED).pack(anchor="center", padx=24, pady=40)
            self._schedule_log_scroll_restore(bottom_gap)
            return
        colors = {
            "info": ("INFO", "#76b7ff"),
            "download": ("DOWNLOAD", "#bb94ff"),
            "success": ("ERFOLG", "#23eac2"),
            "warning": ("WARNUNG", "#ffd67a"),
            "error": ("FEHLER", "#ff7c9c"),
        }
        icon_kinds = {"info": "info", "download": "download",
                      "success": "success", "warning": "warning", "error": "error"}
        for event in reversed(view):
            title, color = colors[event["level"]]
            row = ctk.CTkFrame(self.log_list, fg_color="#121842",
                               corner_radius=11, border_width=1,
                               border_color="#303967")
            row.pack(fill="x", padx=8, pady=3)
            head = ctk.CTkFrame(row, fg_color="transparent")
            head.pack(fill="x", padx=12, pady=(6, 0))
            small_icon_label(head, icon_kinds[event["level"]], 17, color).pack(
                side="left", padx=(0, 6))
            make_label(head, event["time"], 11, MUTED).pack(side="left")
            make_label(head, title, 11, color, True).pack(side="left", padx=(10, 0))
            full_message = event["message"]
            # One compact line for each event; original text remains in data.
            message_label = make_label(
                row, self._truncate_title(full_message, 66), 12, TEXT,
                anchor="w", height=21)
            message_label.pack(fill="x", padx=12, pady=(0, 6), anchor="w")
            message_label.bind(
                "<Configure>",
                lambda _evt, w=message_label, message=full_message:
                    self._fit_if_visible(w, message, 66), add="+")
            HoverTooltip(message_label, full_message)
            self.after_idle(lambda w=message_label, message=full_message:
                            self._fit_if_visible(w, message, 66))
        self._schedule_log_scroll_restore(bottom_gap)

    def _copy_log(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self._log_as_text())
            self.update_idletasks()
            self.log_notice.configure(text="Protokoll kopiert.", text_color=GREEN)
        except Exception as exc:
            self.log_notice.configure(text=f"Kopieren fehlgeschlagen: {exc}",
                                      text_color="#ff8a9c")

    def _save_log(self):
        destination = filedialog.asksaveasfilename(
            title="Download-Protokoll speichern", defaultextension=".txt",
            initialfile=f"NeonTube_Log_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.txt",
            filetypes=[("Textdatei", "*.txt"), ("Alle Dateien", "*.*")])
        if not destination:
            return
        try:
            Path(destination).write_text(self._log_as_text(), encoding="utf-8")
            self.log_notice.configure(text="Protokoll gespeichert.", text_color=GREEN)
        except OSError as exc:
            self.log_notice.configure(text=f"Speichern fehlgeschlagen: {exc}",
                                      text_color="#ff8a9c")

    def _clear_log(self):
        if not self.log_entries:
            return
        if not messagebox.askyesno("Download-Protokoll leeren",
                                   "Protokolleinträge dieser Sitzung löschen? "
                                   "Download-Verlauf und Dateien bleiben erhalten."):
            return
        self.log_entries.clear()
        # Running jobs may create a new progress card after clearing the log.
        self._log_progress_deciles.clear()
        self.log_notice.configure(text="Protokoll geleert.", text_color=GREEN)
        self._render_log_entries(reset_scroll=True)

    def on_close(self):
        if self._clipboard_watch_after is not None:
            try:
                self.after_cancel(self._clipboard_watch_after)
            except Exception:
                pass
            self._clipboard_watch_after = None
        running = any(j.status in ("downloading", "processing", "pausing", "retrying")
                      for j in self.manager.jobs.values())
        if running and not messagebox.askyesno(
                "Programm schließen", "Es laufen noch Downloads. Wirklich beenden?"):
            return
        self.manager.close()
        self.config_data["download_dir"] = self.output_dir.get()
        try:
            save_json(CONFIG_FILE, self.config_data)
        except OSError:
            pass
        self.destroy()


def main():
    app = NeonTubeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
