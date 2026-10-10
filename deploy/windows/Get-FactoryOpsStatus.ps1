#Requires -Version 5.1
<#
.SYNOPSIS
  Show the scheduled task, the listening process, recent log lines, and /health/.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'FactoryOps.Common.ps1')

$config = Read-FactoryOpsConfig
$healthy = $false

$task = Get-ScheduledTask -TaskName $script:FactoryOpsServerTask -ErrorAction SilentlyContinue
if ($task) {
    $info = Get-ScheduledTaskInfo -TaskName $script:FactoryOpsServerTask
    Write-Host ("Task {0} state={1} lastResult={2} lastRun={3}" -f $task.TaskName, $task.State, $info.LastTaskResult, $info.LastRunTime)
} else {
    Write-Host 'Task FactoryOpsServer is not registered.'
}

$listener = Get-FactoryOpsListeningProcess -Port ([int]$config.port)
if ($listener) {
    $ours = Test-FactoryOpsServerProcess -Process $listener
    Write-Host ("Listen port {0} pid {1} factoryops={2}" -f $config.port, $listener.ProcessId, $ours)
} else {
    Write-Host ("Nothing is listening on port {0}." -f $config.port)
}

$logPath = Join-Path $config.logDir 'operations.log'
if (Test-Path -LiteralPath $logPath) {
    Write-Host '--- operations.log (last 20 lines) ---'
    Get-Content -LiteralPath $logPath -Tail 20
}

$url = Get-FactoryOpsHealthUrl -Config $config
try {
    $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
    Write-Host ("Health {0} {1}" -f $response.StatusCode, $response.Content)
    if ($response.StatusCode -eq 200 -and $response.Content -match '"status"\s*:\s*"ok"') {
        $healthy = $true
    }
} catch {
    Write-Host ("Health request failed: {0}" -f $_.Exception.Message)
}

if ($healthy) {
    exit 0
}
exit 1
