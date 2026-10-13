#Requires -Version 5.1
<#
.SYNOPSIS
  Stop the FactoryOps scheduled task and its server process.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'FactoryOps.Common.ps1')

$config = Read-FactoryOpsConfig
$task = Get-ScheduledTask -TaskName $script:FactoryOpsServerTask -ErrorAction SilentlyContinue
if ($task) {
    Stop-ScheduledTask -TaskName $script:FactoryOpsServerTask -ErrorAction SilentlyContinue
}

$listener = Get-FactoryOpsListeningProcess -Port ([int]$config.port)
if ($listener) {
    if (-not (Test-FactoryOpsServerProcess -Process $listener)) {
        Write-FactoryOpsLog -LogDirectory $config.logDir -Level ERROR -Message ("Port {0} is owned by pid {1}, which is not FactoryOps. It was left running." -f $config.port, $listener.ProcessId)
        exit 1
    }
    Stop-Process -Id ([int]$listener.ProcessId) -Force
    Write-FactoryOpsLog -LogDirectory $config.logDir -Message ("Stopped FactoryOps pid {0}." -f $listener.ProcessId)
} else {
    Write-FactoryOpsLog -LogDirectory $config.logDir -Message 'FactoryOps server is not listening.'
}
exit 0
