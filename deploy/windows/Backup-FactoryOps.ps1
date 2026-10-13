#Requires -Version 5.1
<#
.SYNOPSIS
  Run the database-safe FactoryOps backup and record a visible failure.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'FactoryOps.Common.ps1')

$config = Read-FactoryOpsConfig
$python = [string]$config.pythonExe
$script = Join-Path $config.projectRoot 'scripts\backup_factoryops.py'
$arguments = @(
    $script,
    '--database', [string]$config.databasePath,
    '--media', [string]$config.mediaRoot,
    '--destination', [string]$config.backupDir,
    '--retention-days', [string]$config.retentionDays,
    '--application-root', [string]$config.projectRoot
)

Write-FactoryOpsLog -LogDirectory $config.logDir -Message ("Backup starting to {0}" -f $config.backupDir)
& $python @arguments
$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-FactoryOpsLog -LogDirectory $config.logDir -Level ERROR -Message ("BACKUP FAILED with exit code {0}. See the message above. Live data was not deleted." -f $code)
    exit $code
}
Write-FactoryOpsLog -LogDirectory $config.logDir -Message 'BACKUP OK'
exit 0
