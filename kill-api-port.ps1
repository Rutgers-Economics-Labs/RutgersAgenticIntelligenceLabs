<#
.SYNOPSIS
  Stop any process listening on the API port (default 8000).

.DESCRIPTION
  Run from repo root before .\start-api.ps1 -NoReload when port 8000 is still held
  by a previous uvicorn, reload child, or another tool. Uses Get-NetTCPConnection
  and netstat parsing (same approach as start-api.ps1).

.PARAMETER Port
  TCP port to free. Omit or 0 = RAIL_API_PORT from env / repo root .env, else 8000.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\kill-api-port.ps1

.EXAMPLE
  .\kill-api-port.ps1 -Port 8001
#>
param(
    [int]$Port = 0
)

Set-Location -LiteralPath $PSScriptRoot
$root = $PSScriptRoot
. (Join-Path $root "rail-api-port.ps1")
$Port = Resolve-RailApiPort -ExplicitPort $Port -RepoRoot $root

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
            $tkLines = @(cmd.exe /c "taskkill /F /PID $procId 2>&1")
            foreach ($line in $tkLines) {
                if ($line) { Write-Host "   taskkill: $line" -ForegroundColor DarkGray }
            }
        }
    }
}

Stop-ListenersOnPort -PortNum $Port
Start-Sleep -Milliseconds 800
$stillListen = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($stillListen.Count -gt 0) {
    Write-Host ">> Port $Port still in use; one more kill + wait ..." -ForegroundColor DarkYellow
    Stop-ListenersOnPort -PortNum $Port
    Start-Sleep -Seconds 1
}

$stillListen = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($stillListen.Count -gt 0) {
    $pids = ($stillListen | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique)
    $anyLive = $false
    foreach ($listenPid in $pids) {
        if ($listenPid -gt 0 -and (Get-Process -Id $listenPid -ErrorAction SilentlyContinue)) {
            $anyLive = $true
            break
        }
    }
    if (-not $anyLive) {
        Write-Host ">> LISTEN still appears for :$Port but those PIDs are gone (stale TCP rows). Port should be usable." -ForegroundColor Green
        exit 0
    }
    Write-Host ">> Port $Port is still in LISTEN state. Live PIDs: $($pids -join ', ')" -ForegroundColor Red
    Write-Host ">> netstat lines for :$Port :" -ForegroundColor Yellow
    netstat -ano | Select-String -Pattern ":$Port\s" | ForEach-Object { Write-Host "   $_" }
    foreach ($listenPid in $pids) {
        & tasklist.exe /FI "PID eq $listenPid" /FO LIST 2>&1 | Write-Host
    }
    Write-Host ">> Windows excluded TCP ranges (if $Port falls inside one, pick another port or adjust Hyper-V reserve):" -ForegroundColor Yellow
    netsh interface ipv4 show excludedportrange protocol=tcp 2>&1 | ForEach-Object { Write-Host "   $_" }
    Write-Host ">> Try: reboot, or start-api with -Port 8001, or run an elevated shell if access was denied." -ForegroundColor Yellow
    exit 1
}

Write-Host ">> Port $Port is free." -ForegroundColor Green
