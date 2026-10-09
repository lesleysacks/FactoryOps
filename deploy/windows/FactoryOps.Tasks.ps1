# Task Scheduler XML for FactoryOps. Dot-source from the installer.

function New-FactoryOpsServerTaskXml {
    param([string]$ScriptPath, [string]$InstallRoot)
    $argument = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$ScriptPath`" -InstallRoot `"$InstallRoot`""
    return @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>FactoryOps production server. Starts at boot and does not open a terminal window.</Description>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger><Enabled>true</Enabled></BootTrigger>
  </Triggers>
  <Principals>
    <Principal>
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions>
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>$argument</Arguments>
      <WorkingDirectory>$InstallRoot\app</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@
}

function New-FactoryOpsBackupTaskXml {
    param([string]$ScriptPath, [string]$InstallRoot)
    $argument = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$ScriptPath`" -InstallRoot `"$InstallRoot`""
    return @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Daily FactoryOps database and media backup.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T02:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal>
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <RestartOnFailure>
      <Interval>PT15M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions>
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>$argument</Arguments>
      <WorkingDirectory>$InstallRoot\app</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@
}

function New-FactoryOpsBrowserTaskXml {
    param([string]$ScriptPath, [string]$InstallRoot, [string]$DesktopUser)
    $argument = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -InstallRoot `"$InstallRoot`""
    return @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Open the FactoryOps login window after the desktop user signs in.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>$DesktopUser</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal>
      <UserId>$DesktopUser</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
  </Settings>
  <Actions>
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>$argument</Arguments>
    </Exec>
  </Actions>
</Task>
"@
}

function New-FactoryOpsShortcut {
    param($Layout, [string]$OpenScript)
    $shell = New-Object -ComObject WScript.Shell
    $desktop = $shell.SpecialFolders('AllUsersDesktop')
    if (-not $desktop) {
        $desktop = $Layout.Root
    }
    $shortcut = Join-Path $desktop 'FactoryOps.lnk'
    try {
        $link = $shell.CreateShortcut($shortcut)
        $link.TargetPath = 'powershell.exe'
        $link.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$OpenScript`" -InstallRoot `"$($Layout.Root)`""
        $link.WorkingDirectory = $Layout.App
        $link.WindowStyle = 7
        $link.Description = 'Open the FactoryOps login window'
        $link.Save()
        Write-Host "Desktop shortcut: $shortcut"
    } catch {
        $fallback = Join-Path $Layout.Root 'FactoryOps.lnk'
        $link = $shell.CreateShortcut($fallback)
        $link.TargetPath = 'powershell.exe'
        $link.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$OpenScript`" -InstallRoot `"$($Layout.Root)`""
        $link.WorkingDirectory = $Layout.App
        $link.Description = 'Open the FactoryOps login window'
        $link.Save()
        Write-Host "Could not write the common desktop shortcut. Created $fallback instead."
    }
}
