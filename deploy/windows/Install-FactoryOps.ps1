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
