# Downloads the official Deno binary to .runtime\deno.exe without a system-wide install.
# Verifies SHA-256 against the checksum file published with the GitHub release.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$runtime = Join-Path $PSScriptRoot '.runtime'
New-Item -Path $runtime -ItemType Directory -Force | Out-Null
$architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
if ($architecture -eq 'Arm64') {
    $archive = 'deno-aarch64-pc-windows-msvc.zip'
} elseif ($architecture -eq 'X64') {
    $archive = 'deno-x86_64-pc-windows-msvc.zip'
} else {
    throw 'Deno wird in diesem Skript nur auf Windows x64/ARM64 unterstützt.'
}
$url = 'https://github.com/denoland/deno/releases/latest/download/' + $archive
$zip = Join-Path $runtime $archive
$hashFile = Join-Path $runtime ($archive + '.sha256sum')
Write-Host 'Lade Deno von denoland/deno (GitHub) herunter ...'
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
Invoke-WebRequest -Uri ($url + '.sha256sum') -OutFile $hashFile -UseBasicParsing
$checksumText = Get-Content -Path $hashFile -Raw
$match = [regex]::Match($checksumText, '(?i)\b[a-f0-9]{64}\b')
if (-not $match.Success) { throw 'Konnte den offiziellen SHA-256-Prüfwert nicht lesen.' }
$expected = $match.Value.ToLowerInvariant()
$actual = (Get-FileHash -Path $zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'SHA-256-Prüfung fehlgeschlagen! Archiv wird nicht verwendet.' }
Expand-Archive -Path $zip -DestinationPath $runtime -Force
Remove-Item $zip, $hashFile -Force
$deno = Join-Path $runtime 'deno.exe'
if (-not (Test-Path $deno)) { throw 'deno.exe wurde im Archiv nicht gefunden.' }
& $deno --version
if ($LASTEXITCODE -ne 0) { throw 'Deno konnte nicht gestartet werden.' }
Write-Host 'Deno erfolgreich unter .runtime\deno.exe eingerichtet.'
