"""Optional language selector and UI-only translation cache for NeonTube.

Only known, fixed interface strings are submitted to the translation
provider. URLs, video titles, paths, credentials and user data are not.
"""
from __future__ import annotations
import json
import queue
import threading
import time

from neontube_locale_packs import CORE_TRANSLATIONS, CORE_KEYS
from pathlib import Path

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

# Only fixed UI copy, never data values, internal identifiers or download modes.
UI_TEXTS = frozenset(["+ Neues Profil","× Abgebrochen","▱  Durchsuchen","◷ Wartet …","⚠ Fehler – zum Anzeigen auswählen","✓ Abgeschlossen","Abbrechen","Abgeschlossen","Aktuelle Geschwindigkeit","Alle anzeigen","Alle auswählen","Alle Dateien","Alle Einträge entfernen und aktive Downloads abbrechen?","Als Favorit speichern / Favorit entfernen","Anzeigen","API-Schlüssel fehlt. Bitte unter Einstellungen speichern.","Audioformat","Aus Favoriten entfernen","Auswahl aufheben","Auswahl entfernen","Auto-Scroll aktiv","Auto-Scroll pausiert · nach oben scrollen","Automatische Download-Reparatur läuft","Benötigt Internetzugang; manche Videos sind regional oder technisch gesperrt.","Bereits gespeicherte Dateien werden nicht automatisch überschrieben.","Bereits heruntergeladen","Beste Qualität","Bitte einen API-Schlüssel unter Einstellungen eintragen, um zu suchen.","Bitte mindestens einen gültigen http(s)-Link einfügen.","Bitte nur Inhalte herunterladen, für die du die entsprechenden Rechte hast.","Bitte zuerst einen Suchbegriff eingeben.","Cookies-Datei (optional)","Cookies-Datei auswählen","Datei wird verarbeitet / zusammengeführt","Deine bevorzugten Qualitäts- und Audioeinstellungen","Deine Warteschlange ist leer","Die Sprache wird sofort gespeichert. Für weitere Sprachen werden Oberflächentexte online übersetzt und lokal gespeichert.","Dieser Download-Ordner ist nicht mehr vorhanden.","Dieses Profil existiert bereits.","Doppelte Downloads","Download abgebrochen","Download abgeschlossen","Download fehlgeschlagen","Download läuft","Download pausiert","Download starten","Download wird pausiert","Download-Ordner auswählen","Download-Ordner öffnen","Download-Profile","Download-Protokoll","Download-Protokoll leeren","Download-Protokoll speichern","Download-System bereit. Noch kein Download gestartet.","Download-Verlauf","Download-Verlauf und Dateien bleiben erhalten.","Download-Verwaltung und Speicherorte anpassen","Download-Warteschlange","Downloads sortieren","Duplikatschutz aktiv","Durchsuchen","Eigenen YouTube-API-Schlüssel eintragen","Einstellungen","Einstellungen gespeichert.","Einstellungen speichern","Es laufen noch Downloads. Wirklich beenden?","Es wird kein Download automatisch gestartet.","Favoriten","Fehler","Fortschritt","Fortsetzen","Füge einen YouTube-Link ein.","Gemerkte Videos jederzeit ohne erneute YouTube-Suche aufrufen.","Gesamten Verlauf löschen? Dateien bleiben erhalten.","Gib einen Suchbegriff ein und klicke auf Suchen.","Heruntergeladen","Ⅱ Pausiert","In der Zwischenablage ist kein Text.","Kein Download ausgewählt.","Kein Eintrag ausgewählt.","Kein YouTube-Link","Keine Videoinformationen gefunden","Konvertierung / Verarbeitung …","Kopieren","Leeren","Link einfügen","Link übernehmen","Live-Ereignisse, Downloads und Fehlermeldungen","Löschen","muss im PATH liegen","Name für das neue Download-Profil:","Netscape-Cookies als .txt-Datei","nicht gefunden","Noch kein Verlauf","Noch kein Video ausgewählt","Noch keine abgeschlossenen Downloads","Noch keine abgeschlossenen Downloads.","Noch keine Favoriten gespeichert.","Oberfläche: customtkinter • Download-Engine: yt-dlp","Ohne API-Daten ist yt-dlp für die Vorschau erforderlich.","Ordner auswählen","Ordner öffnen","Parallele Downloads","Pausieren","Pausieren …","Playlist herunterladen","Profil erstellen","Profil löschen","Profile","Programm schließen","Protokoll geleert.","Protokoll gespeichert.","Protokoll kopiert.","Protokolleinträge dieser Sitzung löschen? ","Qualität","Restzeit","Schlüssel wird nur für dieses Windows-Konto verschlüsselt gespeichert (DPAPI).","Speichern","Speicherort","Sprache / Language","Sprache auswählen","Sprache geändert.","Standard-Downloadordner","Starten","Suchen","Textdatei","Textdateien","Titel, Künstler oder Thema suchen …","Treffer:","Über","Über NeonTube Downloader","verfügbar","Verlauf","Verlauf löschen","Verwenden","Video für Mehrfachdownload auswählen","Video wird vorbereitet …","Videoinformationen werden geladen …","Videos und Audio einfach und schnell herunterladen.","Videos und Audiodateien herunterladen.","Videovorschau","Vorschau nicht verfügbar","Vorschau und Videoinformationen","Warteschlange","Warteschlange leeren","Weitere Ergebnisse laden","Weitere Treffer verfügbar.","YouTube-Link einfügen … (mehrere Links möglich)","YouTube-Link erkannt","YouTube-Suche","Zur Warteschlange (0)","Zur YouTube-Suche","Zurück zum Download","Zwischenablage"]) | frozenset(ENGLISH if False else ())
ENGLISH = {"Videos und Audio einfach und schnell herunterladen.":"Download videos and audio easily and quickly.","YouTube-Suche":"YouTube Search","Favoriten":"Favorites","Verlauf":"History","Einstellungen":"Settings","Profile":"Profiles","Über":"About","Link einfügen":"Paste link","YouTube-Link einfügen … (mehrere Links möglich)":"Paste YouTube link … (multiple links supported)","Videos finden und direkt in deine Download-Warteschlange übernehmen.":"Find videos and add them to your download queue.","Titel, Künstler oder Thema suchen …":"Search for a title, artist or topic …","Suchen":"Search","Treffer:":"Results:","Alle auswählen":"Select all","Auswahl aufheben":"Clear selection","Weitere Ergebnisse laden":"Load more results","Link übernehmen":"Use link","Zur YouTube-Suche":"Go to YouTube Search","Noch keine Favoriten gespeichert.":"No favorites saved yet.","Aus Favoriten entfernen":"Remove from favorites","Klicke in der YouTube-Suche auf das Herz neben einem Video.":"Click the heart next to a video in YouTube Search.","Gemerkte Videos jederzeit ohne erneute YouTube-Suche aufrufen.":"Access saved videos without searching again.","Video (MP4)":"Video (MP4)","Nur Audio (MP3)":"Audio only (MP3)","Playlist herunterladen":"Download playlist","Qualität":"Quality","Beste Qualität":"Best quality","Audioformat":"Audio format","Speicherort":"Save location","Durchsuchen":"Browse","▱  Durchsuchen":"▱  Browse","Download starten":"Start download","Pausieren":"Pause","Fortsetzen":"Resume","Abbrechen":"Cancel","Auswahl entfernen":"Remove selected","Download-Warteschlange":"Download queue","Deine Warteschlange ist leer":"Your queue is empty","Ordner öffnen":"Open folder","Alle anzeigen":"Show all","Download-Verlauf":"Download history","Noch kein Verlauf":"No history yet","Noch keine abgeschlossenen Downloads":"No completed downloads yet","Noch keine abgeschlossenen Downloads.":"No completed downloads yet.","Download-Ordner öffnen":"Open download folder","Verlauf löschen":"Clear history","Gesamten Verlauf löschen? Dateien bleiben erhalten.":"Clear your entire history? Files will be kept.","Download-Profile":"Download profiles","Deine bevorzugten Qualitäts- und Audioeinstellungen":"Your preferred quality and audio settings","+ Neues Profil":"+ New profile","Verwenden":"Use","Löschen":"Delete","Profil erstellen":"Create profile","Profil löschen":"Delete profile","Name für das neue Download-Profil:":"Name for the new download profile:","Dieses Profil existiert bereits.":"This profile already exists.","Download-Verwaltung und Speicherorte anpassen":"Customize download management and save locations","Parallele Downloads":"Concurrent downloads","Standard-Downloadordner":"Default download folder","Downloads sortieren":"Organize downloads","Cookies-Datei (optional)":"Cookie file (optional)","Netscape-Cookies als .txt-Datei":"Netscape cookies as .txt file","Eigenen YouTube-API-Schlüssel eintragen":"Enter your YouTube API key","Anzeigen":"Show","Schlüssel wird nur für dieses Windows-Konto verschlüsselt gespeichert (DPAPI).":"The key is stored encrypted for this Windows account only (DPAPI).","verfügbar":"available","muss im PATH liegen":"must be in PATH","nicht gefunden":"not found","Einstellungen speichern":"Save settings","Einstellungen gespeichert.":"Settings saved.","Sprache / Language":"Language","Sprache auswählen":"Choose language","Sprache geändert.":"Language changed.","Die Sprache wird sofort gespeichert. Für weitere Sprachen werden Oberflächentexte online übersetzt und lokal gespeichert.":"The language is saved immediately. For additional languages, interface text is translated online and cached locally.","Download-Protokoll":"Download log","Zurück zum Download":"Back to downloads","Live-Ereignisse, Downloads und Fehlermeldungen":"Live events, downloads and errors","Alle Ereignisse":"All events","Downloads":"Downloads","Fehler":"Errors","Kopieren":"Copy","Speichern":"Save","Leeren":"Clear","Auto-Scroll aktiv":"Auto-scroll on","Auto-Scroll pausiert · nach oben scrollen":"Auto-scroll paused · scroll to top","Über NeonTube Downloader":"About NeonTube Downloader","Videos und Audiodateien herunterladen.":"Download videos and audio files.","Oberfläche: customtkinter • Download-Engine: yt-dlp":"Interface: CustomTkinter • Download engine: yt-dlp","Benötigt Internetzugang; manche Videos sind regional oder technisch gesperrt.":"Requires internet; some videos are regionally or technically restricted.","Bitte nur Inhalte herunterladen, für die du die entsprechenden Rechte hast.":"Only download content you have permission to use.","Fortschritt":"Progress","Restzeit":"Time remaining","Aktuelle Geschwindigkeit":"Current speed","Vorschau und Videoinformationen":"Preview and video information","Noch kein Video ausgewählt":"No video selected","Füge einen YouTube-Link ein.":"Paste a YouTube link.","Videovorschau":"Video preview","Keine Videoinformationen gefunden":"No video information found","Video wird vorbereitet …":"Preparing video …","Videoinformationen werden geladen …":"Loading video information …","Vorschau nicht verfügbar":"Preview unavailable","Alle Einträge entfernen und aktive Downloads abbrechen?":"Remove all entries and cancel active downloads?","Duplikatschutz aktiv":"Duplicate protection active","Warteschlange leeren":"Clear queue","Protokoll kopiert.":"Log copied.","Protokoll gespeichert.":"Log saved.","Protokoll geleert.":"Log cleared.","Standard":"Default","Keine (wie bisher)":"None (as before)","Kein Download ausgewählt.":"No download selected.","Kein Eintrag ausgewählt.":"No item selected.","Download abgebrochen":"Download canceled","Download abgeschlossen":"Download completed","Download fehlgeschlagen":"Download failed","Download läuft":"Downloading","Download pausiert":"Download paused","Download wird pausiert":"Pausing download","Automatische Download-Reparatur läuft":"Automatic recovery in progress","Abgeschlossen":"Completed","Bereits heruntergeladen":"Already downloaded","Heruntergeladen":"Downloaded","Starten":"Start","Ordner auswählen":"Select folder","Video für Mehrfachdownload auswählen":"Select video for batch download","Als Favorit speichern / Favorit entfernen":"Add/remove favorite"}
# Offline translations are authoritative; never override them with stale cloud cache.
UI_TEXTS = UI_TEXTS | frozenset(ENGLISH) | frozenset(CORE_KEYS)

