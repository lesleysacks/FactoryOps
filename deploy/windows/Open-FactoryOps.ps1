#Requires -Version 5.1
<#
.SYNOPSIS
    Open the existing FactoryOps login page after the server is healthy.

.DESCRIPTION
    Does not sign anyone in and does not embed a password. If the login window
    is already open, this script exits without opening another one.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\FactoryOps'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\FactoryOps.Common.ps1"
Assert-FactoryOpsWindows
$layout = Get-FactoryOpsLayout -InstallRoot $InstallRoot
$port = Get-FactoryOpsPort -Layout $layout
$loginUrl = "http://127.0.0.1:$port/accounts/login/"

$mutex = New-Object System.Threading.Mutex($false, 'Global\FactoryOpsBrowserLauncher')
$owned = $false
try {
    $owned = $mutex.WaitOne(0)
} catch [System.Threading.AbandonedMutexException] {
    $owned = $true
}
if (-not $owned) {
    exit 0
}

try {
    $already = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^(msedge|chrome)\.exe$' -and
            $_.CommandLine -and
            $_.CommandLine.Contains($loginUrl)
        }
    if ($already) {
        Write-Host 'FactoryOps login window is already open.'
        exit 0
    }

    $ready = Wait-FactoryOpsHealth -Port $port -Seconds 120
    if ($ready -ne 0) {
        $log = Join-Path $layout.Logs 'factoryops.log'
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "FactoryOps did not become ready. The server is separate from this window and nobody was signed in. Ask a supervisor to read $log and start the FactoryOps Server task.",
            'FactoryOps'
        ) | Out-Null
        exit 1
    }

    $edge = @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if ($edge) {
        Start-Process -FilePath $edge -ArgumentList @("--app=$loginUrl")
        exit 0
    }
    $chrome = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if ($chrome) {
        Start-Process -FilePath $chrome -ArgumentList @("--app=$loginUrl")
        exit 0
    }
    Start-Process $loginUrl
    exit 0
} finally {
    if ($owned) {
        $mutex.ReleaseMutex() | Out-Null
    }
}
