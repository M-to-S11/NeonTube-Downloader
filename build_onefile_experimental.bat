@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
echo EXPERIMENTELL: Single-EXE-Build. Empfohlen ist build_exe.bat (Ordner-Modus).
echo Vorher build_exe.bat einmal ausfuehren, damit alle Abhaengigkeiten bereitstehen.
where py >nul 2>&1
if not errorlevel 1 (
   py -3 build_windows.py --mode onefile
) else (
   python build_windows.py --mode onefile
)
if errorlevel 1 (
   echo Build fehlgeschlagen.
) else (
   echo Single-EXE: dist\NeonTubeDownloader.exe
)
pause
