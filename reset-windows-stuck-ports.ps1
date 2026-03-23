<#
.SYNOPSIS
  Try to clear Windows TCP state that blocks binds (e.g. ghost LISTEN on 8000).

.DESCRIPTION
  Restarts the WinNAT service (often helps after Hyper-V / WSL / Docker). Requires
  an elevated PowerShell. If the port is still stuck, reboot.

.EXAMPLE
  # Right-click PowerShell -> Run as administrator, then:
  cd C:\path\to\RutgersAgenticIntelligenceLabs
  .\reset-windows-stuck-ports.ps1
#>
Write-Host ">> Restarting WinNAT (needs Administrator) ..." -ForegroundColor Cyan
try {
    Restart-Service -Name winnat -Force -ErrorAction Stop
    Write-Host ">> WinNAT restarted. Try .\start-api.ps1 again." -ForegroundColor Green
} catch {
    Write-Host ">> $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ">> Run this script from an elevated PowerShell, or reboot." -ForegroundColor Yellow
    exit 1
}
