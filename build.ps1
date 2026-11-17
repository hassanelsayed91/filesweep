# Build standalone executables with PyInstaller.
#   .\build.ps1                 -> dist\FileSweep.exe and dist\filesweep.exe
#   .\build.ps1 -SkipInstall    -> reuse an existing PyInstaller install
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $SkipInstall) {
    python -m pip install --upgrade pyinstaller
}

python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name FileSweep --icon assets\filesweep.ico run_gui.py

python -m PyInstaller --noconfirm --clean --onefile --console `
    --name filesweep --icon assets\filesweep.ico run_cli.py

Write-Host ""
Write-Host "Done:" -ForegroundColor Green
Write-Host "  dist\FileSweep.exe   (GUI)"
Write-Host "  dist\filesweep.exe   (CLI)"
