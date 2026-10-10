#Requires -Version 5.1
<#
.SYNOPSIS
  Start the FactoryOps production server.

.DESCRIPTION
  Without -Service, this asks Task Scheduler to start FactoryOpsServer.
  The scheduled task runs this same script with -Service, which keeps
  Waitress in the foreground so a crash can be restarted by the task.
  If this project's server already owns the port, the script exits 0.
#>
[CmdletBinding()]
param(
    [switch]$Service
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'FactoryOps.Common.ps1')

$config = Read-FactoryOpsConfig
if (-not $Service) {
    try {
        Start-ScheduledTask -TaskName $script:FactoryOpsServerTask
        Write-FactoryOpsLog -LogDirectory $config.logDir -Message 'Requested FactoryOpsServer start.'
    } catch {
        $listener = Get-FactoryOpsListeningProcess -Port ([int]$config.port)
        if ($listener -and (Test-FactoryOpsServerProcess -Process $listener)) {
            Write-FactoryOpsLog -LogDirectory $config.logDir -Message 'FactoryOpsServer is already running.'
            exit 0
        }
        Write-FactoryOpsLog -LogDirectory $config.logDir -Level ERROR -Message $_.Exception.Message
        exit 1
    }
    exit 0
}

$port = [int]$config.port
$listener = Get-FactoryOpsListeningProcess -Port $port
if ($listener) {
    if (Test-FactoryOpsServerProcess -Process $listener) {
        Write-FactoryOpsLog -LogDirectory $config.logDir -Message ("FactoryOps already listening on port {0}." -f $port)
        exit 0
    }
    Write-FactoryOpsLog -LogDirectory $config.logDir -Level ERROR -Message ("Port {0} is in use by another program (pid {1})." -f $port, $listener.ProcessId)
    exit 1
}

$env:DJANGO_SETTINGS_MODULE = 'config.settings.production'
$env:FACTORYOPS_BIND = [string]$config.bind
$env:FACTORYOPS_PORT = [string]$config.port
$env:FACTORYOPS_LOG_DIR = [string]$config.logDir
$env:FACTORYOPS_DB_PATH = [string]$config.databasePath
$env:FACTORYOPS_MEDIA_ROOT = [string]$config.mediaRoot
$env:FACTORYOPS_KIOSK_URL = [string]$config.kioskUrl

$python = [string]$config.pythonExe
$serve = Join-Path $config.projectRoot 'scripts\serve_production.py'
$serverLog = Join-Path $config.logDir 'server.log'
Write-FactoryOpsLog -LogDirectory $config.logDir -Message ("Starting {0} {1}" -f $python, $serve)
Set-Location -LiteralPath $config.projectRoot
& $python $serve >> $serverLog 2>&1
$code = $LASTEXITCODE
if (-not $code) {
    $code = 0
}
Write-FactoryOpsLog -LogDirectory $config.logDir -Level $(if ($code -eq 0) { 'INFO' } else { 'ERROR' }) -Message ("FactoryOps server process exited {0}." -f $code)
exit $code
