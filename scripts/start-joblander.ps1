# Launches JobLander: starts the local server from its dedicated Python
# environment, waits for it to come up (polling, not a blind sleep), then
# opens your browser. Created by install.ps1 - safe to re-run any time.
# This file lives in scripts\ - $Root is the app's actual root folder.

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$ServerDir = Join-Path $Root 'server'
$Url = 'http://127.0.0.1:8787/'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "JobLander hasn't been set up yet." -ForegroundColor Red
    Write-Host "Please run Install-JobLander.bat first." -ForegroundColor Yellow
    exit 1
}

Write-Host "Starting JobLander..." -ForegroundColor Cyan
Write-Host "Leave this window open while you use the app - closing it stops the server." -ForegroundColor DarkGray
Write-Host ""

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $VenvPython
$psi.Arguments = 'main.py'
$psi.WorkingDirectory = $ServerDir
$psi.UseShellExecute = $false
$proc = [System.Diagnostics.Process]::Start($psi)

$maxWaitSeconds = 30
$up = $false
# Real wall-clock stopwatch, not a hand-accumulated counter - measured for
# real on the dev machine that a failed request to a closed port can itself
# take ~2.4s to time out (not the instant "connection refused" you'd get on
# a machine with no security software watching network traffic; this
# machine, like real target machines, has Avast). Tracking only the
# Start-Sleep duration would silently let the real wait run to several
# times the intended 30s cap whenever requests are slow to fail.
$sw = [System.Diagnostics.Stopwatch]::StartNew()
while ($sw.Elapsed.TotalSeconds -lt $maxWaitSeconds) {
    if ($proc.HasExited) {
        Write-Host "The server process exited unexpectedly (exit code $($proc.ExitCode)) before it came up." -ForegroundColor Red
        break
    }
    try {
        $resp = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 2 -UseBasicParsing
        if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) { $up = $true; break }
    } catch {
        # Not up yet (connection refused, or still timing out) - keep waiting.
    }
    Start-Sleep -Milliseconds 500
}

if ($up) {
    Write-Host "JobLander is up - opening your browser..." -ForegroundColor Green
    Start-Process $Url
} elseif (-not $proc.HasExited) {
    Write-Host "The server didn't respond within $maxWaitSeconds seconds." -ForegroundColor Yellow
    Write-Host "It may still be starting - try opening $Url yourself in a moment, or check for errors above." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Server is running. Close this window (or press Ctrl+C) to stop JobLander."
Wait-Process -Id $proc.Id -ErrorAction SilentlyContinue
