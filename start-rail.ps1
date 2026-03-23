<#
.SYNOPSIS
  One-shot RAIL dev: install dependencies, then run FastAPI + Next.js.

.DESCRIPTION
  - Prepends nvm-windows Node to PATH (.nvmrc if present, else latest v22.x, else newest v*).
  - pip install -e packages/api
  - npm install in packages/web
  - Starts uvicorn on 127.0.0.1:8000 (minimized window) and npm run dev in this terminal.

.PARAMETER Quick
  Skip pip/npm install; only start servers (use after first successful run).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\start-rail.ps1

.EXAMPLE
  .\start-rail.ps1 -Quick
#>
param(
    [switch]$Quick
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Add-NvmNodeToPath {
    $nvmBase = Join-Path $env:LOCALAPPDATA "nvm"
    if (-not (Test-Path $nvmBase)) { return }

    $nvmrc = Join-Path $root ".nvmrc"
    $want = $null
    if (Test-Path $nvmrc) {
        $want = (Get-Content $nvmrc -Raw).Trim()
    }

    $dirs = Get-ChildItem $nvmBase -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^v\d' }
    if (-not $dirs) { return }

    $pick = $null
    if ($want) {
        $exact = Join-Path $nvmBase "v$want"
        if (Test-Path (Join-Path $exact "node.exe")) {
            $pick = Get-Item $exact
        }
        if (-not $pick) {
            $pick = $dirs | Where-Object { $_.Name -match "^v$([regex]::Escape($want))(\.|$)" } |
                ForEach-Object {
                    try { [PSCustomObject]@{ Dir = $_; Ver = [version]($_.Name.Substring(1)) } } catch { $null }
                } |
                Where-Object { $_ } | Sort-Object { $_.Ver } -Descending |
                Select-Object -First 1 -ExpandProperty Dir
        }
    }
    if (-not $pick) {
        $pick = $dirs | Where-Object { $_.Name -match '^v22\.' } |
            ForEach-Object {
                try { [PSCustomObject]@{ Dir = $_; Ver = [version]($_.Name.Substring(1)) } } catch { $null }
            } |
            Where-Object { $_ } | Sort-Object { $_.Ver } -Descending |
            Select-Object -First 1 -ExpandProperty Dir
    }
    if (-not $pick) {
        $pick = $dirs | ForEach-Object {
            try { [PSCustomObject]@{ Dir = $_; Ver = [version]($_.Name.Substring(1)) } } catch { $null }
        } | Where-Object { $_ } | Sort-Object { $_.Ver } -Descending | Select-Object -First 1 -ExpandProperty Dir
    }

    if ($pick -and (Test-Path (Join-Path $pick.FullName "node.exe"))) {
        $env:Path = "$($pick.FullName);$env:Path"
    }
}

Add-NvmNodeToPath

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Error @"
Node.js not found on PATH.
Install Node (e.g. nvm-windows: https://github.com/coreybutler/nvm-windows ) or add node.exe to PATH.
If you use nvm, optional repo file .nvmrc can pin the major version (e.g. 22).
"@
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found on PATH. Install Python 3.11+ and try again."
}

$apiDir = Join-Path $root "packages\api"
$webDir = Join-Path $root "packages\web"
$engineRoot = Join-Path $root "packages\engine"

if (-not (Test-Path $apiDir) -or -not (Test-Path $webDir) -or -not (Test-Path $engineRoot)) {
    Write-Error "Expected packages\api, packages\web, and packages\engine under $root"
}

$env:ENGINE_ROOT = $engineRoot
$env:RAIL_ANALYSIS_DIR = Join-Path $engineRoot "analysis"
$env:RAIL_TRANSFORM_DIR = Join-Path $engineRoot "transforms"

if (-not $Quick) {
    Write-Host "→ pip install -e packages\api …" -ForegroundColor Cyan
    python -m pip install --quiet -e $apiDir
    Write-Host "→ npm install (packages\web) …" -ForegroundColor Cyan
    Push-Location $webDir
    npm install
    Pop-Location
}

Write-Host "→ API  http://127.0.0.1:8000  (docs /docs)" -ForegroundColor Green
$apiProc = Start-Process -FilePath "python" -ArgumentList @(
    "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"
) -WorkingDirectory $apiDir -PassThru -WindowStyle Minimized

Write-Host "→ Web  http://localhost:3000" -ForegroundColor Green
Write-Host "   Stop: Ctrl+C here (API process will be stopped)." -ForegroundColor DarkGray
Set-Location $webDir
try {
    npm run dev
}
finally {
    if ($apiProc -and -not $apiProc.HasExited) {
        Stop-Process -Id $apiProc.Id -Force -ErrorAction SilentlyContinue
    }
}
