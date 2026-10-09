#Requires -Version 5.1
<#
.SYNOPSIS
    Restore a verified backup.

.DESCRIPTION
    Without -ReplaceLive the target must not be the live data directory.
    Replacing live data requires the confirmation text and a stopped server.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Backup,
    [Parameter(Mandatory = $true)][string]$Target,
    [string]$InstallRoot = 'C:\FactoryOps',
    [switch]$ReplaceLive,
    [string]$ConfirmReplace = ''
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\FactoryOps.Common.ps1"
Assert-FactoryOpsWindows
if ($ReplaceLive -and $ConfirmReplace -ne 'REPLACE LIVE DATA') {
    throw 'Refusing to replace live data. Re-run with -ConfirmReplace "REPLACE LIVE DATA" only after the server is stopped.'
}
$layout = Get-FactoryOpsLayout -InstallRoot $InstallRoot
if ($ReplaceLive) {
    Stop-FactoryOpsServerTask -Layout $layout
}
Import-FactoryOpsEnv -Path $layout.EnvFile
$arguments = @('manage.py', 'restore_factoryops', '--backup', $Backup, '--target', $Target)
if ($ReplaceLive) {
    $arguments += '--replace-live'
}
Push-Location $layout.App
try {
    & $layout.VenvPython @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
