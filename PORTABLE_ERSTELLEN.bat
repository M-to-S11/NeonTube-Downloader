@echo off
setlocal EnableExtensions
chcp 65001 >nul
pushd "%~dp0"
title NeonTube Downloader - Windows Portable ZIP erstellen
echo ============================================================
echo NeonTube Downloader V1.38.1 - Portable ZIP ohne Videoplayer
echo ============================================================
echo.
where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>&1
    if errorlevel 1 goto no_python
    set "PYTHON_CMD=python"
)
%PYTHON_CMD% -m pip install --upgrade -r requirements.txt "pyinstaller>=6.21"
if errorlevel 1 goto failed
if not exist ".runtime\deno.exe" (
    where deno >nul 2>&1
    if errorlevel 1 (
        echo.
        echo Installiere Deno fuer die portable Version ...
        powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_deno.ps1"
        if errorlevel 1 goto failed
    )
)
if not exist ".runtime\ffmpeg\ffmpeg.exe" (
    where ffmpeg >nul 2>&1
    if errorlevel 1 goto download_ffmpeg
    where ffprobe >nul 2>&1
    if errorlevel 1 goto download_ffmpeg
) else (
    if not exist ".runtime\ffmpeg\ffprobe.exe" goto download_ffmpeg
)
goto ffmpeg_ready
:download_ffmpeg
echo.
echo Lade FFmpeg und FFprobe fuer die portable Version ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_ffmpeg.ps1"
if errorlevel 1 goto failed
if not exist ".runtime\ffmpeg\ffprobe.exe" goto missing_ffprobe
:ffmpeg_ready
if defined NEONTUBE_SIGN_THUMBPRINT (
    echo Signierter Build angefordert. Zertifikat wird vor dem ZIP geprueft.
) else (
    echo Hinweis: Portable-ZIP ohne digitale Signatur kann durch Smart App Control blockiert werden.
)
%PYTHON_CMD% build_windows.py --mode onedir --portable-zip
if errorlevel 1 goto failed
echo.
echo ============================================================
echo Fertig: dist\NeonTubeDownloader_Portable_V1.38.1_Windows.zip
echo Die fertige ZIP entpacken und NeonTubeDownloader.exe starten.
echo Auf dem Ziel-PC sind Python, VLC und Installation nicht noetig.
echo ============================================================
pause
popd
exit /b 0
:missing_ffprobe
echo FFprobe fehlt: .runtime\ffmpeg\ffprobe.exe
goto failed
:no_python
echo Auf diesem BUILD-PC ist Python erforderlich.
echo Auf anderen PCs braucht die spaeter erstellte portable EXE kein Python.
goto failed
:failed
echo.
echo Der Portable-Build wurde nicht abgeschlossen. Details stehen oben.
pause
popd
exit /b 1
