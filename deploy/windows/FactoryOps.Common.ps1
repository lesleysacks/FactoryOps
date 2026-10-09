# Shared helpers for FactoryOps Windows scripts.
# ASCII on purpose so Windows PowerShell 5.1 reads the file without a BOM.

$ErrorActionPreference = 'Stop'

function Get-FactoryOpsRoot {
    param([string]$InstallRoot)
    if ($InstallRoot) {
        return $InstallRoot
    }
    return 'C:\FactoryOps'
}

function Get-FactoryOpsLayout {
    param([string]$InstallRoot)
    $root = Get-FactoryOpsRoot -InstallRoot $InstallRoot
    $app = Join-Path $root 'app'
    return [ordered]@{
        Root       = $root
        App        = $app
        VenvPython = Join-Path $root 'venv\Scripts\python.exe'
        EnvFile    = Join-Path $root 'config\factoryops.env'
        PublicFile = Join-Path $root 'config\factoryops.public'
        Data       = Join-Path $root 'data'
        Media      = Join-Path $root 'data\media'
        Database   = Join-Path $root 'data\db.sqlite3'
        Logs       = Join-Path $root 'logs'
        Backups    = Join-Path $root 'backups'
        Static     = Join-Path $root 'staticfiles'
        Releases   = Join-Path $root 'releases'
        PidFile    = Join-Path $root 'logs\server.pid'
    }
}

function Assert-FactoryOpsWindows {
    if ($env:OS -ne 'Windows_NT') {
        throw 'These scripts are for the factory Windows PC. They were not run on Windows.'
    }
}

function Get-FactoryOpsPythonLauncher {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
        if ($LASTEXITCODE -ne 0) {
            throw 'Python 3.12 or newer is required. Install it from python.org and enable the py launcher.'
        }
        return @('py', '-3')
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
        if ($LASTEXITCODE -ne 0) {
            throw 'Python 3.12 or newer is required.'
        }
        return @('python')
    }
    throw 'Python 3.12 or newer was not found on PATH. Install Python, then run the installer again.'
}

function Invoke-FactoryOpsLauncher {
    param([string[]]$Launcher, [string[]]$Arguments)
    $prefix = @()
    if ($Launcher.Length -gt 1) {
        $prefix = $Launcher[1..($Launcher.Length - 1)]
    }
    & $Launcher[0] @($prefix + $Arguments)
}

function Import-FactoryOpsEnv {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        throw "Environment file not found: $Path. Run Install-FactoryOps.ps1 first. Do not start with the development server."
    }
    foreach ($line in Get-Content -Path $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) {
            continue
        }
        $parts = $trimmed.Split('=', 2)
        if ($parts.Length -ne 2) {
            continue
        }
        [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), 'Process')
    }
    $env:DJANGO_SETTINGS_MODULE = 'config.settings.production'
}

function Get-FactoryOpsPort {
    param($Layout)
    $port = 8000
    if (Test-Path $Layout.PublicFile) {
        foreach ($line in Get-Content -Path $Layout.PublicFile -Encoding UTF8) {
            if ($line.StartsWith('FACTORYOPS_PORT=')) {
                $port = [int]$line.Split('=', 2)[1].Trim()
            }
        }
    }
    return $port
}

function Test-FactoryOpsHealth {
    param([int]$Port)
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health/" -UseBasicParsing -TimeoutSec 3
        return ($response.StatusCode -eq 200 -and $response.Content -match '"status"\s*:\s*"ok"')
    } catch {
        return $false
    }
}

function Wait-FactoryOpsHealth {
    param([int]$Port, [int]$Seconds = 120)
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        if (Test-FactoryOpsHealth -Port $Port) {
            return 0
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    return 1
}

function Protect-FactoryOpsEnvFile {
    param([string]$Path)
    # SYSTEM read, Administrators full control. The desktop user does not need the secret.
    & icacls $Path /inheritance:r /grant:r '*S-1-5-18:(R)' '*S-1-5-32-544:(F)' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not restrict permissions on $Path."
    }
}

function Copy-FactoryOpsCode {
    param([string]$Source, [string]$Destination)
    if (-not (Test-Path $Source)) {
        throw "Source directory does not exist: $Source"
    }
    if ((Test-Path $Destination) -and ((Resolve-Path $Source).Path -eq (Resolve-Path $Destination).Path)) {
        Write-Host 'Source and application directory are the same. Leaving application files in place.'
        return
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    & robocopy $Source $Destination /E /R:2 /W:2 /NFL /NDL /NJH /NJS `
        /XD .git .venv venv media logs backups staticfiles releases __pycache__ .pytest_cache .mypy_cache `
        /XF .env *.sqlite3 *.sqlite3-wal *.sqlite3-shm
    if ($LASTEXITCODE -ge 8) {
        throw "Copying application files failed (robocopy exit $LASTEXITCODE)."
    }
}

function Write-FactoryOpsPublicFile {
    param($Layout, [string]$Bind, [int]$Port)
    $content = "FACTORYOPS_BIND=$Bind`r`nFACTORYOPS_PORT=$Port`r`n"
    Set-Content -Path $Layout.PublicFile -Value $content -Encoding ASCII
}

function Register-FactoryOpsTask {
    param([string]$Name, [string]$XmlPath)
    & schtasks.exe /Create /TN $Name /XML $XmlPath /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not register scheduled task '$Name'. Run the installer from an elevated PowerShell."
    }
}

function Stop-FactoryOpsServerTask {
    param($Layout)
    & schtasks.exe /End /TN 'FactoryOps Server' | Out-Null
    if (Test-Path $Layout.PidFile) {
        $procId = (Get-Content $Layout.PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($procId) {
            & taskkill.exe /PID $procId /T /F | Out-Null
        }
    }
}
