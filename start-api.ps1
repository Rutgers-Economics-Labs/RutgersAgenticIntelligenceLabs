<#
.SYNOPSIS
  Start only the RAIL FastAPI service in this terminal (foreground).

.DESCRIPTION
  Changes to the repo root (this script's directory), sets ENGINE_ROOT, optionally
  runs pip install -e, frees the API port immediately before binding (so a long
  pip step cannot leave 8000 taken by another process), then runs uvicorn.

.PARAMETER Quick
  Skip pip install; only start uvicorn.

.PARAMETER Port
  Listen port. Omit or pass 0 to use RAIL_API_PORT (env or repo root .env), else 8000.

.PARAMETER NoReload
  Disable uvicorn --reload. Use for long hydration jobs: reload restarts the process
  and cancels in-flight background tasks (empty logs / failed jobs).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\start-api.ps1

.EXAMPLE
  .\start-api.ps1 -Quick

.EXAMPLE
  .\start-api.ps1 -Port 8001 -Quick

.EXAMPLE
  .\start-api.ps1 -NoReload
#>
param(
    [switch]$Quick,
    [switch]$NoReload,
    [int]$Port = 0
)

function Stop-ListenersOnPort {
    param([int]$PortNum)
    Write-Host ">> Freeing port $PortNum ..." -ForegroundColor DarkGray
    $pidsToStop = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($row in (Get-NetTCPConnection -LocalPort $PortNum -State Listen -ErrorAction SilentlyContinue)) {
        [void]$pidsToStop.Add($row.OwningProcess)
    }
    foreach ($line in (netstat -ano)) {
        if ($line -notmatch "LISTENING") { continue }
        if ($line -notmatch ":$PortNum\s") { continue }
        if ($line -match "LISTENING\s+(\d+)\s*$") {
            [void]$pidsToStop.Add([int]$Matches[1])
        }
    }
    foreach ($procId in $pidsToStop) {
        if ($procId -le 0) { continue }
        $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
        # Stale rows: Get-NetTCPConnection/netstat can report LISTEN + PID after the process is gone.
        if (-not $p) { continue }
        Write-Host "   Stopping PID $procId ($($p.ProcessName))" -ForegroundColor DarkYellow
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
        } catch {
            $msg = $_.Exception.Message
            if ($msg -notmatch "Cannot find a process") {
                Write-Host "   Stop-Process failed: $msg" -ForegroundColor DarkYellow
            }
        }
        Start-Sleep -Milliseconds 200
        if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
            # Use cmd so taskkill stderr does not become a terminating error when $ErrorActionPreference = Stop
            $tkLines = @(cmd.exe /c "taskkill /F /PID $procId 2>&1")
            foreach ($line in $tkLines) {
                if ($line) { Write-Host "   taskkill: $line" -ForegroundColor DarkGray }
            }
        }
    }
}

Set-Location -LiteralPath $PSScriptRoot
$root = $PSScriptRoot
. (Join-Path $root "rail-api-port.ps1")
$Port = Resolve-RailApiPort -ExplicitPort $Port -RepoRoot $root

Write-Host ">> Repo root: $root" -ForegroundColor DarkGray
Write-Host ">> API port: $Port" -ForegroundColor DarkGray
Stop-ListenersOnPort -PortNum $Port

$ErrorActionPreference = "Stop"

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
    Write-Host ">> pip install -e packages\api ..." -ForegroundColor Cyan
    python -m pip install -e $apiDir
}

Write-Host ""
Write-Host ">> API  http://127.0.0.1:$Port  (health /health, docs /docs)" -ForegroundColor Green
if ($NoReload) {
    Write-Host "   Mode: no --reload (stable for hydration jobs)" -ForegroundColor DarkGray
} else {
    Write-Host '   Mode: --reload (file edits restart server; cancels running jobs)' -ForegroundColor DarkYellow
}
Write-Host '   Stop: Ctrl+C' -ForegroundColor DarkGray
Write-Host ""

Set-Location $apiDir

# Bind happens here — free port again after pip so nothing can take 8000 during install.
Stop-ListenersOnPort -PortNum $Port
Start-Sleep -Milliseconds 800
$stillListen = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($stillListen.Count -gt 0) {
    Write-Host ">> Port $Port still in use; one more kill + wait ..." -ForegroundColor DarkYellow
    Stop-ListenersOnPort -PortNum $Port
    Start-Sleep -Seconds 1
}

Write-Host ">> Bind probe 127.0.0.1:$Port ..." -ForegroundColor DarkGray
$bindPy = "import socket,sys;p=int(sys.argv[1]);s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',p));s.close()"
python -c $bindPy @("$Port")
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host ">> Port $Port is not bindable (WinError 10048 is common)." -ForegroundColor Red
    Write-Host "   netstat can show LISTEN with PIDs that no longer exist (orphaned socket)." -ForegroundColor Yellow
    Write-Host "   Try: .\reset-windows-stuck-ports.ps1 (Admin) or reboot." -ForegroundColor Yellow
    Write-Host "   Workaround: set RAIL_API_PORT=8001 in repo root .env and point the web app at that port (NEXT_PUBLIC_API_URL)." -ForegroundColor Yellow
    exit 1
}

$uvArgs = @("app.main:app", "--host", "127.0.0.1", "--port", "$Port")
if (-not $NoReload) { $uvArgs += "--reload" }
python -m uvicorn @uvArgs
