#Requires -Version 5.1
<#
.SYNOPSIS
    Add a LAN address to ALLOWED_HOSTS without rotating SECRET_KEY.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$LanAddress,
    [string]$InstallRoot = 'C:\FactoryOps',
    [int]$Port = 0,
    [switch]$Https
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\FactoryOps.Common.ps1"
Assert-FactoryOpsWindows
if ($LanAddress -eq '*' -or $LanAddress.Contains('*')) {
    throw 'Do not use a wildcard LAN address.'
}
$layout = Get-FactoryOpsLayout -InstallRoot $InstallRoot
if ($Port -le 0) {
    $Port = Get-FactoryOpsPort -Layout $layout
}
$arguments = @(
    'manage.py', 'configure_lan',
    '--env-file', $layout.EnvFile,
    '--lan', $LanAddress,
    '--hostname', $env:COMPUTERNAME,
    '--port', "$Port"
)
if ($Https) { $arguments += '--https' }
Push-Location $layout.App
try {
    & $layout.VenvPython @arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
$bind = '0.0.0.0'
if (Test-Path $layout.PublicFile) {
    foreach ($line in Get-Content $layout.PublicFile) {
        if ($line.StartsWith('FACTORYOPS_BIND=')) { $bind = $line.Split('=', 2)[1].Trim() }
    }
}
Write-FactoryOpsPublicFile -Layout $layout -Bind $bind -Port $Port
Stop-FactoryOpsServerTask -Layout $layout
Start-Sleep -Seconds 2
& schtasks.exe /Run /TN 'FactoryOps Server' | Out-Null
Write-Host "LAN host updated. Restart requested. SECRET_KEY was not printed or rotated."
