# Builds LTH-Overlays.msix for Microsoft Store upload (Windows, needs the Windows SDK for makeappx).
# 1) python packaging\build_dist.py      2) fill Identity in AppxManifest.xml   3) run this script
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$src = Join-Path $root "dist\LTH Overlays"
$stage = Join-Path $root "dist\msix-stage"
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item $src $stage -Recurse
Copy-Item (Join-Path $PSScriptRoot "AppxManifest.xml") $stage
New-Item -ItemType Directory -Force (Join-Path $stage "Assets") | Out-Null
# Logos: generated from the app icon by the Python helper
& (Join-Path $src "python\python.exe") (Join-Path $PSScriptRoot "make_logos.py") (Join-Path $stage "Assets")
$makeappx = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\makeappx.exe" | Sort-Object FullName | Select-Object -Last 1
& $makeappx.FullName pack /d $stage /p (Join-Path $root "dist\LTH-Overlays.msix") /o
Write-Host "Done: dist\LTH-Overlays.msix - upload it in Partner Center (the Store signs it)."
