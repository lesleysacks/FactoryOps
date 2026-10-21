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
  Restore a backup into a new folder. Confirmation is required.

.DESCRIPTION
  This refuses to overwrite the live database. Stop the server yourself
  before you manually promote a restored copy.
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory = $true)][string]$Backup,
    [Parameter(Mandatory = $true)][string]$Destination
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'FactoryOps.Common.ps1')

$config = Read-FactoryOpsConfig
if (-not $PSCmdlet.ShouldProcess($Destination, 'Restore FactoryOps into a separate folder. The live database will not be overwritten.')) {
    Write-Host 'Nothing was written.'
    exit 1
}

$python = [string]$config.pythonExe
$script = Join-Path $config.projectRoot 'scripts\restore_factoryops.py'
& $python $script `
    --backup $Backup `
    --destination $Destination `
    --live-database ([string]$config.databasePath) `
    --confirm
$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-FactoryOpsLog -LogDirectory $config.logDir -Level ERROR -Message ("RESTORE FAILED with exit code {0}." -f $code)
    exit $code
}
Write-FactoryOpsLog -LogDirectory $config.logDir -Message ("RESTORE OK {0}" -f $Destination)
exit 0
