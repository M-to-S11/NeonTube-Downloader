# Requires Windows 10/11 x64; downloads FFmpeg+FFprobe with official SHA256 verification.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if (-not [Environment]::Is64BitOperatingSystem) {
    throw 'Die portable Windows-Version braucht ein 64-Bit-Windows.'
}
$base = Join-Path $PSScriptRoot '.runtime'
$ff = Join-Path $base 'ffmpeg'
New-Item -ItemType Directory -Force -Path $base, $ff | Out-Null
$url = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
$zip = Join-Path $base 'ffmpeg-release-essentials.zip'
$sha = $zip + '.sha256'
$tmp = Join-Path $base 'ffmpeg_extract'
try {
    Write-Host 'Lade FFmpeg Essentials von gyan.dev ...'
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Invoke-WebRequest -Uri ($url + '.sha256') -OutFile $sha -UseBasicParsing
    $expectedText = Get-Content -LiteralPath $sha -Raw
    $match = [regex]::Match($expectedText, '(?i)\b[a-f0-9]{64}\b')
    if (-not $match.Success) { throw 'FFmpeg SHA256-Datei unlesbar.' }
    $actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
    if ($actual.ToLowerInvariant() -ne $match.Value.ToLowerInvariant()) {
        throw 'FFmpeg-SHA256-Pruefung fehlgeschlagen.'
    }
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
    $exe = Get-ChildItem -LiteralPath $tmp -Recurse -File -Filter 'ffmpeg.exe' | Select-Object -First 1
    $probe = Get-ChildItem -LiteralPath $tmp -Recurse -File -Filter 'ffprobe.exe' | Select-Object -First 1
    if (-not $exe -or -not $probe) { throw 'FFmpeg oder FFprobe nicht im Archiv gefunden.' }
    Copy-Item -LiteralPath $exe.FullName -Destination (Join-Path $ff 'ffmpeg.exe') -Force
    Copy-Item -LiteralPath $probe.FullName -Destination (Join-Path $ff 'ffprobe.exe') -Force
    Write-Host 'FFmpeg und FFprobe geprueft und gespeichert.'
} finally {
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    if (Test-Path $zip) { Remove-Item -Force $zip }
    if (Test-Path $sha) { Remove-Item -Force $sha }
}
