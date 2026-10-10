#Requires -Version 5.1
<#
.SYNOPSIS
  Install FactoryOps on the Windows 11 factory PC and register startup tasks.

.DESCRIPTION
  Creates a virtual environment, installs production dependencies, applies
  migrations, collects static files, and registers a SYSTEM startup task.
  Re-running this script updates the same tasks. It does not overwrite an
  existing .env and it does not delete the database or uploaded photos.

  Run from an elevated PowerShell window. Do not point ProjectRoot at a
  user profile; the startup task runs as SYSTEM.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [string]$PythonExe = 'python',
    [int]$Port = 8000,
    [string]$Bind = '0.0.0.0',
    [string]$KioskUrl = '',
    [string]$LogDir = '',
    [string]$BackupDir = '',
    [int]$RetentionDays = 14,
    [string]$DisplayUser = '',
    [string]$FirewallRemoteAddress = 'LocalSubnet',
    [switch]$SkipFirewall,
    [switch]$SkipBackupTask
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'FactoryOps.Common.ps1')

function Resolve-FullPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($Path)
}

Assert-FactoryOpsAdministrator

if ($ProjectRoot.Contains('"')) {
    throw 'ProjectRoot cannot contain double quotes.'
}
$ProjectRoot = Resolve-FullPath $ProjectRoot
$manage = Join-Path $ProjectRoot 'manage.py'
if (-not (Test-Path -LiteralPath $manage)) {
    throw "manage.py was not found in $ProjectRoot"
}
if ($ProjectRoot -match '\\Users\\') {
    Write-Warning 'ProjectRoot is under a user profile. SYSTEM may be unable to read it after reboot. Use C:\FactoryOps\app.'
}
if ($RetentionDays -lt 1) {
    throw 'RetentionDays must be at least 1.'
}
if ($Port -lt 1 -or $Port -gt 65535) {
    throw 'Port must be between 1 and 65535.'
}

$parent = Split-Path -Parent $ProjectRoot
if (-not $LogDir) {
    $LogDir = Join-Path $parent 'logs'
}
if (-not $BackupDir) {
    $BackupDir = Join-Path $parent 'backups'
}
$LogDir = Resolve-FullPath $LogDir
$BackupDir = Resolve-FullPath $BackupDir
$databasePath = Join-Path $ProjectRoot 'db.sqlite3'
$mediaRoot = Join-Path $ProjectRoot 'media'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
New-Item -ItemType Directory -Path $mediaRoot -Force | Out-Null

$venvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonExe -m venv (Join-Path $ProjectRoot '.venv')
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not create the virtual environment.'
    }
}
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw 'pip upgrade failed.'
}
& $venvPython -m pip install -r (Join-Path $ProjectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) {
    throw 'Installing requirements.txt failed.'
}

$envFile = Join-Path $ProjectRoot '.env'
$example = Join-Path $ProjectRoot '.env.production.example'
if (-not (Test-Path -LiteralPath $envFile)) {
    if (-not (Test-Path -LiteralPath $example)) {
        throw "Missing $example"
    }
    Copy-Item -LiteralPath $example -Destination $envFile
    throw "Created $envFile from the example. Set SECRET_KEY, ALLOWED_HOSTS, and CSRF_TRUSTED_ORIGINS, then run Install-FactoryOps.ps1 again. The placeholder secret will not start."
}

if (-not $KioskUrl) {
    $fromEnv = Get-FactoryOpsDotEnvValue -Path $envFile -Name 'FACTORYOPS_KIOSK_URL'
    if ($fromEnv) {
        $KioskUrl = $fromEnv
    } else {
        $KioskUrl = 'http://127.0.0.1:{0}/accounts/login/' -f $Port
    }
}

