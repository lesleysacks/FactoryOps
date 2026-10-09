#Requires -Version 5.1
<#
.SYNOPSIS
    Stop the FactoryOps server process. Does not delete data.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\FactoryOps'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\FactoryOps.Common.ps1"
Assert-FactoryOpsWindows
$layout = Get-FactoryOpsLayout -InstallRoot $InstallRoot
Stop-FactoryOpsServerTask -Layout $layout
Write-Host 'FactoryOps server stop requested. Database and media files were not deleted.'
