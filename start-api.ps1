<#
.SYNOPSIS
  Start only the RAIL FastAPI service in this terminal (foreground).

.DESCRIPTION
  Sets ENGINE_ROOT and related paths like start-rail.ps1, optionally runs
  pip install -e packages\api, then runs uvicorn so stdout/stderr stay visible
  (unlike start-rail.ps1, which launches the API in a minimized window).

.PARAMETER Quick
  Skip pip install; only start uvicorn.

.PARAMETER Port
  Listen port (default 8000).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\start-api.ps1

.EXAMPLE
  .\start-api.ps1 -Quick

.EXAMPLE
  .\start-api.ps1 -Port 8001 -Quick
#>
param(
    [switch]$Quick,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found on PATH. Install Python 3.11+ and try again."
}

$apiDir = Join-Path $root "packages\api"
$engineRoot = Join-Path $root "packages\engine"

if (-not (Test-Path $apiDir) -or -not (Test-Path $engineRoot)) {
    Write-Error "Expected packages\api and packages\engine under $root"
}

$env:ENGINE_ROOT = $engineRoot
$env:RAIL_ANALYSIS_DIR = Join-Path $engineRoot "analysis"
$env:RAIL_TRANSFORM_DIR = Join-Path $engineRoot "transforms"

if (-not $Quick) {
    Write-Host "→ pip install -e packages\api …" -ForegroundColor Cyan
    python -m pip install -e $apiDir
}

Write-Host ""
Write-Host "→ API  http://127.0.0.1:$Port  (health /health, docs /docs)" -ForegroundColor Green
Write-Host "   Stop: Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

Set-Location $apiDir
python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload
