$ErrorActionPreference = "Stop"

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$tunnelConfig = Join-Path $env:USERPROFILE ".cloudflared\config.yml"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python virtual environment not found: $python"
}
if (-not (Test-Path -LiteralPath $cloudflared)) {
    throw "cloudflared not found: $cloudflared"
}
if (-not (Test-Path -LiteralPath $tunnelConfig)) {
    throw "Cloudflare Tunnel config not found: $tunnelConfig"
}

$backend = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $backend) {
    Start-Process -FilePath $python -ArgumentList "run.py web" -WorkingDirectory $projectRoot -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Seconds 1
        $backend = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
    } while (-not $backend -and (Get-Date) -lt $deadline)
}

$tunnel = Get-Process cloudflared -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $tunnel) {
    Start-Process -FilePath $cloudflared -ArgumentList @("tunnel", "--config", $tunnelConfig, "run") -WorkingDirectory $projectRoot -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

$backendReady = [bool](Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1)
$tunnelReady = [bool](Get-Process cloudflared -ErrorAction SilentlyContinue | Select-Object -First 1)

if (-not $backendReady -or -not $tunnelReady) {
    throw "Online services failed to start. Backend=$backendReady Tunnel=$tunnelReady"
}

Write-Host "Online deployment is running at https://060115.top"
