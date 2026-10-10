#Requires -Version 5.1
<#
.SYNOPSIS
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
