# NeonTube Downloader V1.38.1 – Portable Windows

<img src="assets/neontube_logo.png" alt="NeonTube Downloader Logo" width="72">

NeonTube Downloader ist eine deutschsprachige Windows-App für YouTube-Videos und Audio. Du kannst Links direkt übernehmen, mehrere Downloads verwalten und häufig verwendete Einstellungen als Profil speichern.

**[Portable Windows-ZIP herunterladen](https://github.com/M-to-S11/NeonTube-Downloader/releases/download/v1.38.1/NeonTubeDownloader_Portable_V1.38.1_Windows.zip)** · [Alle Releases](https://github.com/M-to-S11/NeonTube-Downloader/releases)

![Designvorschau der deutschsprachigen NeonTube-Oberfläche mit Linkfeld, Formatwahl, Seitenleiste und Warteschlange](assets/neontube-design.webp)

*Designvorschau des Download-Bereichs. Die Darstellung kann von der veröffentlichten Windows-Version abweichen.*

## Installation und erster Start

1. Lade unter **Assets** die Datei `NeonTubeDownloader_Portable_V1.38.1_Windows.zip` herunter. Die automatisch erzeugten **Source code**-Archive enthalten das Projekt zum Selberbauen.
2. Klicke in Windows mit der rechten Maustaste auf die ZIP und wähle **Alle extrahieren**.
3. Öffne den entpackten Ordner `NeonTubeDownloader` und starte `NeonTubeDownloader.exe`. Lasse den Ordner `_internal` neben der EXE.
4. Öffne in der Seitenleiste **Download**. Unter **Speicherort → Durchsuchen** legst du fest, wo deine Dateien gespeichert werden.

Die portable Ausgabe ist für **Windows x64** gebaut. Python und ein Installationsassistent sind für diese Ausgabe nicht erforderlich. Die EXE ist unsigniert. Windows Smart App Control kann den Start deshalb blockieren.

## Ein Video oder eine Audiodatei herunterladen

1. Kopiere die Adresse des gewünschten YouTube-Videos. Klicke in NeonTube auf **Link einfügen** oder füge den Link direkt ins Feld ein. Du kannst mehrere Links zeilenweise einfügen.
2. Wähle **Video (MP4)** oder **Nur Audio (MP3)**. Für Video wählst du die gewünschte Qualität, soweit YouTube sie bereitstellt. Im Audiomodus kannst du unter **Audioformat** zwischen **MP3**, **M4A** und **WAV** wählen.
3. Aktiviere **Playlist herunterladen**, wenn du eine ganze Playlist übernehmen möchtest.
4. Klicke auf **Download starten**. Rechts in der Warteschlange siehst du Status, Fortschritt, Geschwindigkeit und Restzeit, sobald diese Werte verfügbar sind.
5. Markiere bei Bedarf einen Eintrag zum Pausieren, Fortsetzen oder Abbrechen. Fertige Dateien findest du im gewählten Speicherordner oder über **Verlauf**.

Bitte lade nur Inhalte herunter, für die du die nötigen Rechte oder eine entsprechende Erlaubnis hast.

## Integrierte Funktionen

| Bereich | Was du damit machen kannst |
| --- | --- |
| Link-Erkennung und Vorschau | Kopierte YouTube-Links nach Rückfrage übernehmen. Die Vorschau zeigt verfügbare Metadaten wie Titel und Vorschaubild. Das Übernehmen eines Links startet noch keinen Download. |
| Video, Audio und Playlists | Einzelvideos und Playlists verarbeiten. MP4-Video bis zur verfügbaren Qualität, mit Auswahl bis 4K, oder Audio als MP3, M4A oder WAV speichern. |
| Warteschlange | Mehrere Downloads gleichzeitig ausführen, einzelne Einträge pausieren, fortsetzen, abbrechen oder entfernen. Fortschritt, Dateigröße, Geschwindigkeit und Restzeit verfolgen. |
| Wiederholungsversuche | Bei vorübergehenden Verbindungsfehlern erneut versuchen. Vorhandene Teildateien werden weiterverwendet, soweit der Download dies unterstützt. |
| Duplikatschutz | Doppelte Einträge in der Warteschlange vermeiden. Bei bereits vorhandenen Downloads desselben Formats fragt NeonTube vor einem erneuten Download nach. |
| YouTube-Suche | Mit eigenem API-Schlüssel nach Videos suchen, Vorschaubilder und Kanalinformationen sehen, weitere Ergebnisse laden und mehrere Treffer in die Warteschlange übernehmen. |
| Favoriten und Verlauf | Suchtreffer über das Herz merken, gespeicherte Favoriten erneut aufrufen und abgeschlossene Downloads im Verlauf finden. |
| Speicherordner und Profile | Formate und Qualität als Profil speichern. Neue Downloads optional nach Kanal, Playlist oder Dateiformat in Unterordner einsortieren. |
| Download-Protokoll | Meldungen der aktuellen Sitzung lesen, kopieren oder als Datei speichern. |

## YouTube-Suche und Favoriten einrichten

1. Aktiviere in der [Google Cloud Console](https://console.cloud.google.com/apis/library/youtube.googleapis.com) die **YouTube Data API v3** für dein Google-Cloud-Projekt und erstelle dort einen API-Schlüssel.
2. Öffne in NeonTube **Einstellungen → YouTube Data API v3**, füge den Schlüssel ein und klicke auf **Einstellungen speichern**.
3. Wechsle links zu **YouTube-Suche**. Über **Link übernehmen** legst du einen Treffer ins Linkfeld. Mit dem Herz speicherst du ihn unter **Favoriten**. Über die Kontrollkästchen kannst du mehrere Treffer auswählen und gemeinsam in die Warteschlange legen.

Für Downloads über einen bekannten YouTube-Link ist kein API-Schlüssel nötig. Einstellungen, Favoriten und Verlauf speichert die App im Benutzerprofil unter `%APPDATA%\NeonTubeDownloader`.

## Bei Start- oder Downloadproblemen

| Situation | Was du prüfen kannst |
| --- | --- |
| Beim Start fehlen Dateien | Entpacke die ZIP erneut und starte die EXE aus dem vollständigen Ordner mit `_internal`. |
| Die YouTube-Suche meldet einen API-Fehler | Prüfe, ob die API im richtigen Google-Cloud-Projekt aktiviert ist und ob der dort erstellte Schlüssel in NeonTube gespeichert wurde. |
| Ein Download bricht ab | Öffne das **Download-Protokoll** und prüfe die konkrete Fehlermeldung. Bei Speicherfehlern kontrolliere den freien Platz und die Schreibrechte für den Zielordner. |
| Die Datei liegt in einem Unterordner | Prüfe unter **Einstellungen → Downloads sortieren**, ob nach Kanal, Playlist oder Format einsortiert wird. |

## Technik und eigene Builds

- **CustomTkinter** stellt die Oberfläche bereit. **yt-dlp** verarbeitet die Medienlinks, **FFmpeg** und **FFprobe** übernehmen Medienverarbeitung und Analyse. **Deno** unterstützt die JavaScript-Ausführung für die YouTube-Extraktion.
- Für einen eigenen Windows-Build mit installiertem Python führe `PORTABLE_ERSTELLEN.bat` aus. Die fertige ZIP landet im Ordner `dist`.
- Im Repository baut **Actions → Portable Windows-Version → Run workflow** die in `build_windows.py` hinterlegte Version. Ein passender Git-Tag wie `v1.38.1` startet den Workflow ebenfalls. Bereits veröffentlichte Versionen werden übersprungen.
