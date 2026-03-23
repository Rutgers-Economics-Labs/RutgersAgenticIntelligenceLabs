# Dot-source from start-api.ps1 / kill-api-port.ps1 (repo root).
function Resolve-RailApiPort {
    param(
        [int]$ExplicitPort = 0,
        [Parameter(Mandatory)][string]$RepoRoot
    )
    if ($ExplicitPort -gt 0) { return $ExplicitPort }
    if ($env:RAIL_API_PORT -match '^\d+$') { return [int]$env:RAIL_API_PORT }
    $envFile = Join-Path $RepoRoot ".env"
    if (Test-Path -LiteralPath $envFile) {
        foreach ($line in Get-Content -LiteralPath $envFile) {
            $t = $line.Trim()
            if ($t.Length -eq 0 -or $t.StartsWith('#')) { continue }
            if ($t -match '^\s*RAIL_API_PORT\s*=\s*(\d+)\s*$') { return [int]$Matches[1] }
        }
    }
    return 8000
}
