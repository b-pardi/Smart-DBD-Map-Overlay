# build the one-file terminal release, run inside the conda env:
#   conda activate dbdmap-env; ./build.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    throw "pyinstaller not found, run 'pip install pyinstaller' in the dbdmap-env"
}

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
pyinstaller --clean --noconfirm smart-dbd-map-overlay.spec
Write-Host "built dist/smart-dbd-map-overlay.exe" -ForegroundColor Green
