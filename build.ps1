# Build standalone executables with PyInstaller.
#   .\build.ps1                 -> dist\FileSweep.exe and dist\filesweep.exe
#   .\build.ps1 -SkipInstall    -> reuse an existing PyInstaller install
#
# Each build gets its own --distpath, then the single-file exes are copied to
# dist\ root. PyInstaller's output handling removes sibling files in the same
# dist folder, so keeping the builds separate is what makes both survive.
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$icon = Join-Path $PSScriptRoot "assets\filesweep.ico"
if (-not (Test-Path $icon)) { throw "Icon not found: $icon" }

if (-not $SkipInstall) {
    python -m pip install --upgrade pyinstaller
}

function Invoke-PyInstaller {
    param([string[]]$ArgList)
    & python -m PyInstaller @ArgList
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
}

Invoke-PyInstaller @(
    "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", "FileSweep", "--icon", $icon,
    "--distpath", "dist\gui", "--workpath", "build\gui", "--specpath", "build",
    "run_gui.py"
)

Invoke-PyInstaller @(
    "--noconfirm", "--clean", "--onefile", "--console",
    "--name", "FileSweep-CLI", "--icon", $icon,
    "--distpath", "dist\cli", "--workpath", "build\cli", "--specpath", "build",
    "run_cli.py"
)

Copy-Item "dist\gui\FileSweep.exe" "dist\FileSweep.exe" -Force
Copy-Item "dist\cli\FileSweep-CLI.exe" "dist\FileSweep-CLI.exe" -Force
Remove-Item -Recurse -Force "dist\gui", "dist\cli"

Write-Host ""
Write-Host "Done:" -ForegroundColor Green
Get-ChildItem dist | ForEach-Object {
    Write-Host ("  dist\{0}  ({1:N1} MB)" -f $_.Name, ($_.Length / 1MB))
}
