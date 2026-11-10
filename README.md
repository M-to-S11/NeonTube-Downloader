# NeonTube Downloader

[Portable Windows-Version unter Releases](https://github.com/M-to-S11/NeonTube-Downloader/releases)

Neue Versionen lassen sich über **Actions → Portable Windows-Version → Run workflow** veröffentlichen. Der Workflow verwendet die Versionsnummer in `build_windows.py` und baut die portable ZIP auf Windows x64. Alternativ startet ein passender Git-Tag wie `v1.38.1` den Build. Bereits veröffentlichte Versionen werden übersprungen.

# NeonTube Downloader V1.38.1 – Ohne Videoplayer + Portable Windows

Die Videoplayer- und Playlist-Funktion wurde **vollständig aus dem Programm entfernt**.
Es ist keine Installation von VLC oder `python-vlc` mehr erforderlich.
Die übrigen Funktionen (Video/MP3-Downloads, Suche, Favoriten, Reparatur,
Mehrfachauswahl, Duplikatschutz, Link-Erkennung und Ordnersortierung) bleiben.

## Portable Windows-Version erzeugen

Diese herunterladbare ZIP **enthält Quellcode und einen vollständigen Portable-Builder**, noch **keine vorgefertigte Windows-EXE**. Eine Windows-EXE kann mit PyInstaller nur auf Windows erstellt werden.

1. ZIP entpacken.
2. Auf **deinem Windows-PC mit Python** `PORTABLE_ERSTELLEN.bat` doppelklicken.
3. Das Skript installiert die Build-Abhängigkeiten, lädt Deno und FFmpeg/FFprobe (mit SHA-256-Prüfung), erzeugt `NeonTubeDownloader.exe` und verpackt den **vollständigen** Programmordner.
4. Die fertige ZIP befindet sich unter `dist\NeonTubeDownloader_Portable_V1.38.1_Windows.zip`.
5. Diese **fertige** ZIP auf einen anderen Windows-10/11-64-Bit-PC kopieren, entpacken und `NeonTubeDownloader.exe` starten. **Kein Python, kein VLC und kein Installer** erforderlich.

**Wichtig:** Nur die EXE aus dem fertigen `NeonTubeDownloader`-Ordner herauszukopieren reicht nicht; die mitgelieferten `_internal`-Dateien werden benötigt. Für eine echte portable Ausführung immer den ganzen Ordner verteilen. Der Build braucht Internetzugang für externe Pakete. Eine unsignierte EXE kann durch Windows Smart App Control blockiert werden.

Die Einstellungen, Favoriten und der Verlauf bleiben wie bisher in `%APPDATA%\NeonTubeDownloader` erhalten. Gespeicherte Playlist-Daten aus einer älteren Player-Version werden **nicht gelöscht**, aber von dieser Version nicht mehr verwendet.

# NeonTube Downloader V1.36.0 – Automatische Ordnerverwaltung

**Neu:** Unter Einstellungen → Downloads sortieren wählst du, ob die neuen
Downloads im Standardordner bleiben oder nach Kanal, Playlist bzw. Format
in automatisch erstellte Unterordner kommen. Die frühere Ablage bleibt als
Standard aktiv. Die komplette Anleitung steht weiter unten.

---

# Korrektur V1.35.1 – Videovorschau

Die Vorschau zeigt Aufrufzahlen aus der YouTube Data API v3 (Text) und yt-dlp (Zahl) jetzt zuverlässig an. Ungültige oder fehlende Werte zeigen „Videovorschau“. Keine Änderungen am Design oder Download-Verhalten.

# Neuerung V1.35.0 – Automatische Link-Erkennung

NeonTube erkennt gültige YouTube-Links, wenn diese während der laufenden Sitzung in die Windows-Zwischenablage kopiert werden. Sobald das Programmfenster aktiv ist, kannst du per Rückfrage festlegen, ob die Links in das bestehende Eingabefeld übernommen werden. Es startet dadurch **kein** Download. Bereits bei Programmstart vorhandene Zwischenablage-Inhalte werden ignoriert. Du kannst weiterhin auf „Link einfügen“ klicken. Keine zusätzliche Freigabe, kein API-Schlüssel und keine Designänderung erforderlich.

## Neu in Version 1.34.0 – Doppelte Downloads erkennen

- NeonTube erkennt dasselbe YouTube-Video über verschiedene Linkformen
  (youtube.com/watch, youtu.be, Shorts, Live, music.youtube.com).
- Schon laufende/pausierte/ausstehende Downloads desselben Videos und
  Dateiformats werden nicht nochmals in die Warteschlange gestellt.
- Bereits heruntergeladene Videos werden anhand des Verlaufs und einer noch
  vorhandenen MP4-/MP3-/Audio-Datei gefunden. Du kannst dann ausdrücklich
  entscheiden, ob du sie dennoch erneut herunterladen möchtest.
- Einträge im Verlauf, deren Dateien gelöscht oder verschoben wurden,
  blockieren den erneuten Download nicht. Alte `.part`-Pfade werden bei
  vorhandenen Enddateien mit einer `[Video-ID]` im Namen aufgelöst.
- Die Prüfung funktioniert bei einzelnen Links, Favoriten und Mehrfachauswahl.
  Bei mehreren Videos erscheint höchstens eine gemeinsame Rückfrage.
- Unterschiedliche Medienvarianten (MP4 vs. MP3, unterschiedliche Audio-Codecs)
  werden als eigenständige Downloads behandelt. Qualität und Zielordner können
  variieren, daher wird vor einer erneuten gleichen Medienvariante gefragt.
- Bereits vorhandene Dateien werden von NeonTube nicht automatisch gelöscht
  oder überschrieben; yt-dlp bleibt für den Dateinamen zuständig.
- Die Erkennung kompletter Playlists aus historischen Einzeldateien ist aus
  Sicherheitsgründen nicht aktiv. Bereits wartende Playlists werden erkannt.
- Design, Logos und sämtliche bisherigen Funktionen sind unverändert.

---

## Neu in Version 1.33.0 – Mehrfachauswahl in der YouTube-Suche

- Videokarten haben eine kleine Checkbox unter dem Favoriten-Herz.
- Über die schmale Auswahlleiste sind „Alle auswählen“ und „Auswahl aufheben“ verfügbar.
- „Zur Warteschlange (N)“ übernimmt alle markierten, bereits geladenen Videos gleichzeitig.
- Die vorhandenen Download-Einstellungen (MP4/MP3, Qualität, Zielordner und parallele Downloads) gelten für die gesamte Auswahl.
- Weitere Ergebnisse können nachgeladen werden, ohne die Auswahl der ersten Seite zu verlieren.
- Eine neue Suche setzt die Auswahl zurück. Duplikate in Suchergebnissen werden ignoriert.
- Die normale Einzelvideo-Schaltfläche „Starten“, Favoriten und die intelligente Download-Reparatur bleiben erhalten.
- Designs und Bilder aus V1.32.0 wurden nicht geändert.

Hinweis: Die Windows-Oberfläche und echte Downloads bitte vor einer Weitergabe zusätzlich testen.

---

## Neu in Version 1.32.0 – Intelligente Download-Reparatur

NeonTube Downloader V1.32.0 – Intelligente Download-Reparatur

- Begrenzt auf 3 vollständige Versuche; yt-dlp versucht Einzelverbindungen/Fragmente separat erneut.
- Automatische Wiederholung ausschließlich bei typischen temporären Netzproblemen (z. B. Timeout, Reset, Bad Record MAC, HTTP 5xx).
- 2 / 5 Sekunden gestaffelte Wartezeit bei erneuten Verbindungsversuchen.
- Während der Wiederholung wird auf eine parallele Fragmentverbindung reduziert.
- Teil-Downloads (.part) bleiben erhalten; yt-dlp setzt sie fort, soweit Server/Format dies unterstützen.
- Kein automatisches Wiederholen bei 401/403/404/429, Privatvideos, fehlenden Rechten, beschädigter Zertifikatsprüfung oder lokalen Festplattenproblemen.
- Reparaturstatus und Countdown im bestehenden Warteschlangenstatus/Restzeitfeld; Log meldet Versuche.
- Pausieren, Abbrechen und Schließen sind auch während der Wartezeit möglich.
- Oberfläche, Logo, Hero-Banner, Navigation und Fensterlayout unverändert.

Hinweis: Netzwerk- oder YouTube-Sperren können nicht garantiert behoben werden. Download-Abbrüche während FFmpeg-Verarbeitung werden nicht automatisch neu begonnen.

---

# NeonTube Downloader V1.32.0 – ohne Updatefunktionen und ohne Profil-Karte unten rechts

Diese Version basiert auf der letzten bewährten Oberfläche **V1.23**, bevor die Updateprüfung eingeführt wurde. Die Download-Engine (`downloader.py`) und sämtliche vorhandenen Designbilder sind unverändert.

## Neu in Version 1.31.2 – korrigiertes eigenes Logo im Hero-Banner

- Das komplette Banner wurde neu als Neon-Wellen-Artwork erstellt. Das alte
  rote YouTube-Symbol ist **vollständig aus der Bilddatei entfernt** und nicht
  lediglich durch das neue Logo verdeckt.
- Das vom Nutzer bereitgestellte türkisfarbene NeonTube-Logo ist integriert.
- Auch Header, Fenster-/EXE-Icon und „Über“-Seite verwenden dieses Logo.
- Die optionalen Asset-Build-Skripte überschreiben das Markenlogo nicht mehr.
- Bestehende API-Einstellungen, Favoriten und Download-Funktionen bleiben erhalten.
- Vor einer Verteilung bitte die App auf Windows starten und Layout/Downloads prüfen.

## Seit Version 1.31.0 – Favoriten

- Ein neuer Navigationspunkt **Favoriten** mit Herzsymbol erscheint links.
- In der YouTube-Suche kann ein Video mit dem Herz oben rechts auf seiner Karte
  gespeichert oder wieder entfernt werden.
- Favoriten zeigen Vorschaubilder, Videotitel, Kanal und Dauer; über
  **Link übernehmen** und **Starten** werden sie wie Suchtreffer verwendet.
- Gespeicherte Videos bleiben nach dem Schließen des Programms erhalten;
  zuletzt gemerkte Videos stehen oben. Sie liegen unter
  `%APPDATA%\NeonTubeDownloader\favorites.json`.
  Für die Favoritenliste ist keine API-Anfrage erforderlich; Vorschaubilder
  werden aus dem lokalen Cache verwendet oder einzeln nachgeladen.
- Duplikate werden verhindert. Der API-Schlüssel bleibt wie bisher getrennt.
- Das übrige Layout, die Download-Warteschlange und das Download-Verhalten
  sind unverändert. Windows-GUI und echte Downloads bitte vor Veröffentlichung testen.

## Seit Version 1.30.0 – YouTube-Suche optimiert

- Größere 16:9-Vorschaubilder (160 × 90) und deutlichere, mehrzeilige Videotitel.
- Vollständiger Titel als Mouseover-Hinweis; HTML-Sonderzeichen in
  API-Titeln und Kanalnamen werden korrekt dargestellt.
- Suchergebnisse passen sich der Fenstergröße an (1, 2 oder 3 Spalten).
- Trefferanzahl pro Suchaufruf: 6 / 12 / 24; die Auswahl wird gespeichert.
- Nachladen weiterer Ergebnisse: Bilder vorheriger Seiten werden auch
  während des Nachladens weiter abgerufen.
- „Link übernehmen“ übernimmt den Link; „Starten“ legt das Video über den
  bestehenden yt-dlp-Downloadpfad in die Warteschlange.
- Bestehende Einstellungen, API-Schlüssel, Downloads, Verlauf, Log und
  Glas-/Neon-Design bleiben erhalten. 13+ automatisierte Tests ohne Netzwerk.
- Bitte unter Windows GUI, Downloads und EXE zusätzlich ausprobieren.

## Seit Version 1.29.0 – YouTube-API und bessere Netzwerkstabilität

Diese Version basiert auf **V1.28.8 AutoScroll** und behält das Glas-/Neondesign,
Einstellungen im Hauptfenster, Warteschlange, Verlauf, Profile und Log bei.

- **YouTube-Suche:** Neuer Eintrag „YouTube-Suche“ links; Titel, Kanal, Laufzeit,
  Vorschaubilder, „Link übernehmen“, „Starten“ und „Weitere Ergebnisse“.
- **YouTube Data API v3:** Verwendet die offizielle Google-API für Suche und
  Videometadaten; wenn Metadaten abrufbar sind, muss yt-dlp sie nicht separat ermitteln.
- **API-Schlüssel:** Unter **Einstellungen → YouTube Data API v3** eigenen
  API-Schlüssel eingeben und auf **Einstellungen speichern** klicken.
  Unter Windows wird der Schlüssel im Profil des aktuellen Benutzers durch **DPAPI**
  verschlüsselt gespeichert unter `%APPDATA%\NeonTubeDownloader\youtube_api_key.dat`.
  Ein eventuell gesetztes `YOUTUBE_API_KEY` in der Umgebung hat Vorrang.
- **Download-Resilienz:** Bei typischen Verbindungsunterbrechungen sind zusätzliche
  Wiederholungsversuche möglich; yt-dlp setzt vorhandene Teildateien fort.
  Reduzierte Fragment-Parallelität (2 statt 4), längere Timeouts und mehr
  Fragment-/Extractor-Retries; Hinweis im Download-Log.
- **Ohne API-Schlüssel:** Link-Downloads arbeiten wie bisher (yt-dlp). Nur die
  YouTube-Suche erfordert einen Schlüssel.
- **Einschränkungen:** Eine YouTube-API ersetzt den Download über yt-dlp **nicht**,
  und verbessert nicht automatisch jede Download-Situation. YouTube-Sperren,
  regionale Einschränkungen und Rechte müssen weiterhin beachtet werden.

### Eigenen YouTube-API-Schlüssel erhalten

1. https://console.cloud.google.com/ öffnen und Projekt anlegen.
2. **APIs und Dienste → Bibliothek → YouTube Data API v3 → Aktivieren**.
3. **APIs und Dienste → Anmeldedaten → API-Schlüssel erstellen**.
4. Für die offizielle Data API geeignete API-/Dienst-Beschränkungen festlegen.
   Eine IP-/HTTP-Referrer-Beschränkung kann Desktop-Clients blockieren;
   diese muss zur eigenen Bereitstellung passen.
5. Den Schlüssel **nicht** in Quellcode, ZIPs oder öffentlich verteilte EXEs schreiben.
   Jeder Benutzer benötigt seinen eigenen Schlüssel oder einen eigenen
   abgesicherten Vermittlungsdienst. Die Suche verbraucht API-Kontingent.
6. Im Programm den Schlüssel unter Einstellungen speichern und die Suche öffnen.

**Wichtig:** Die offizielle YouTube Data API v3 liefert keine MP3-/MP4-Dateien.
Bitte nur Medien herunterladen, für die Nutzungsrechte und die
Plattformbedingungen dies erlauben.

### Testen und Weitergeben

- `start_windows.bat` startet die Python-Version unter Windows.
- `build_exe.bat` baut nach Installation der Abhängigkeiten eine Windows-EXE.
- `build_setup.bat` baut optional ein Inno-Setup-Installationsprogramm.
- Für eine portable Veröffentlichung muss der gesamte Ordner
  `dist\NeonTubeDownloader` weitergegeben werden.
- **Python / Deno / yt-dlp / FFmpeg:** Die Windows-Packaging-Schritte müssen
  weiterhin auf einem Windows-PC getestet werden; die Quellen wurden hier
  mit Syntax-, Unit- und Build-Prüfungen überprüft, nicht als Windows-EXE gestartet.

## Funktionen

- MP4-Video und MP3-Audio mit `yt-dlp`
- Vorschau mit Vorschaubild, Qualität und Videotitel
- Mehrere gleichzeitige Downloads, Warteschlange, Pausieren, Fortsetzen und Abbrechen
- Fortschritt, Dateigröße, Downloadgeschwindigkeit und Restzeit
- Download-Verlauf, Speicherordner öffnen, Profile und Einstellungen
- Dunkles Neon-/Glassmorphism-Design mit CustomTkinter
- Erstellung einer portablen Windows-EXE und eines Installers

## Bewusst nicht enthalten

- Keine automatische oder manuelle `yt-dlp`-Versionsprüfung im Programm
- Keine GitHub-Release-Prüfung oder Update-Benachrichtigungen
- Kein Programm-Update-Assistent, keine Update-Build-Schaltfläche
- Keine Installation oder Downloads von Updates beim Programmstart

Die zum Bauen benötigten Python-Abhängigkeiten werden nur beim **manuellen** Ausführen des Build-Skripts installiert, nicht von der gestarteten Anwendung.

## Unter Windows starten (Python-Version)

1. ZIP vollständig entpacken.
2. Im Ordner `NeonTube_Downloader` die Datei `start_windows.bat` starten.
3. Beim ersten Start werden ggf. die benötigten Abhängigkeiten eingerichtet.

## Windows-EXE und Installationsassistent erstellen

1. Aktuelle funktionierende Version zuerst sichern.
2. Im entpackten Projekt `build_exe.bat` ausführen.
3. Ausgabe: `dist\NeonTubeDownloader\NeonTubeDownloader.exe` (gesamten Ordner mitnehmen).
4. Optional: Inno Setup 6 installieren und `build_setup.bat` ausführen.
5. Ausgabe: `dist\installer\NeonTubeDownloader_Setup_V1_31_0.exe`.

Bestehende Einstellungen und der Verlauf bleiben unter `%APPDATA%\NeonTubeDownloader` erhalten. Alte Update-Konfigurationswerte werden von dieser Version ignoriert; andere Werte und Verlaufsdateien werden nicht gelöscht.

Für Video-/Audiokonvertierung werden FFmpeg und für aktuelle YouTube-Extraktion Deno benötigt. Die Windows-Build-Skripte bündeln diese Abhängigkeiten soweit verfügbar/eingerichtet. Ein vollständiger Windows-GUI- und EXE-Build-Test muss auf einem Windows-PC erfolgen.

Bitte nur Inhalte herunterladen, für die du die entsprechenden Nutzungsrechte besitzt.


## Änderung V1.28.1
- **Nur** die kleine Profil-Karte am unteren rechten Rand der Download-Seite entfernt.
- Der Menüpunkt **Profile** links und die vollständige Profilverwaltung bleiben erhalten.
- In V1.28.1 blieben Zahnrad und Einstellungen erhalten (das Zahnrad wird erst in V1.28.4 entfernt).
- Keine Ersatzgrafik oder andere Karte am entfernten Platz.
- Download-Engine (`downloader.py`) unverändert.


## Änderung V1.28.4
- Nur das Zahnrad oben rechts aus dem Programmkopf entfernt.
- **Einstellungen** in der linken Seitenleiste bleiben unverändert und funktionieren weiterhin.
- Die Profilkarte unten rechts bleibt wie in V1.28.1 entfernt; der linke Profil-Menüpunkt bleibt.
- Keine zusätzlichen Updatefunktionen. Die Download-Engine bleibt unverändert.

## Änderung V1.28.4 – kompaktere Bedienelemente
- Nur die vom Nutzer markierten Bedienelemente im Download-Bereich verkleinert: Link-Leiste und Einfügen-Button, MP4-/MP3-Auswahl, Playlist-Häkchen, Qualitäts-/Audio-/Speicherfelder sowie Download starten/Pausieren/Abbrechen.
- Rund 10–15 % kleinere Höhen und Schriftgrößen, mit angepassten Abständen innerhalb der Optionskarte.
- Vorschau, Fortschrittsbereich, Warteschlange, Verlauf, Profile links und Einstellungen links sind unverändert.
- Zahnrad oben rechts und Profilkarte unten rechts bleiben entfernt. Keine Update-Funktion.
- Download-Engine (`downloader.py`) ist unverändert.

Für bereits installierte Windows-EXE neu mit `build_exe.bat` und `build_setup.bat` bauen.


## V1.28.4 – noch etwas kompakter
Die Bedienelemente des Download-Bereichs wurden ausgehend von V1.28.3 um weitere ca. 5–8 % in der Höhe verkleinert. Die Download-Optionen-Karte ist nun etwas niedriger, damit kein unnötiger Leerraum entsteht. Vorschaubild, Fortschrittsbereich, Warteschlange, Verlauf, linkes Menü und Download-Engine sind unverändert. Es gibt weiterhin keine eingebauten Updatefunktionen, kein Zahnrad oben rechts und keine Profilkarte unten rechts.

## V1.28.5 – Einstellungen im Hauptbereich

Die Seite „Einstellungen“ öffnet sich jetzt direkt im Hauptbereich wie „Profile“, ohne eigenes Fenster. Alle bisherigen Optionen (parallele Downloads, Downloadordner und Cookies-Datei) sowie ihre Speicherung bleiben erhalten. Die kompakte Download-Oberfläche und die zuvor entfernten Elemente bleiben unverändert.

## V1.28.7 – Integriertes Download-Protokoll

Der „Log“-Knopf im Fortschrittsbereich öffnet eine eigene Seite **im Hauptfenster**. Kein separates Log-Fenster mehr. Das Protokoll sammelt echte Download-Ereignisse dieser Sitzung (Start, Statuswechsel, Fortschrittsmeilensteine je 10 %, Erfolg, Warnung und Fehler). Schaltflächen: **Alle Ereignisse / Downloads / Fehler**, **Kopieren**, **Speichern** als UTF-8-Text, **Leeren** mit Bestätigung sowie **Zurück zum Download**. Beim Filtern und Exportieren werden nur die gewählten Kategorien verwendet. Die jüngsten 100 Treffer sind sichtbar, maximal 500 Ereignisse werden im Arbeitsspeicher behalten. Es werden keine Logs automatisch auf Festplatte gespeichert und keine Cookies oder vollständigen Download-URLs ins Protokoll geschrieben.

**Bewusst unverändert:** Download-Engine `downloader.py`, kompaktes Download-Design, Warteschlange, Verlauf, Profile, Einstellungen im Hauptbereich, kein Zahnrad oben rechts, keine Profilkarte unten rechts, keine Update-Funktion.


## V1.28.8 – Automatisches Scrollen im Download-Protokoll

Die neuesten Protokoll-Einträge stehen oben. Solange die Liste ganz oben steht, folgt die Anzeige automatisch neuen Meldungen. Beim manuellen Scrollen nach unten zu älteren Einträgen wird Auto-Scroll pausiert, und die Position bleibt auch bei neu eintreffenden Meldungen erhalten. Sobald man wieder nach oben scrollt, wird Auto-Scroll automatisch reaktiviert. Ein dezenter Status im Protokoll zeigt an, ob die Funktion aktiv oder pausiert ist. Beim Öffnen des Logs und beim Wechsel des Filters erscheint der neueste Eintrag oben.

Die Download-Engine, sonstige UI und gespeicherte Einstellungen bleiben unverändert.


## Neu in 1.36.0 – Automatische Ordnerverwaltung

In **Einstellungen → Downloads sortieren** kann die Ablage neuer Downloads
festgelegt werden. Nach der Wahl auf **Einstellungen speichern** klicken.

- **Keine (wie bisher)** (Standard): Videos werden direkt im gewählten Downloadordner gespeichert.
- **Nach Kanal**: Ein Unterordner je YouTube-Kanal, z. B. `Downloads/Kanalname/Video.mp4`.
- **Nach Playlist**: Ein Unterordner je Playlist. Einzelvideos landen unter `Einzelvideos`.
- **Nach Dateiformat**: z. B. `Downloads/MP4/` oder `Downloads/MP3/`, bei anderem Audioformat unter dessen Namen.

Alle vier Einstellungen wirken nur auf **neu eingereihte** Downloads, nicht auf
bereits laufende oder vorhandene Dateien. Ordner werden beim Download angelegt.
Das automatische Fortsetzen von Teildateien und FFmpeg bleiben unverändert.
Die Download-History und die Duplikaterkennung funktionieren auch mit Unterordnern.
Bei einem Playlist-Download ist `Playlist herunterladen` weiterhin notwendig.

Bestehende Einstellungen, API-Schlüssel und Favoriten bleiben erhalten.
