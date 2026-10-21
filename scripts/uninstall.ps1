<#
.SYNOPSIS
    Removes AutoTemplates for the current user (shortcuts, autostart, private environment).
    Settings and the template library are kept; -RemoveData also deletes settings, index and logs
    (the library folder is never deleted).
#>
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\AutoTemplates",
    [switch]$RemoveData
)

$ErrorActionPreference = "Stop"
$venv = Join-Path $InstallDir "venv"
$vpython = Join-Path $venv "Scripts\python.exe"

$ErrorActionPreference = "Continue"
if (Test-Path $vpython) {
    & $vpython -m autotemplates action quit --no-start 2>&1 | Out-Null
    Start-Sleep -Milliseconds 1200
}
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($venv, [StringComparison]::OrdinalIgnoreCase)) -or
        ($_.CommandLine -and $_.CommandLine -match '-m\s+autotemplates\b' -and $_.Name -match '^pythonw?\.exe$')
    } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
$ErrorActionPreference = "Stop"

if (Test-Path $vpython) { & $vpython -m autotemplates setup --remove }
$desktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "AutoTemplates.lnk"
if (Test-Path $desktopLink) { Remove-Item -Force $desktopLink; Write-Host "Removed $desktopLink" }
if (Test-Path $venv) { Remove-Item -Recurse -Force $venv; Write-Host "Removed $venv" }
if ($RemoveData -and (Test-Path $InstallDir)) { Remove-Item -Recurse -Force $InstallDir; Write-Host "Removed $InstallDir" }
Write-Host "AutoTemplates was uninstalled. Your templates folder was not touched."
