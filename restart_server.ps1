$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$startScript = Join-Path $projectRoot "start_server.ps1"
$port = 5000

$listeningConnections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
$pids = @($listeningConnections | Select-Object -ExpandProperty OwningProcess -Unique)

foreach ($pid in $pids) {
    if ($pid) {
        try {
            Stop-Process -Id $pid -Force
            Write-Host "Stopped process $pid on port $port." -ForegroundColor Yellow
        } catch {
            Write-Warning "Could not stop process $pid: $($_.Exception.Message)"
        }
    }
}

Start-Sleep -Seconds 1

if (-not (Test-Path $startScript)) {
    throw "start_server.ps1 not found at $startScript"
}

powershell.exe -NoProfile -ExecutionPolicy Bypass -File $startScript
