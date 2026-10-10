# Shared helpers for the FactoryOps Windows scripts.
# ASCII only, so Windows PowerShell 5.1 reads this file without a BOM.

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:FactoryOpsServerTask = 'FactoryOpsServer'
$script:FactoryOpsBackupTask = 'FactoryOpsBackup'
$script:FactoryOpsFirewallName = 'FactoryOps LAN'

function Get-FactoryOpsConfigPath {
    if (-not $env:ProgramData) {
        throw 'ProgramData is not set. These scripts are for Windows.'
    }
    return (Join-Path $env:ProgramData 'FactoryOps\factoryops.config.json')
}

function Read-FactoryOpsConfig {
    $path = Get-FactoryOpsConfigPath
    if (-not (Test-Path -LiteralPath $path)) {
        throw "FactoryOps is not installed. Missing $path. Run Install-FactoryOps.ps1 first."
    }
    return (Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Write-FactoryOpsConfig {
    param($Config)
    $path = Get-FactoryOpsConfigPath
    $directory = Split-Path -Parent $path
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $json = $Config | ConvertTo-Json -Depth 6
    Set-Content -LiteralPath $path -Value $json -Encoding UTF8
}

function Assert-FactoryOpsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $admin = [Security.Principal.WindowsBuiltInRole]::Administrator
    if (-not $principal.IsInRole($admin)) {
        throw 'Run this script from an elevated PowerShell window (Run as administrator).'
    }
}

function Get-FactoryOpsDotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    foreach ($line in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        if ($line -match ('^\s*' + [Regex]::Escape($Name) + '=(.*)$')) {
            return $Matches[1].Trim()
        }
    }
    return $null
}

function Write-FactoryOpsLog {
    param(
        [Parameter(Mandatory = $true)][string]$LogDirectory,
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet('INFO', 'ERROR')][string]$Level = 'INFO'
    )
    $stamp = Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK'
    $line = '{0} {1} {2}' -f $stamp, $Level, $Message
    if (-not (Test-Path -LiteralPath $LogDirectory)) {
        New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    }
    $logPath = Join-Path $LogDirectory 'operations.log'
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
    if ($Level -eq 'ERROR') {
        [Console]::Error.WriteLine($line)
    } else {
        Write-Host $line
    }
}

function Get-FactoryOpsListeningProcess {
    param([Parameter(Mandatory = $true)][int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $connection) {
        return $null
    }
    $filter = 'ProcessId={0}' -f [int]$connection.OwningProcess
    return (Get-CimInstance Win32_Process -Filter $filter)
}

function Test-FactoryOpsServerProcess {
    param($Process)
    if (-not $Process) {
        return $false
    }
    $command = [string]$Process.CommandLine
    return ($command -like '*serve_production.py*')
}

function Get-FactoryOpsHealthUrl {
    param($Config)
    return ('http://127.0.0.1:{0}/health/' -f [int]$Config.port)
}
