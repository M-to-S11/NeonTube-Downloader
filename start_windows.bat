@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title NeonTube Downloader - Installation und Start

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python wurde nicht gefunden.
        echo Python 3.11+ installieren: https://www.python.org/downloads/
        echo Beim Installieren "Add python.exe to PATH" aktivieren.
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

%PYTHON% -c "import customtkinter, yt_dlp, yt_dlp_ejs, PIL, requests, imageio_ffmpeg" >nul 2>&1
if errorlevel 1 (
    echo Installiere benoetigte Python-Pakete ...
    %PYTHON% -m pip install --upgrade -r requirements.txt
    if errorlevel 1 (
        echo Paketinstallation fehlgeschlagen. Internetverbindung pruefen.
        pause
        exit /b 1
    )
)

if not exist ".runtime\deno.exe" (
    where deno >nul 2>&1
    if errorlevel 1 (
        echo Fuer YouTube wird die JavaScript-Laufzeit Deno benoetigt.
        echo Sie wird offiziell von GitHub geladen, lokal gespeichert und per SHA-256 geprueft.
        choice /C JN /M "Deno jetzt installieren"
        if errorlevel 2 goto run_app
        powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_deno.ps1"
        if errorlevel 1 echo Deno-Installation fehlgeschlagen. Siehe README.md.
    )
)

:run_app
echo Starte NeonTube Downloader ...
%PYTHON% app.py
if errorlevel 1 (
    echo Das Programm wurde mit einem Fehler beendet.
    pause
)
endlocal
