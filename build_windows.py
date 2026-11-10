# -*- coding: utf-8 -*-
"""Windows portable EXE/ZIP builder for NeonTube Downloader V1.38.0.

The builder is intentionally Windows-only. The built onedir ZIP requires
neither Python nor VLC on the recipient computer.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import zipfile

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = 'NeonTubeDownloader'
VERSION = '1.38.0'
REQUIRED = (
    'app.py', 'downloader.py', 'youtube_api.py', 'favorites.py',
    'duplicate_guard.py', 'clipboard_links.py', 'search_batch.py',
    'requirements.txt', 'THIRD_PARTY_LICENSES.txt', 'assets/app.ico', 'assets/hero_art.png',
    'assets/sidebar_art.png', 'assets/gradient_hot.png',
    'assets/gradient_purple.png', 'assets/preview_mountain.png',
)
MODULES = ('app.py', 'downloader.py', 'youtube_api.py', 'favorites.py',
           'duplicate_guard.py', 'clipboard_links.py', 'search_batch.py')
PACKAGES = ('customtkinter', 'yt_dlp', 'yt_dlp_ejs', 'PIL', 'requests',
            'imageio_ffmpeg', 'PyInstaller')


def validate_project():
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    if missing:
        raise RuntimeError('Dateien fehlen: ' + ', '.join(missing))
    for name in MODULES:
        compile((ROOT / name).read_bytes(), str(ROOT / name), 'exec')
    src = (ROOT / 'app.py').read_text(encoding='utf-8')
    for removed in ('from player_page import', 'PlayerPage(', 'self.player_page',
                    'PLAYER_LIBRARY_FILE'):
        if removed in src:
            raise RuntimeError('Der Videoplayer wurde nicht vollständig entfernt: ' + removed)
    for name in ('player_page.py', 'player_library.py'):
        if (ROOT / name).exists():
            raise RuntimeError('Unnötige Player-Datei vorhanden: ' + name)
    return True


def find_deno():
    candidates = [ROOT / '.runtime' / 'deno.exe']
    found = shutil.which('deno')
    if found: candidates.append(Path(found))
    candidates.append(Path.home() / '.deno' / 'bin' / 'deno.exe')
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.lower() == '.exe':
            return candidate.resolve()
    return None


def find_ffmpeg_pair():
    """Only a complete ffmpeg+ffprobe pair guarantees portable metadata/merging."""
    folder = ROOT / '.runtime' / 'ffmpeg'
    ffmpeg, ffprobe = folder / 'ffmpeg.exe', folder / 'ffprobe.exe'
    if ffmpeg.is_file() and ffprobe.is_file():
        return ffmpeg.resolve(), ffprobe.resolve()
    # External tools may be on PATH in different folders; PyInstaller still
    # places both in one ffmpeg folder in the final portable distribution.
    system_ffmpeg, system_ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if system_ffmpeg and system_ffprobe:
        ffmpeg, ffprobe = Path(system_ffmpeg), Path(system_ffprobe)
        if ffmpeg.is_file() and ffprobe.is_file():
            return ffmpeg.resolve(), ffprobe.resolve()
    return None


def command_for_build(deno: Path, ffmpeg: Path, ffprobe: Path,
                      mode: str = 'onedir', console: bool = False):
    if mode not in ('onedir', 'onefile'):
        raise ValueError('Unbekannter Build-Modus: ' + mode)
    for binary in (deno, ffmpeg, ffprobe):
        if not binary.is_file():
            raise FileNotFoundError(binary)
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
           '--' + mode, '--console' if console else '--windowed',
           '--name', APP, '--icon', str(ROOT / 'assets' / 'app.ico'),
           '--add-data', str(ROOT / 'assets') + os.pathsep + 'assets',
           '--add-data', str(ROOT / 'THIRD_PARTY_LICENSES.txt') + os.pathsep + '.',
           '--add-binary', str(deno) + os.pathsep + 'deno',
           '--add-binary', str(ffmpeg) + os.pathsep + 'ffmpeg',
           '--add-binary', str(ffprobe) + os.pathsep + 'ffmpeg',
           '--collect-all', 'customtkinter',
           '--collect-all', 'yt_dlp',
           '--collect-all', 'yt_dlp_ejs',
           '--collect-all', 'imageio_ffmpeg',
           '--hidden-import', 'PIL._tkinter_finder',
           '--hidden-import', 'search_batch',
           '--hidden-import', 'duplicate_guard',
           '--hidden-import', 'clipboard_links',
           '--distpath', str(ROOT / 'dist'),
           '--workpath', str(ROOT / 'build'),
           '--specpath', str(ROOT), str(ROOT / 'app.py')]
    return cmd


def ensure_dependencies():
    missing = [name for name in PACKAGES if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError('Python-Pakete fehlen: ' + ', '.join(missing) +
                           '. Bitte PORTABLE_ERSTELLEN.bat ausführen.')


def verify_portable_dist(root: Path):
    expected = (root / (APP + '.exe'),)
    for path in expected:
        if not path.is_file():
            raise RuntimeError('Programm-EXE fehlt: ' + str(path))
    files = list(root.rglob('*'))
    for required in ('deno.exe', 'ffmpeg.exe', 'ffprobe.exe', 'THIRD_PARTY_LICENSES.txt', 'hero_art.png',
                     'app.ico'):
        if not any(p.name.lower() == required.lower() for p in files):
            raise RuntimeError('Portable Build unvollständig: ' + required)
    if any(p.name.lower() == 'libvlc.dll' for p in files):
        raise RuntimeError('Unerwartete VLC-Runtime im Paket.')
    return True


def create_portable_zip(root: Path) -> Path:
    dest = ROOT / 'dist' / f'NeonTubeDownloader_Portable_V{VERSION}_Windows.zip'
    with zipfile.ZipFile(dest, 'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as archive:
        for path in sorted(root.rglob('*')):
            if path.is_file():
                archive.write(path, Path(root.name) / path.relative_to(root))
    with zipfile.ZipFile(dest) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError('Defekte ZIP-Datei: ' + bad)
    return dest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('onedir', 'onefile'), default='onedir')
    parser.add_argument('--console', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--portable-zip', action='store_true',
                        help='Erstellt nach onedir eine fertige Portable-Windows-ZIP')
    args = parser.parse_args(argv)
    validate_project()
    if args.check_only:
        print('Quellcode geprüft; Videoplayer entfernt: OK')
        return 0
    if sys.platform != 'win32':
        raise RuntimeError('Eine Windows-EXE muss mit Windows-Python unter Windows gebaut werden.')
    if args.portable_zip and args.mode != 'onedir':
        raise ValueError('Portable-ZIP erfordert den Modus onedir.')
    ensure_dependencies()
    deno = find_deno()
    ff_pair = find_ffmpeg_pair()
    if deno is None:
        raise RuntimeError('Deno fehlt. Bitte PORTABLE_ERSTELLEN.bat nutzen.')
    if ff_pair is None:
        raise RuntimeError('FFmpeg/FFprobe fehlen. Bitte PORTABLE_ERSTELLEN.bat nutzen.')
    cmd = command_for_build(deno, *ff_pair, args.mode, args.console)
    print('Erstelle', args.mode, 'Windows-Build ...', flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)
    dist = ROOT / 'dist'
    exe = (dist / APP / (APP + '.exe') if args.mode == 'onedir'
           else dist / (APP + '.exe'))
    if not exe.is_file():
        raise RuntimeError('PyInstaller hat keine EXE erstellt.')
    if args.mode == 'onedir':
        verify_portable_dist(dist / APP)
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    report = (f'NeonTube Downloader V{VERSION} Windows Build\n'
              f'Erstellt UTC: {datetime.now(timezone.utc).isoformat()}\n'
              f'Python: {sys.version.split()[0]}\n'
              f'Windows: {platform.platform()}\n'
              f'SHA-256 der EXE: {digest}\n'
              'EXE-Test auf einem Windows-Zielgerät empfohlen.\n')
    (dist / 'BUILD_REPORT.txt').write_text(report, encoding='utf-8')
    print('Erstellt:', exe)
    if args.portable_zip:
        portable = create_portable_zip(dist / APP)
        print('Portable ZIP:', portable)
        print('Diese ZIP ist ohne Python-Installation auf Windows-PCs nutzbar.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        print('\nFEHLER:', exc, file=sys.stderr)
        raise SystemExit(1)
