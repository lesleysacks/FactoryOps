#Requires -Version 5.1
<#
.SYNOPSIS
  Open the FactoryOps login page when a standard display account signs in.

.DESCRIPTION
  Places a Startup-folder shortcut for that user only. It does not store
  sign-in credentials and it does not change Windows sign-in policy. The
  web server keeps running if the browser is closed.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$DisplayUser
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'FactoryOps.Common.ps1')

Assert-FactoryOpsAdministrator

if ($DisplayUser -match '[\\"]') {
    throw 'DisplayUser must be a local account name without a domain prefix.'
}

$account = Get-LocalUser -Name $DisplayUser -ErrorAction SilentlyContinue
if (-not $account) {
    throw "Local user $DisplayUser does not exist. Create a standard account in Settings, sign in once so Windows creates the profile, then run this script again."
}
$admins = @(Get-LocalGroupMember -Group 'Administrators' | Where-Object { $_.Name -match ('\\' + [Regex]::Escape($DisplayUser) + '$') })
if ($admins.Count -gt 0) {
    throw 'The display account must be a standard user, not an administrator.'
}

$profile = Get-CimInstance Win32_UserProfile | Where-Object { $_.LocalPath -and ($_.LocalPath -match ('\\' + [Regex]::Escape($DisplayUser) + '$')) } | Select-Object -First 1
if (-not $profile) {
    throw "No profile for $DisplayUser. Sign in to that account once, sign out, then run this script again."
}

$config = Read-FactoryOpsConfig
$startup = Join-Path $profile.LocalPath 'AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup'
if (-not (Test-Path -LiteralPath $startup)) {
    New-Item -ItemType Directory -Path $startup -Force | Out-Null
}

$kioskScript = Join-Path $PSScriptRoot 'Start-FactoryOpsKiosk.ps1'
$shortcutPath = Join-Path $startup 'FactoryOps Kiosk.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = 'powershell.exe'
$shortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $kioskScript
$shortcut.WorkingDirectory = [string]$config.projectRoot
$shortcut.WindowStyle = 7
$shortcut.Description = 'Open the FactoryOps login page in full screen'
$shortcut.Save()

$updated = [ordered]@{
    projectRoot           = [string]$config.projectRoot
    pythonExe             = [string]$config.pythonExe
    port                  = [int]$config.port
    bind                  = [string]$config.bind
    kioskUrl              = [string]$config.kioskUrl
    logDir                = [string]$config.logDir
    backupDir             = [string]$config.backupDir
    retentionDays         = [int]$config.retentionDays
    databasePath          = [string]$config.databasePath
    mediaRoot             = [string]$config.mediaRoot
    firewallRemoteAddress = [string]$config.firewallRemoteAddress
    displayUser           = $DisplayUser
    kioskStartupShortcut  = $shortcutPath
}
Write-FactoryOpsConfig $updated
Write-Host ("Kiosk shortcut written to {0}" -f $shortcutPath)
Write-Host 'It runs only after that display account signs in. The server does not depend on it.'
