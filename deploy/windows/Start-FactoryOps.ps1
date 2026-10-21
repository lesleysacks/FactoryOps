#Requires -Version 5.1
<#
.SYNOPSIS
    Start the FactoryOps production server if it is not already healthy.

.DESCRIPTION
    Loads the production environment, validates settings, and runs Waitress.
    Does not run database migrations and does not open a browser.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\FactoryOps'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\FactoryOps.Common.ps1"
Assert-FactoryOpsWindows
$layout = Get-FactoryOpsLayout -InstallRoot $InstallRoot
if (-not (Test-Path $layout.VenvPython)) {
    throw "FactoryOps is not installed at $($layout.Root)."
}
Import-FactoryOpsEnv -Path $layout.EnvFile
$bind = if ($env:FACTORYOPS_BIND) { $env:FACTORYOPS_BIND } else { '0.0.0.0' }
$port = if ($env:FACTORYOPS_PORT) { [int]$env:FACTORYOPS_PORT } else { 8000 }
if ($bind -eq '*') {
    throw 'FACTORYOPS_BIND must not be "*". Use 0.0.0.0 for the factory LAN or 127.0.0.1 for this PC only.'
}

$mutex = New-Object System.Threading.Mutex($false, 'Global\FactoryOpsServer')
$owned = $false
try {
    try {
        $owned = $mutex.WaitOne(0)
    } catch [System.Threading.AbandonedMutexException] {
        $owned = $true
    }
    if (-not $owned) {
        Write-Host 'Another FactoryOps server start is in progress.'
        exit (Wait-FactoryOpsHealth -Port $port -Seconds 120)
    }
    if (Test-FactoryOpsHealth -Port $port) {
        Write-Host "FactoryOps is already healthy on port $port."
        exit 0
    }
    New-Item -ItemType Directory -Force -Path $layout.Logs | Out-Null
    Set-Content -Path $layout.PidFile -Value $PID -Encoding ASCII
    $consoleLog = Join-Path $layout.Logs 'server-console.log'
    Push-Location $layout.App
    try {
        & $layout.VenvPython -c "import django; django.setup()" *>> $consoleLog
        if ($LASTEXITCODE -ne 0) {
            throw "Production configuration is invalid. See $consoleLog. Database migrations were not run."
        }
        Write-Host "Starting Waitress on ${bind}:${port}."
        & $layout.VenvPython -m waitress --listen="${bind}:${port}" --threads=4 config.wsgi:application *>> $consoleLog
        exit $LASTEXITCODE
    } finally {
        Pop-Location
    }
} finally {
    if ($owned) {
        $mutex.ReleaseMutex() | Out-Null
    }
}
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
