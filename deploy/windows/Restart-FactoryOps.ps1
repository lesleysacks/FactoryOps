#Requires -Version 5.1
<#
.SYNOPSIS
  Stop FactoryOps and start it again through Task Scheduler.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'FactoryOps.Common.ps1')

& (Join-Path $PSScriptRoot 'Stop-FactoryOps.ps1')
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
Start-Sleep -Seconds 2
& (Join-Path $PSScriptRoot 'Start-FactoryOps.ps1')
exit $LASTEXITCODE
