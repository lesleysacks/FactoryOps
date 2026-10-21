#Requires -Version 5.1
<#
.SYNOPSIS
    Install FactoryOps on a Windows factory PC.

.DESCRIPTION
    Copies the application, creates a virtual environment, writes a production
    environment file only when one does not already exist, migrates, collects
    static files, and registers startup tasks. Re-running does not delete or
    replace the database, media, or SECRET_KEY.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\FactoryOps',
    [string]$Source = '',
    [string]$DesktopUser = '',
    [string]$LanAddress = '',
    [string]$Bind = '0.0.0.0',
    [int]$Port = 8000,
    [switch]$ConfigureFirewall,
    [switch]$SkipTasks
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\FactoryOps.Common.ps1"
. "$PSScriptRoot\FactoryOps.Tasks.ps1"
Assert-FactoryOpsWindows

if (-not $Source) {
    $Source = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}
$layout = Get-FactoryOpsLayout -InstallRoot $InstallRoot
foreach ($dir in @($layout.Root, $layout.App, $layout.Data, $layout.Media, (Split-Path $layout.EnvFile), $layout.Logs, $layout.Backups, $layout.Static, $layout.Releases)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

Write-Host "Installing FactoryOps from $Source to $($layout.Root)"
Copy-FactoryOpsCode -Source $Source -Destination $layout.App

$launcher = Get-FactoryOpsPythonLauncher
if (-not (Test-Path $layout.VenvPython)) {
    Write-Host 'Creating virtual environment.'
    Invoke-FactoryOpsLauncher -Launcher $launcher -Arguments @('-m', 'venv', (Join-Path $layout.Root 'venv'))
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
} else {
    Write-Host 'Virtual environment already exists. Reusing it.'
}

& $layout.VenvPython -m pip install --disable-pip-version-check -r (Join-Path $layout.App 'requirements.txt')
if ($LASTEXITCODE -ne 0) {
    throw 'Installing Python dependencies failed. On an offline PC, install from a wheelhouse and rerun this script.'
}

if (-not (Test-Path $layout.EnvFile)) {
    Write-Host 'Creating the production environment file and a new SECRET_KEY. This happens once.'
    $generated = & $layout.VenvPython -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
    $generated = ($generated | Out-String).Trim()
    if ($generated.Length -lt 50) {
        throw 'SECRET_KEY generation failed. No environment file was written.'
    }
    $env:FACTORYOPS_NEW_SECRET = $generated
    $env:FACTORYOPS_LAN = $LanAddress
    $env:FACTORYOPS_HOSTNAME = $env:COMPUTERNAME
    $env:FACTORYOPS_BIND = $Bind
    $env:FACTORYOPS_PORT = "$Port"
    $env:FACTORYOPS_SQLITE_PATH = $layout.Database
    $env:FACTORYOPS_MEDIA_ROOT = $layout.Media
    $env:FACTORYOPS_STATIC_ROOT = $layout.Static
    $env:FACTORYOPS_LOG_DIR = $layout.Logs
    $env:FACTORYOPS_BACKUP_DIR = $layout.Backups
    $env:FACTORYOPS_ENV_FILE = $layout.EnvFile
    Push-Location $layout.App
    try {
        & $layout.VenvPython -c "from config.ops.envfile import write_initial_from_environment; write_initial_from_environment()"
        if ($LASTEXITCODE -ne 0) { throw 'Could not write the production environment file.' }
    } finally {
        Pop-Location
        [Environment]::SetEnvironmentVariable('FACTORYOPS_NEW_SECRET', $null, 'Process')
    }
    Protect-FactoryOpsEnvFile -Path $layout.EnvFile
    Write-Host "SECRET_KEY stored in $($layout.EnvFile). It was not printed."
} else {
    Write-Host "Keeping the existing environment file $($layout.EnvFile). SECRET_KEY was not rotated."
}

Write-FactoryOpsPublicFile -Layout $layout -Bind $Bind -Port $Port
Import-FactoryOpsEnv -Path $layout.EnvFile

Push-Location $layout.App
try {
    & $layout.VenvPython -c "import django; django.setup()"
    if ($LASTEXITCODE -ne 0) {
        throw 'Production configuration is invalid. Fix the environment file. The database file was not deleted.'
    }
    & $layout.VenvPython manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) {
        throw 'Database migration failed. The existing database file was not deleted.'
    }
    & $layout.VenvPython manage.py collectstatic --noinput
    if ($LASTEXITCODE -ne 0) { throw 'collectstatic failed.' }
    & $layout.VenvPython manage.py check --deploy
    if ($LASTEXITCODE -ne 0) { throw 'Django deployment checks reported an error.' }
} finally {
    Pop-Location
}

if ($ConfigureFirewall) {
    & netsh.exe advfirewall firewall delete rule name="FactoryOps LAN" | Out-Null
    & netsh.exe advfirewall firewall add rule name="FactoryOps LAN" dir=in action=allow protocol=TCP localport=$Port profile=private,domain | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not add the private-network firewall rule. Run from an elevated PowerShell.'
    }
    Write-Host "Firewall allows inbound TCP $Port on Private and Domain profiles only."
}

if (-not $SkipTasks) {
    $startScript = Join-Path $PSScriptRoot 'Start-FactoryOps.ps1'
    $backupScript = Join-Path $PSScriptRoot 'Backup-FactoryOps.ps1'
    $openScript = Join-Path $PSScriptRoot 'Open-FactoryOps.ps1'
    $taskDir = Join-Path $layout.Root 'config\tasks'
    New-Item -ItemType Directory -Force -Path $taskDir | Out-Null
    $serverXml = Join-Path $taskDir 'FactoryOps-Server.xml'
    $backupXml = Join-Path $taskDir 'FactoryOps-Backup.xml'
    Set-Content -Path $serverXml -Encoding Unicode -Value (New-FactoryOpsServerTaskXml -ScriptPath $startScript -InstallRoot $layout.Root)
    Set-Content -Path $backupXml -Encoding Unicode -Value (New-FactoryOpsBackupTaskXml -ScriptPath $backupScript -InstallRoot $layout.Root)
    Register-FactoryOpsTask -Name 'FactoryOps Server' -XmlPath $serverXml
    Register-FactoryOpsTask -Name 'FactoryOps Backup' -XmlPath $backupXml
    if ($DesktopUser) {
        $browserXml = Join-Path $taskDir 'FactoryOps-Browser.xml'
        Set-Content -Path $browserXml -Encoding Unicode -Value (New-FactoryOpsBrowserTaskXml -ScriptPath $openScript -InstallRoot $layout.Root -DesktopUser $DesktopUser)
        Register-FactoryOpsTask -Name 'FactoryOps Browser' -XmlPath $browserXml
    } else {
        Write-Host 'No -DesktopUser was given. The login window will not open at sign-in until you register it.'
    }
    New-FactoryOpsShortcut -Layout $layout -OpenScript $openScript
    & schtasks.exe /Run /TN 'FactoryOps Server' | Out-Null
}

Write-Host ''
Write-Host 'FactoryOps files are installed. The development server was not started.'
Write-Host "Create the first administrator yourself (do not put the password in a script):"
Write-Host "  cd $($layout.App)"
Write-Host "  ..\venv\Scripts\python.exe manage.py createsuperuser"
Write-Host 'Log in through the existing FactoryOps login page. No account is signed in automatically.'
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
