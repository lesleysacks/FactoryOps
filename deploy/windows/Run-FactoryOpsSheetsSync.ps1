#Requires -Version 5.1
<#
.SYNOPSIS
  Run one Google Sheets sync using the factory PC production settings.

.DESCRIPTION
  Reads the ProgramData config written by Install-FactoryOps.ps1 and calls
  manage.py sync_google_sheets. When the integration is disabled, that
  command exits successfully and does not contact Google. This script does
  not print .env and does not delete the database.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'FactoryOps.Common.ps1')

$config = Read-FactoryOpsConfig
$python = [string]$config.pythonExe
$manage = Join-Path ([string]$config.projectRoot) 'manage.py'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python was not found at $python. Run Install-FactoryOps.ps1 first."
}
if (-not (Test-Path -LiteralPath $manage)) {
    throw "manage.py was not found at $manage."
}

$env:DJANGO_SETTINGS_MODULE = 'config.settings.production'
& $python $manage sync_google_sheets
exit $LASTEXITCODE
