<#
.SYNOPSIS
  Set up a virtual environment for BackupQT and create a Desktop shortcut to launch it (no console).

.DESCRIPTION
  - Creates .venv in the project folder if missing
  - Installs requirements from requirements.txt
  - Creates a Desktop shortcut that runs BackupQT.pyw with .venv\Scripts\pythonw.exe
  - Optional: launches the app immediately with -Launch

.PARAMETER ShortcutName
  Name of the shortcut to create on the Desktop (default: BackupQT.lnk)

.PARAMETER Launch
  If specified, launches the app after setup completes

.USAGE
  Right-click Install.ps1 → Run with PowerShell
  or from PowerShell:
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\Install.ps1 -Launch
#>
[CmdletBinding()]
param(
  [string]$ShortcutName = 'BackupQT.lnk',
  [switch]$Launch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Ok($msg)   { Write-Host "[ OK ] $msg" -ForegroundColor Green }

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$venvDir = Join-Path $root '.venv'
$pythonExe = Join-Path $venvDir 'Scripts\python.exe'
$pythonwExe = Join-Path $venvDir 'Scripts\pythonw.exe'
$scriptPath = Join-Path $root 'BackupQT.pyw'

if (-not (Test-Path $scriptPath)) {
  throw "BackupQT.pyw not found at $scriptPath"
}

if (-not (Test-Path $venvDir)) {
  Write-Info "Creating virtual environment in .venv"
  $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
  if ($pyLauncher) {
    # Prefer Python 3.11 if available
    $spec = '-3.11'
    try {
      & py $spec -c "import sys;print(sys.version)" | Out-Null
    } catch {
      $spec = '-3'
    }
    & py $spec -m venv .venv
  } else {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
      throw 'Python not found. Please install Python 3.11 or the Python Launcher (py).'
    }
    & python -m venv .venv
  }
  Write-Ok 'Virtual environment created.'
} else {
  Write-Info 'Virtual environment already exists (.venv)'
}

if (-not (Test-Path $pythonExe)) {
  throw "venv python.exe not found at $pythonExe"
}

Write-Info 'Upgrading pip and installing requirements (if any)'
& $pythonExe -m pip install --upgrade pip setuptools wheel | Out-Host

$req = Join-Path $root 'requirements.txt'
if (Test-Path $req) {
  & $pythonExe -m pip install -r $req | Out-Host
} else {
  Write-Warn 'requirements.txt not found; skipping dependency install'
}

if (-not (Test-Path $pythonwExe)) {
  throw "venv pythonw.exe not found at $pythonwExe"
}

Write-Info 'Creating Desktop shortcut'
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop $ShortcutName

$wsh = New-Object -ComObject WScript.Shell
$lnk = $wsh.CreateShortcut($shortcutPath)
$lnk.TargetPath = $pythonwExe
$lnk.Arguments = ' "' + $scriptPath + '"'
$lnk.WorkingDirectory = $root
$lnk.IconLocation = $pythonwExe
$lnk.Save()
Write-Ok "Shortcut created: $shortcutPath"

if ($Launch) {
  Write-Info 'Launching application...'
  Start-Process -FilePath $pythonwExe -ArgumentList '"' + $scriptPath + '"' -WorkingDirectory $root | Out-Null
}

Write-Ok 'Setup complete.'