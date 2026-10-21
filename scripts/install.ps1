<#
.SYNOPSIS
    Installs AutoTemplates for the current user - no admin rights, no .exe.

.DESCRIPTION
    * Warns when this folder is behind GitHub (git fetch) or has local changes.
    * Creates a private virtual environment in %LOCALAPPDATA%\AutoTemplates\venv,
      so AutoTemplates never shares packages with your other Python apps.
    * Installs AutoTemplates (PySide6-Essentials, Pygments) from a temporary copy
      of this folder (works from Google Drive / OneDrive and paths with spaces).
    * Creates a Start-menu (and with -DesktopShortcut, Desktop) shortcut.
    * Optionally starts it with Windows (-Autostart).
    * Starts it with pythonw.exe: no console window, only the tray icon.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Autostart -DesktopShortcut
#>
param(
    [switch]$Autostart,
    [switch]$DesktopShortcut,
    [string]$Python = "",
    [string]$InstallDir = "$env:LOCALAPPDATA\AutoTemplates",
    [switch]$NoLaunch,
    [switch]$SkipGitCheck
)

$ErrorActionPreference = "Stop"
$source = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $InstallDir "venv"

function Find-Python {
    if ($Python) { return @($Python) }
    if (Get-Command py -ErrorAction SilentlyContinue) { return @("py", "-3") }
    if (Get-Command python -ErrorAction SilentlyContinue) { return @("python") }
    throw "Python 3.10+ was not found. Install it from python.org (per user, no admin needed) and run this script again."
}

function Get-SourceVersion {
    $line = Select-String -Path (Join-Path $source "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($line) { return $line.Matches[0].Groups[1].Value }
    return "?"
}

function Test-GitState {
    $ErrorActionPreference = "Continue"  # git writes to stderr
    if ($SkipGitCheck -or -not (Test-Path (Join-Path $source ".git"))) { return }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { return }
    $commit = (& git -C $source log -1 --format="%h %cd" --date=format:"%Y-%m-%d %H:%M" 2>$null)
    $branch = (& git -C $source rev-parse --abbrev-ref HEAD 2>$null)
    Write-Host "  git    : $branch @ $commit"
    & git -C $source fetch --quiet 2>$null
    $behind = (& git -C $source rev-list --count "HEAD..@{u}" 2>$null)
    $changes = @(& git -C $source status --porcelain 2>$null)
    if ($changes.Count -gt 0) {
        Write-Host "  ATENTIE / WARNING: local changes that 'git pull' will not overwrite:" -ForegroundColor Yellow
        $changes | Select-Object -First 10 | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    }
    if ($behind -and [int]$behind -gt 0) {
        Write-Host "  ATENTIE / WARNING: this folder is $behind commit(s) behind GitHub. Run 'git pull' first (or Ctrl+C now)." -ForegroundColor Yellow
        Start-Sleep -Seconds 5
    }
}

function Stop-AutoTemplates {
    # Never replace files under a running copy: ask it to quit, then stop what is left.
    $ErrorActionPreference = "Continue"
    $vpy = Join-Path $venv "Scripts\python.exe"
    if (Test-Path $vpy) {
        & $vpy -m autotemplates action quit --no-start 2>&1 | Out-Null
        Start-Sleep -Milliseconds 1200
    }
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($venv, [StringComparison]::OrdinalIgnoreCase)) -or
            ($_.CommandLine -and $_.CommandLine -match '-m\s+autotemplates\b' -and $_.Name -match '^pythonw?\.exe$')
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

$version = Get-SourceVersion
Write-Host "AutoTemplates installer - version $version" -ForegroundColor Cyan
Write-Host "  source : $source"
Write-Host "  target : $venv"
Test-GitState

$py = Find-Python
$exe = $py[0]
$pyArgs = @()
if ($py.Count -gt 1) { $pyArgs = $py[1..($py.Count - 1)] }
& $exe @pyArgs -c "import sys; assert sys.version_info >= (3, 10), sys.version" 2>$null
if ($LASTEXITCODE -ne 0) { throw "AutoTemplates needs Python 3.10 or newer." }

if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    Write-Host "Creating the private environment..."
    & $exe @pyArgs -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Creating the virtual environment failed." }
}
$vpython = Join-Path $venv "Scripts\python.exe"
$vpythonw = Join-Path $venv "Scripts\pythonw.exe"

Stop-AutoTemplates

$build = Join-Path $env:TEMP ("autotemplates-src-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $build | Out-Null
try {
    foreach ($item in @("pyproject.toml", "README.md", "src")) {
        $from = Join-Path $source $item
        if (Test-Path $from) { Copy-Item -Path $from -Destination $build -Recurse -Force }
    }
    Get-ChildItem $build -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Installing AutoTemplates $version and its dependencies (PySide6-Essentials, Pygments)..."
    & $vpython -m pip install --disable-pip-version-check --upgrade pip | Out-Null
    & $vpython -m pip install --disable-pip-version-check --upgrade --force-reinstall --no-deps "$build"
    if ($LASTEXITCODE -ne 0) { throw "pip install failed (behind a proxy? set HTTPS_PROXY and retry)." }
    & $vpython -m pip install --disable-pip-version-check --upgrade "$build"
    if ($LASTEXITCODE -ne 0) { throw "pip install failed (behind a proxy? set HTTPS_PROXY and retry)." }
} finally {
    Remove-Item -Recurse -Force $build -ErrorAction SilentlyContinue
}

# DevPilot reads devpilot.tool.json from the tool's folder: keep a copy next to the venv.
Copy-Item -Path (Join-Path $source "devpilot.tool.json") -Destination $InstallDir -Force -ErrorAction SilentlyContinue

$setupArgs = @("-m", "autotemplates", "setup", "--start-menu")
if ($Autostart) { $setupArgs += @("--autostart", "on") }
& $vpython @setupArgs
if ($LASTEXITCODE -ne 0) { throw "Creating the shortcut failed." }

if ($DesktopShortcut) {
    $startLink = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\AutoTemplates.lnk"
    $desktop = [Environment]::GetFolderPath("Desktop")
    if ((Test-Path $startLink) -and $desktop) {
        Copy-Item -Path $startLink -Destination (Join-Path $desktop "AutoTemplates.lnk") -Force
        Write-Host "Desktop shortcut: $(Join-Path $desktop 'AutoTemplates.lnk')"
    }
}

$installed = (& $vpython -m autotemplates version)
Write-Host "Installed: $installed" -ForegroundColor Green
if ($installed -notmatch [regex]::Escape($version)) {
    Write-Host "  WARNING: expected $version - the installation did not update." -ForegroundColor Yellow
}

if (-not $NoLaunch) {
    Start-Process -FilePath $vpythonw -ArgumentList @("-m", "autotemplates", "gui") -WorkingDirectory $env:USERPROFILE
    Write-Host "AutoTemplates is running: look for its icon in the tray (^ next to the clock)." -ForegroundColor Green
}
Write-Host "Done. Start menu: AutoTemplates. Uninstall: Uninstall.bat"
