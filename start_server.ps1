$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Join-Path $projectRoot "hiremind"
$stdoutLog = Join-Path $appRoot "server.out.log"
$stderrLog = Join-Path $appRoot "server.err.log"
$hostUrl = "http://127.0.0.1:5000"
$port = 5000
$pythonCandidates = @(
    "C:\Users\Gnaneshwar Reddy\AppData\Local\Programs\Python\Python313\python.exe",
    (Join-Path $appRoot ".venv\Scripts\python.exe")
)

$pythonExe = $pythonCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if (-not $pythonExe) {
    throw "Python executable not found. Update start_server.ps1 with the correct path."
}

if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "HireMind is already running on $hostUrl" -ForegroundColor Yellow
    exit 0
}

if (Test-Path $stdoutLog) {
    Remove-Item -LiteralPath $stdoutLog -Force
}

if (Test-Path $stderrLog) {
    Remove-Item -LiteralPath $stderrLog -Force
}

Write-Host "Starting HireMind server on $hostUrl" -ForegroundColor Cyan
$process = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList "run_server.py" `
    -WorkingDirectory $appRoot `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

$started = $false
for ($attempt = 0; $attempt -lt 15; $attempt++) {
    Start-Sleep -Milliseconds 500

    if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
        break
    }

    try {
        $response = Invoke-WebRequest -UseBasicParsing $hostUrl -TimeoutSec 2
        if ($response.StatusCode -ge 200) {
            $started = $true
            break
        }
    } catch {
    }
}

if (-not $started) {
    Write-Host "HireMind failed to start. Check logs below." -ForegroundColor Red
    if (Test-Path $stderrLog) {
        Get-Content $stderrLog
    }
    if (Test-Path $stdoutLog) {
        Get-Content $stdoutLog
    }
    exit 1
}

Write-Host "HireMind is running at $hostUrl" -ForegroundColor Green
Write-Host "PID: $($process.Id)" -ForegroundColor DarkGray
