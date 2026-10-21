#Requires -Version 5.1
<#
.SYNOPSIS
    Restore a verified backup into a new temporary folder. Does not change live data.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Backup,
    [string]$InstallRoot = 'C:\FactoryOps'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\FactoryOps.Common.ps1"
Assert-FactoryOpsWindows
$layout = Get-FactoryOpsLayout -InstallRoot $InstallRoot
Import-FactoryOpsEnv -Path $layout.EnvFile
$target = Join-Path $env:TEMP ('FactoryOps-restore-test-' + (Get-Date -Format 'yyyyMMddTHHmmss'))
Push-Location $layout.App
try {
    & $layout.VenvPython manage.py restore_factoryops --backup $Backup --target $target
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Restore test passed. Files are in $target. The live database was not replaced."
} finally {
    Pop-Location
}
