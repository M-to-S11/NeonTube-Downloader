"""Voluntary, standards-compliant Authenticode signing for NeonTube Windows builds.

This is NOT a Smart App Control bypass. A certificate from a trusted issuer is
required. Existing valid signatures on third-party components are preserved.
No credentials, certificate, or private keys are bundled with the project.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

THUMBPRINT_RE = re.compile(r"^[a-fA-F0-9]{40}$")
PE_EXTENSIONS = {'.exe', '.dll', '.pyd'}
TIMESTAMP_SERVER = 'http://timestamp.digicert.com'


def normalize_thumbprint(text: str) -> str:
    """Accept only a public 40-hex-digit certificate thumbprint."""
    value = ''.join(str(text).split())
    if not THUMBPRINT_RE.fullmatch(value):
        raise ValueError('Zertifikat-Fingerabdruck muss aus 40 Hex-Zeichen bestehen.')
    return value.upper()


def find_signtool() -> Path:
    located = shutil.which('signtool.exe') or shutil.which('signtool')
    if located:
        return Path(located)
    root = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))
    kits = root / 'Windows Kits' / '10' / 'bin'
    candidates = sorted(kits.glob('*/x64/signtool.exe'), reverse=True)
    if not candidates:
        candidates = sorted(kits.glob('*/x86/signtool.exe'), reverse=True)
    if not candidates:
        raise RuntimeError('SignTool fehlt. Bitte Windows SDK installieren (Signing Tools).')
    return candidates[0]


def run_signtool(args: list[str], *, check: bool = True):
    return subprocess.run(args, check=check, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def is_trusted_signed(signtool: Path, file: Path) -> bool:
    result = run_signtool([str(signtool), 'verify', '/pa', '/q', str(file)],
                          check=False)
    return result.returncode == 0


def find_pe_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob('*') if p.is_file() and
                  p.suffix.lower() in PE_EXTENSIONS)


def sign_portable(folder: Path, thumbprint: str, *, signtool: Path | None = None,
                  timestamp_server: str = TIMESTAMP_SERVER) -> dict[str, int]:
    """Sign untrusted/unsigned PE files from the onedir distribution in place.

    If any signing or trust verification fails, abort rather than distribute an
    archive that falsely claims Smart App Control compatibility.
    """
    if sys.platform != 'win32':
        raise RuntimeError('Authenticode-Code-Signierung nur unter Windows möglich.')
    thumbprint = normalize_thumbprint(thumbprint)
    folder = Path(folder)
    if not (folder / 'NeonTubeDownloader.exe').is_file():
        raise RuntimeError('Die gebaute NeonTubeDownloader.exe wurde nicht gefunden.')
    tool = signtool or find_signtool()
    paths = find_pe_files(folder)
    if not paths:
        raise RuntimeError('Keine Windows-Binärdateien zum Signieren gefunden.')
    stats = {'already_trusted': 0, 'newly_signed': 0, 'total': len(paths)}
    for binary in paths:
        if is_trusted_signed(tool, binary):
            stats['already_trusted'] += 1
            continue
        args = [str(tool), 'sign', '/sha1', thumbprint, '/fd', 'SHA256',
                '/tr', timestamp_server, '/td', 'SHA256', str(binary)]
        signed = run_signtool(args, check=False)
        if signed.returncode != 0:
            detail = (signed.stderr or signed.stdout or 'Unbekannter Fehler').strip()
            raise RuntimeError(f'Signierung fehlgeschlagen: {binary.name}: {detail[:700]}')
        if not is_trusted_signed(tool, binary):
            raise RuntimeError(f'Signatur nicht vertrauenswürdig: {binary.name}. '
                               'Ein Zertifikat einer anerkannten CA ist erforderlich.')
        stats['newly_signed'] += 1
    # Verify every PE file again. This is separate from the signing loop on purpose.
    failed = [str(p.relative_to(folder)) for p in paths if not is_trusted_signed(tool, p)]
    if failed:
        raise RuntimeError('Nicht vertrauenswürdig signierte Dateien: ' + ', '.join(failed[:10]))
    return stats
