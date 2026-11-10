@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
if not exist "dist\NeonTubeDownloader\NeonTubeDownloader.exe" (
   echo Zuerst build_exe.bat ausfuehren!
   pause
   exit /b 1
)
set "ISCC="
where ISCC.exe >nul 2>&1
if not errorlevel 1 set "ISCC=ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
   echo Inno Setup 6 fehlt. Installiere es von https://jrsoftware.org/isinfo.php
   echo Danach build_setup.bat erneut starten.
   pause
   exit /b 1
)
"%ISCC%" "NeonTubeDownloader_Setup.iss"
if errorlevel 1 (
   echo Installer-Build fehlgeschlagen!
   pause
   exit /b 1
)
echo.
echo Fertig! Installer unter dist\installer\NeonTubeDownloader_Setup_V1_32_0.exe
pause
