#Requires -Version 5.1
<#
.SYNOPSIS
    Run a verified database and media backup. Leaves the server running.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\FactoryOps'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\FactoryOps.Common.ps1"
Assert-FactoryOpsWindows
$layout = Get-FactoryOpsLayout -InstallRoot $InstallRoot
Import-FactoryOpsEnv -Path $layout.EnvFile
Push-Location $layout.App
try {
    & $layout.VenvPython manage.py backup_factoryops
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
