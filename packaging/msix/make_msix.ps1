# Builds LTH-Overlays.msix for Microsoft Store upload (Windows, needs the Windows SDK for makeappx).
# 1) python packaging\build_dist.py      2) fill Identity in AppxManifest.xml   3) run this script
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$src = Join-Path $root "dist\LTH Overlays"
$stage = Join-Path $root "dist\msix-stage"
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item $src $stage -Recurse
# Version from lth_timing/__init__.py (Store needs 4 parts, last one 0)
$ver = (Select-String -Path (Join-Path $root "lth_timing\__init__.py") -Pattern 'VERSION = "([0-9.]+)"').Matches[0].Groups[1].Value
$manifest = (Get-Content (Join-Path $PSScriptRoot "AppxManifest.xml") -Raw) -replace 'Version="0\.0\.0\.0"', ('Version="' + $ver + '.0"')
if ($manifest -match "REPLACE") { Write-Warning "Fill Identity Name / Publisher / PublisherDisplayName from Partner Center first." }
Set-Content -Path (Join-Path $stage "AppxManifest.xml") -Value $manifest -Encoding UTF8
New-Item -ItemType Directory -Force (Join-Path $stage "Assets") | Out-Null
# Logos: generated from the app icon by the Python helper
& (Join-Path $src "python\python.exe") (Join-Path $PSScriptRoot "make_logos.py") (Join-Path $stage "Assets") (Join-Path $root "lth_overlays\data\brand\lth-icon-256.png")
$makeappx = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\makeappx.exe" | Sort-Object FullName | Select-Object -Last 1
& $makeappx.FullName pack /d $stage /p (Join-Path $root "dist\LTH-Overlays.msix") /o
Write-Host "Done: dist\LTH-Overlays.msix - upload it in Partner Center (the Store signs it)."
