# Install the built executables for the current user (no admin rights needed).
#   .\install.ps1     -> copies dist\*.exe to %LOCALAPPDATA%\Programs\FileSweep
#                        and adds Desktop + Start Menu shortcuts
#   .\install.ps1 -Uninstall
param(
    [switch]$Uninstall,
    [switch]$NoDesktop
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$installDir = Join-Path $env:LOCALAPPDATA "Programs\FileSweep"
$startMenu  = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$desktop    = [Environment]::GetFolderPath("Desktop")
$exe        = Join-Path $installDir "FileSweep.exe"
$icon       = Join-Path $installDir "filesweep.ico"

function New-Shortcut {
    param([string]$Path, [string]$Target, [string]$IconPath)
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $Target
    $shortcut.WorkingDirectory = (Split-Path $Target)
    $shortcut.IconLocation = "$IconPath,0"
    $shortcut.Description = "FileSweep - tidy any folder by file type"
    $shortcut.Save()
}

if ($Uninstall) {
    foreach ($path in @($desktop, $startMenu)) {
        $lnk = Join-Path $path "FileSweep.lnk"
        if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host "removed $lnk" }
    }
    if (Test-Path $installDir) { Remove-Item $installDir -Recurse -Force; Write-Host "removed $installDir" }
    Write-Host "FileSweep uninstalled." -ForegroundColor Green
    return
}

if (-not (Test-Path "dist\FileSweep.exe")) {
    throw "dist\FileSweep.exe not found - run .\build.ps1 first."
}

New-Item -ItemType Directory -Force -Path $installDir | Out-Null
Copy-Item "dist\FileSweep.exe" $exe -Force
if (Test-Path "dist\FileSweep-CLI.exe") {
    Copy-Item "dist\FileSweep-CLI.exe" (Join-Path $installDir "FileSweep-CLI.exe") -Force
}
Copy-Item "assets\filesweep.ico" $icon -Force

New-Shortcut -Path (Join-Path $startMenu "FileSweep.lnk") -Target $exe -IconPath $icon
if (-not $NoDesktop) {
    New-Shortcut -Path (Join-Path $desktop "FileSweep.lnk") -Target $exe -IconPath $icon
}

Write-Host ""
Write-Host "Installed to: $installDir" -ForegroundColor Green
Write-Host "Shortcuts: Desktop + Start Menu"
Write-Host "Uninstall with: .\install.ps1 -Uninstall"