$existingShortcut = ''
$existingDisplay = ''
$configPath = Get-FactoryOpsConfigPath
if (Test-Path -LiteralPath $configPath) {
    $previous = Read-FactoryOpsConfig
    if ($previous.kioskStartupShortcut) {
        $existingShortcut = [string]$previous.kioskStartupShortcut
    }
    if (-not $DisplayUser -and $previous.displayUser) {
        $existingDisplay = [string]$previous.displayUser
    }
}
if (-not $DisplayUser) {
    $DisplayUser = $existingDisplay
}

$config = [ordered]@{
    projectRoot            = $ProjectRoot
    pythonExe              = $venvPython
    port                   = $Port
    bind                   = $Bind
    kioskUrl               = $KioskUrl
    logDir                 = $LogDir
    backupDir              = $BackupDir
    retentionDays          = $RetentionDays
    databasePath           = $databasePath
    mediaRoot              = $mediaRoot
    firewallRemoteAddress  = $FirewallRemoteAddress
    displayUser            = $DisplayUser
    kioskStartupShortcut   = $existingShortcut
}
Write-FactoryOpsConfig $config

$env:DJANGO_SETTINGS_MODULE = 'config.settings.production'
$env:FACTORYOPS_BIND = $Bind
$env:FACTORYOPS_PORT = [string]$Port
$env:FACTORYOPS_LOG_DIR = $LogDir
$env:FACTORYOPS_DB_PATH = $databasePath
$env:FACTORYOPS_MEDIA_ROOT = $mediaRoot
$env:FACTORYOPS_KIOSK_URL = $KioskUrl

& $venvPython (Join-Path $ProjectRoot 'scripts\serve_production.py') --check
if ($LASTEXITCODE -ne 0) {
    throw 'Production configuration check failed. Fix .env and run Install-FactoryOps.ps1 again. Migrations were not applied and startup tasks were not registered.'
}
& $venvPython $manage migrate --noinput
if ($LASTEXITCODE -ne 0) {
    throw 'migrate failed. The database was not reset.'
}
& $venvPython $manage collectstatic --noinput
if ($LASTEXITCODE -ne 0) {
    throw 'collectstatic failed.'
}

$startScript = Join-Path $PSScriptRoot 'Start-FactoryOps.ps1'
$serverArgs = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Service' -f $startScript
$serverAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $serverArgs -WorkingDirectory $ProjectRoot
$serverTrigger = New-ScheduledTaskTrigger -AtStartup
$serverPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$serverSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
Register-ScheduledTask `
    -TaskName $script:FactoryOpsServerTask `
    -Action $serverAction `
    -Trigger $serverTrigger `
    -Principal $serverPrincipal `
    -Settings $serverSettings `
    -Force | Out-Null

if (-not $SkipBackupTask) {
    $backupScript = Join-Path $PSScriptRoot 'Backup-FactoryOps.ps1'
    $backupArgs = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $backupScript
    $backupAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $backupArgs -WorkingDirectory $ProjectRoot
    $backupTrigger = New-ScheduledTaskTrigger -Daily -At '02:00'
    $backupSettings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
        -MultipleInstances IgnoreNew
    Register-ScheduledTask `
        -TaskName $script:FactoryOpsBackupTask `
        -Action $backupAction `
        -Trigger $backupTrigger `
        -Principal $serverPrincipal `
        -Settings $backupSettings `
        -Force | Out-Null
}

if (-not $SkipFirewall) {
    & (Join-Path $PSScriptRoot 'Install-FactoryOpsFirewall.ps1') -Port $Port -RemoteAddress $FirewallRemoteAddress
}

if ($DisplayUser) {
    & (Join-Path $PSScriptRoot 'Register-FactoryOpsKiosk.ps1') -DisplayUser $DisplayUser
}

Write-FactoryOpsLog -LogDirectory $LogDir -Message ("Install finished. Config {0}" -f (Get-FactoryOpsConfigPath))
Write-Host 'Start the server with:  .\deploy\windows\Start-FactoryOps.ps1'
Write-Host 'Status:                  .\deploy\windows\Get-FactoryOpsStatus.ps1'
Write-Host 'The startup task runs at the next boot even if nobody signs in.'
