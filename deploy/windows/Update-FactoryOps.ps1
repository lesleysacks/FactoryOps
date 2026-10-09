#Requires -Version 5.1
<#
.SYNOPSIS
    Update FactoryOps code after a verified backup. Does not delete the database.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\FactoryOps',
    [string]$Source = ''
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\FactoryOps.Common.ps1"
Assert-FactoryOpsWindows
if (-not $Source) {
    $Source = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}
$layout = Get-FactoryOpsLayout -InstallRoot $InstallRoot
Import-FactoryOpsEnv -Path $layout.EnvFile
Push-Location $layout.App
try {
    & $layout.VenvPython manage.py backup_factoryops
    if ($LASTEXITCODE -ne 0) {
        throw 'Backup failed. Update stopped before any code or database change.'
    }
} finally {
    Pop-Location
}

Stop-FactoryOpsServerTask -Layout $layout
$stamp = Get-Date -Format 'yyyyMMddTHHmmss'
$release = Join-Path $layout.Releases "app-$stamp"
Copy-FactoryOpsCode -Source $layout.App -Destination $release
Copy-FactoryOpsCode -Source $Source -Destination $layout.App
& $layout.VenvPython -m pip install --disable-pip-version-check -r (Join-Path $layout.App 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency install failed. Previous code snapshot: ' + $release }

Push-Location $layout.App
try {
    & $layout.VenvPython manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) {
        throw "Migration failed. Database file was not deleted. Code snapshot: $release. Roll back with Rollback-FactoryOps.ps1 -Release `"$release`"."
    }
    & $layout.VenvPython manage.py collectstatic --noinput
    if ($LASTEXITCODE -ne 0) { throw 'collectstatic failed.' }
    & $layout.VenvPython manage.py check --deploy
    if ($LASTEXITCODE -ne 0) { throw 'Deployment checks failed.' }
} finally {
    Pop-Location
}
& schtasks.exe /Run /TN 'FactoryOps Server' | Out-Null
Write-Host "Update applied. Previous code snapshot: $release"
Write-Host 'The pre-update backup is the newest verified folder under ' $layout.Backups
