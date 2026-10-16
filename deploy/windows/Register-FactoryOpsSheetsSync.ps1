#Requires -Version 5.1
<#
.SYNOPSIS
  Register the optional FactoryOps Google Sheets sync task.

.DESCRIPTION
  Creates or updates the FactoryOpsSheetsSync scheduled task. The task runs
  once an hour as SYSTEM and calls Run-FactoryOpsSheetsSync.ps1. It does not
  change the database, .env, or the server task. Re-running this script
  replaces the same task. Uninstall-FactoryOps.ps1 removes it.

  Leave this unregistered until GOOGLE_SHEETS_ENABLED=True and the
  credentials file is in place outside the git checkout.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [int]$IntervalMinutes = 60
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'FactoryOps.Common.ps1')

Assert-FactoryOpsAdministrator

if ($IntervalMinutes -lt 15 -or $IntervalMinutes -gt 1440) {
    throw 'IntervalMinutes must be between 15 and 1440.'
}

$config = Read-FactoryOpsConfig
$projectRoot = [string]$config.projectRoot
$runner = Join-Path $PSScriptRoot 'Run-FactoryOpsSheetsSync.ps1'
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Missing $runner"
}

if (-not $PSCmdlet.ShouldProcess($script:FactoryOpsSheetsTask, 'Register the Google Sheets sync task')) {
    Write-Host 'Registration cancelled. No task was changed.'
    exit 0
}

$argument = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $runner
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument -WorkingDirectory $projectRoot
$start = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 9999)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $script:FactoryOpsSheetsTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host ("Registered {0}. It runs every {1} minutes and does not replace the FactoryOps server task." -f $script:FactoryOpsSheetsTask, $IntervalMinutes)
Write-Host 'If Google Sheets is disabled, each run exits without calling Google.'
exit 0
