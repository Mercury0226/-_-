param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Step {
    param([string]$Message)
    Write-Host "[UJM Acceptance] $Message" -ForegroundColor Cyan
}

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing command: $Name"
    }
}

$root = Split-Path -Parent $PSScriptRoot
$serverDir = Join-Path $root "server"
$dashboardDir = Join-Path $root "dashboard"
$samplePath = Join-Path $root "schemas\behavior-log.example.json"
$venvDir = Join-Path $serverDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$serverProcess = $null

try {
    Write-Step "Checking runtime dependencies"
    Assert-Command -Name "python"
    Assert-Command -Name "npm"

    if (-not (Test-Path $venvPython)) {
        Write-Step "Creating Python virtual environment"
        Push-Location $serverDir
        python -m venv .venv
        Pop-Location
    }

    Write-Step "Installing backend dependencies"
    Push-Location $serverDir
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements.txt
    Pop-Location

    Write-Step "Starting FastAPI"
    $serverProcess = Start-Process -FilePath $venvPython -ArgumentList @("-m", "uvicorn", "main:app", "--host", $HostName, "--port", "$Port") -WorkingDirectory $serverDir -PassThru

    $healthUrl = "http://${HostName}:${Port}/health"
    $ingestUrl = "http://${HostName}:${Port}/api/v1/logs/ingest"
    $ready = $false

    foreach ($i in 1..30) {
        try {
            $health = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 1
            if ($health.status -eq "ok") {
                $ready = $true
                break
            }
        } catch {
            # retry
        }
    }

    if (-not $ready) {
        throw "Health check failed: $healthUrl"
    }

    Write-Step "Posting sample behavior log"
    $payload = Get-Content -Path $samplePath -Raw -Encoding UTF8
    $ingestResp = Invoke-RestMethod -Uri $ingestUrl -Method Post -ContentType "application/json; charset=utf-8" -Body $payload

    if (-not $ingestResp.ok) {
        throw "Ingest response was not ok"
    }

    if (-not $ingestResp.analysis) {
        throw "Ingest response missing analysis"
    }

    Write-Step "Installing and building dashboard"
    Push-Location $dashboardDir
    npm install
    npm run build
    Pop-Location

    Write-Host ""
    Write-Host "================ ACCEPTANCE PASSED ================" -ForegroundColor Green
    Write-Host "Health: $healthUrl"
    Write-Host "Ingest: $ingestUrl"
    Write-Host "Received: $($ingestResp.received)"
    Write-Host "Loop Anomaly: $($ingestResp.analysis.loop_entropy_anomaly)"
    Write-Host "Time Anomaly: $($ingestResp.analysis.time_threshold_anomaly)"
    Write-Host "Summary: $($ingestResp.analysis.summary)"
    Write-Host "UTF-8 sample user includes rare char: user_玥_1001"
    Write-Host "===================================================" -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "================ ACCEPTANCE FAILED ================" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "===================================================" -ForegroundColor Red
    throw
} finally {
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Write-Step "Stopping FastAPI"
        Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
