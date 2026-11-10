@echo off
setlocal EnableExtensions
chcp 65001 >nul
pushd "%~dp0"
title NeonTube Downloader - Signierten Windows Portable-Build erstellen

echo ============================================================
echo NeonTube Downloader - Portable-ZIP mit Code-Signatur
 echo ============================================================
echo.
echo Erfordert ein gueltiges Code-Signing-Zertifikat einer anerkannten
 echo Zertifizierungsstelle im Windows-Zertifikatsspeicher und SignTool.
echo Ein selbstsigniertes Zertifikat reicht fuer Smart App Control nicht.
echo.
set /p "NEONTUBE_SIGN_THUMBPRINT=Zertifikat-Fingerabdruck (40 Hex-Zeichen): "
if not defined NEONTUBE_SIGN_THUMBPRINT goto missing
call "%~dp0PORTABLE_ERSTELLEN.bat"
set "RESULT=%ERRORLEVEL%"
set "NEONTUBE_SIGN_THUMBPRINT="
popd
exit /b %RESULT%
:missing
echo Kein Fingerabdruck angegeben. Ohne Zertifikat ist eine
 echo vertrauenswuerdige Signatur nicht moeglich.
pause
popd
exit /b 1