NATIVE_NAMES = {
    "de": "Deutsch", "en": "English", "es": "Español", "fr": "Français",
    "it": "Italiano", "pt": "Português", "nl": "Nederlands",
    "pl": "Polski", "tr": "Türkçe", "ru": "Русский", "uk": "Українська",
    "ar": "العربية", "bg": "Български", "ro": "Română",
    "ja": "日本語", "ko": "한국어", "hi": "हिन्दी",
    "el": "Ελληνικά", "cs": "Čeština", "sv": "Svenska",
    "da": "Dansk", "fi": "Suomi", "no": "Norsk", "hu": "Magyar",
    "id": "Bahasa Indonesia", "vi": "Tiếng Việt", "th": "ไทย",
    "he": "עברית", "fa": "فارسی", "bn": "বাংলা"
}


class LanguageManager:
    """Asynchronous translations; never blocks or calls Tk from a worker."""

    def __init__(self, folder: Path, language="de"):
        self.cache_file = Path(folder) / "ui_translations_v2.json"
        self.cache = {}
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.cache = {k: v for k, v in data.items() if isinstance(v, dict)}
        except (OSError, ValueError, TypeError):
            pass
        self.cache.setdefault("en", {}).update(ENGLISH)
        for code, translations in CORE_TRANSLATIONS.items():
            self.cache.setdefault(code, {}).update(translations)

        options = {"Deutsch (de)": "de", "English (en)": "en"}
        if GoogleTranslator is not None:
            try:
                all_lang = GoogleTranslator(source="de", target="en").get_supported_languages(as_dict=True)
                for name, code in all_lang.items():
                    if code not in ("de", "en"):
                        options[f"{NATIVE_NAMES.get(code, name.title())} ({code})"] = code
            except Exception:
                pass
        # Offline language packs must remain selectable when the online
        # translation service is missing or unavailable.
        for code in CORE_TRANSLATIONS:
            if code not in options.values():
                options[f"{NATIVE_NAMES.get(code, code)} ({code})"] = code
        self.languages = dict(sorted(options.items(), key=lambda p: (
            0 if p[1] == "de" else 1 if p[1] == "en" else 2, p[0].casefold())))
        self.language = language if language in self.languages.values() else "de"
        self.jobs = queue.Queue()
        self.done = queue.Queue()
        self.pending = set()
        self.lock = threading.Lock()
        self.retry_after = {}
        threading.Thread(target=self._worker, daemon=True,
                         name="NeonTubeTranslation").start()

    def selected_name(self):
        return next((name for name, code in self.languages.items()
                     if code == self.language), "Deutsch (de)")

    def set_language(self, code):
        if code not in self.languages.values():
            return False
        self.language = code
        return True

    def translate(self, original):
        if not isinstance(original, str) or original not in UI_TEXTS or self.language == "de":
            return original
        language = self.language
        result = self.cache.get(language, {}).get(original)
        if isinstance(result, str) and result:
            return result
        if GoogleTranslator is not None and time.monotonic() >= self.retry_after.get(language, 0):
            task = (language, original)
            with self.lock:
                if task not in self.pending:
                    self.pending.add(task)
                    self.jobs.put(task)
        return original

    def _worker(self):
        translators = {}
        while True:
            language, text = self.jobs.get()
            if text in self.cache.get(language, {}):
                with self.lock:
                    self.pending.discard((language, text))
                continue
            try:
                translator = translators.get(language)
                if translator is None:
                    translator = GoogleTranslator(source="de", target=language)
                    translators[language] = translator
                result = translator.translate(text)
                if not isinstance(result, str) or not result.strip():
                    raise ValueError("Empty translation")
                self.done.put((language, text, result.strip(), True))
                time.sleep(0.15)
            except Exception:
                self.done.put((language, text, "", False))

    def collect(self):
        changed = False
        while True:
            try:
                lang, text, translated, ok = self.done.get_nowait()
            except queue.Empty:
                break
            with self.lock:
                self.pending.discard((lang, text))
            if ok:
                if self.cache.setdefault(lang, {}).get(text) != translated:
                    self.cache[lang][text] = translated
                    changed = True
            else:
                self.retry_after[lang] = time.monotonic() + 120
        if changed:
            try:
                tmp = self.cache_file.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.cache, ensure_ascii=False, indent=2),
                               encoding="utf-8")
                tmp.replace(self.cache_file)
            except OSError:
                pass
        return changed

    def _apply(self, widget, attr, custom=False):
        try:
            value = getattr(widget, attr) if custom else widget.cget(attr)
        except Exception:
            return
        if not isinstance(value, str):
            return
        key = "_neontube_i18n_" + attr
        old = getattr(widget, key, None)
        if old and value == old[1]:
            original = old[0]
        elif value in UI_TEXTS:
            original = value
        else:
            if old is not None:
                setattr(widget, key, None)
            return
        translated = self.translate(original)
        if translated == value:
            setattr(widget, key, (original, translated))
            return
        try:
            if custom:
                widget.text = translated
                widget.redraw()
            else:
                widget.configure(**{attr: translated})
            setattr(widget, key, (original, translated))
        except Exception:
            pass

    def refresh_widgets(self, root):
        """Translate visible UI labels; do not touch internal control values."""
        stack = [root]
        while stack:
            widget = stack.pop()
            try:
                stack.extend(widget.winfo_children())
                cls = type(widget).__name__
                if cls in ("NeonSelectionButton", "GradientButton"):
                    self._apply(widget, "text", custom=True)
                elif cls not in ("CTkOptionMenu", "CTkComboBox"):
                    self._apply(widget, "text")
                    if cls == "CTkEntry":
                        self._apply(widget, "placeholder_text")
            except Exception:
                continue
