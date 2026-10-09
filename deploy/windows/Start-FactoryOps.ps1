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
