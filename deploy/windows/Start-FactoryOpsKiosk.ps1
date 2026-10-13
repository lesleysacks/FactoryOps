#Requires -Version 5.1
<#
.SYNOPSIS
  Wait until FactoryOps answers /health/, then open the login page in Edge kiosk mode.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'FactoryOps.Common.ps1')

$config = Read-FactoryOpsConfig
$url = [string]$config.kioskUrl
if ($url -match 'password=') {
    throw 'The kiosk URL must not contain a password.'
}
$parsed = $null
if (-not [Uri]::TryCreate($url, [UriKind]::Absolute, [ref]$parsed)) {
    throw 'The kiosk URL is not absolute. Set kioskUrl in factoryops.config.json.'
}
$path = $parsed.AbsolutePath.TrimEnd('/')
if ($path -ne '/accounts/login') {
    throw 'The kiosk URL must be the FactoryOps login page (/accounts/login/).'
}

$health = Get-FactoryOpsHealthUrl -Config $config
$deadline = (Get-Date).AddSeconds(60)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -Uri $health -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200 -and $response.Content -match '"status"\s*:\s*"ok"') {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $ready) {
    Write-FactoryOpsLog -LogDirectory $config.logDir -Level ERROR -Message 'Kiosk did not open because /health/ did not return ok within 60 seconds. The server task is separate.'
    exit 1
}

$candidates = @(
    (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe')
)
$programFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
if ($programFilesX86) {
    $candidates += (Join-Path $programFilesX86 'Microsoft\Edge\Application\msedge.exe')
}
$edge = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $edge) {
    Write-FactoryOpsLog -LogDirectory $config.logDir -Level ERROR -Message 'Microsoft Edge was not found. The server is still running.'
    exit 1
}

Write-FactoryOpsLog -LogDirectory $config.logDir -Message ("Opening kiosk login {0}" -f $url)
Start-Process -FilePath $edge -ArgumentList @('--kiosk', $url, '--edge-kiosk-type=fullscreen', '--no-first-run')
exit 0
