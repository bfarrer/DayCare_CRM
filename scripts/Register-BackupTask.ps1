<#
.SYNOPSIS
    Registers (or updates) the weekly CRM backup as a Windows scheduled task.

.DESCRIPTION
    Creates a task that runs backup.ps1 on a weekly schedule. The task runs as
    the current user, so it inherits that account's access to the config file
    holding the database URL -- no password is stored in Task Scheduler.

    If the machine is off at the scheduled time, the task runs at the next
    opportunity rather than silently skipping the week.

    Run this from an ordinary PowerShell window. Administrator rights are not
    required for a task that runs as the current user.

.PARAMETER DayOfWeek
    Which day to run. Default Sunday.

.PARAMETER Time
    24-hour time to run. Default 19:00.

.PARAMETER TaskName
    Name shown in Task Scheduler.

.EXAMPLE
    .\Register-BackupTask.ps1
    .\Register-BackupTask.ps1 -DayOfWeek Friday -Time "17:30"
#>
[CmdletBinding()]
param(
    [ValidateSet('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')]
    [string]$DayOfWeek = 'Sunday',
    [string]$Time = '19:00',
    [string]$TaskName = 'DaycareCRM-WeeklyBackup',
    [string]$OutputDir = (Join-Path $HOME "Documents\crm-backups"),
    [string]$ConfigFile = (Join-Path $HOME ".daycare-crm\backup.env"),
    [int]$KeepCount = 12
)

$ErrorActionPreference = 'Stop'

$backupScript = Join-Path $PSScriptRoot 'backup.ps1'
if (-not (Test-Path $backupScript)) {
    throw "backup.ps1 not found next to this script (looked in $PSScriptRoot)."
}

if (-not (Test-Path $ConfigFile)) {
    Write-Warning @"
Config file not found: $ConfigFile

The task will be registered, but every run will fail until you create it.
Create the folder and file with one line:

    DATABASE_URL=postgresql://user:password@host/db?sslmode=require

"@
}

# -File rather than -Command: the path may contain spaces, and -File does not
# re-parse the arguments as script text.
$arguments = @(
    '-NoProfile'
    '-NonInteractive'
    '-ExecutionPolicy','Bypass'
    '-File',"`"$backupScript`""
    '-OutputDir',"`"$OutputDir`""
    '-ConfigFile',"`"$ConfigFile`""
    '-KeepCount',$KeepCount
) -join ' '

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments `
    -WorkingDirectory (Split-Path -Parent $PSScriptRoot)

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $Time

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

# Run as the current user, only when logged on. This avoids storing a Windows
# password in Task Scheduler; the trade-off is the task waits for a logon,
# which -StartWhenAvailable then honours.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Replaced the existing '$TaskName' task."
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Weekly backup of the daycare CRM database. Writes to $OutputDir and keeps the newest $KeepCount." | Out-Null

Write-Host ""
Write-Host "Registered '$TaskName'."
Write-Host "  Runs      : every $DayOfWeek at $Time"
Write-Host "  Backups   : $OutputDir (newest $KeepCount kept)"
Write-Host "  Log       : $(Join-Path $OutputDir 'backup-log.txt')"
Write-Host ""
Write-Host "Run it once now to confirm it works:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "Then check the log:"
Write-Host "  Get-Content '$(Join-Path $OutputDir 'backup-log.txt')' -Tail 20"
