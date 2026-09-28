<#
.SYNOPSIS
    Takes a backup of the daycare CRM's production database.

.DESCRIPTION
    Runs `flask backup`, verifies the file it produced is a readable backup
    rather than a truncated or empty one, deletes backups older than the
    retention count, and appends the outcome to a log.

    Exits non-zero on failure so Task Scheduler records the run as failed
    instead of silently reporting success.

    The database URL is read from a config file OUTSIDE the project folder,
    so the credential is never at risk of being committed. It is applied to
    this process only, so it cannot affect a local development shell that is
    pointed at SQLite.

.PARAMETER ProjectDir
    The DayCare_CRM checkout. Defaults to the parent of this script.

.PARAMETER OutputDir
    Where backups are written. Keep this outside the project folder.

.PARAMETER ConfigFile
    A file containing the line: DATABASE_URL=postgresql://...

.PARAMETER KeepCount
    How many backups to retain. Older ones are deleted.

.EXAMPLE
    .\backup.ps1
    .\backup.ps1 -KeepCount 26 -OutputDir "D:\crm-backups"
#>
[CmdletBinding()]
param(
    [string]$ProjectDir = (Split-Path -Parent $PSScriptRoot),
    [string]$OutputDir  = (Join-Path $HOME "Documents\crm-backups"),
    [string]$ConfigFile = (Join-Path $HOME ".daycare-crm\backup.env"),
    [int]$KeepCount     = 12
)

$ErrorActionPreference = 'Stop'

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $line = "{0}  {1,-5}  {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Write-Host $line
    try {
        $logDir = Split-Path -Parent $script:LogPath
        if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
        Add-Content -Path $script:LogPath -Value $line -Encoding utf8
    } catch {
        # Never let a logging failure mask the backup's own result.
        Write-Host "(could not write to log: $_)"
    }
}

$script:LogPath = Join-Path $OutputDir "backup-log.txt"

try {
    Write-Log "Backup starting. Project: $ProjectDir"

    if (-not (Test-Path $ProjectDir)) {
        throw "Project folder not found: $ProjectDir"
    }

    # Read the connection string. Kept outside the repo so it cannot be
    # committed, and applied per-process so interactive shells are unaffected.
    if (-not (Test-Path $ConfigFile)) {
        throw @"
Config file not found: $ConfigFile
Create it with one line:
    DATABASE_URL=postgresql://user:password@host/db?sslmode=require
Keep it outside the project folder.
"@
    }

    $databaseUrl = $null
    foreach ($line in Get-Content $ConfigFile) {
        $trimmed = $line.Trim()
        if ($trimmed -eq '' -or $trimmed.StartsWith('#')) { continue }
        if ($trimmed -match '^\s*DATABASE_URL\s*=\s*(.+?)\s*$') {
            $databaseUrl = $Matches[1].Trim('"').Trim("'")
        }
    }
    if ([string]::IsNullOrWhiteSpace($databaseUrl)) {
        throw "No DATABASE_URL= line found in $ConfigFile"
    }
    if ($databaseUrl -notmatch '^postgres(ql)?(\+\w+)?://') {
        throw "DATABASE_URL in $ConfigFile does not look like a PostgreSQL URL."
    }
    Write-Log "Config loaded. Target host: $(([uri]$databaseUrl).Host)"

    # Locate the virtual environment's flask. Windows uses Scripts\, other
    # platforms bin/ -- checking both keeps this script testable off Windows.
    $flask = Join-Path $ProjectDir ".venv\Scripts\flask.exe"
    if (-not (Test-Path $flask)) { $flask = Join-Path $ProjectDir ".venv/bin/flask" }
    if (-not (Test-Path $flask)) {
        throw "flask not found in the virtual environment under $ProjectDir\.venv. Run: .\.venv\Scripts\pip install -r requirements.txt"
    }

    if (-not (Test-Path $OutputDir)) {
        New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
        Write-Log "Created output folder: $OutputDir"
    }

    $before = @(Get-ChildItem -Path $OutputDir -Filter "daycare-crm-backup-*.json" -ErrorAction SilentlyContinue)

    # Scope the credential and FLASK_APP to this process only.
    $env:DATABASE_URL = $databaseUrl
    $env:FLASK_APP    = "wsgi.py"

    Write-Log "Running flask backup..."
    Push-Location $ProjectDir
    try {
        $output = & $flask backup --output-dir $OutputDir 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
        # Clear the credential from the process as soon as it is no longer needed.
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }

    if ($exitCode -ne 0) {
        $output | ForEach-Object { Write-Log $_ 'ERROR' }
        throw "flask backup exited with code $exitCode"
    }

    # Identify the file this run produced.
    $after = @(Get-ChildItem -Path $OutputDir -Filter "daycare-crm-backup-*.json")
    $newFiles = $after | Where-Object { $_.Name -notin $before.Name }
    if ($newFiles.Count -eq 0) {
        throw "flask backup reported success but wrote no new file."
    }
    $backupFile = $newFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1

    # Verify it is a readable backup. A file that exists but cannot be parsed
    # is worse than no backup, because it looks like protection.
    try {
        $data = Get-Content $backupFile.FullName -Raw | ConvertFrom-Json
    } catch {
        throw "Backup file is not valid JSON: $($backupFile.Name)"
    }
    if (-not $data.tables) {
        throw "Backup file has no 'tables' section: $($backupFile.Name)"
    }
    $counts = [ordered]@{}
    foreach ($table in 'users','families','guardians','children','stage_events','interactions') {
        $counts[$table] = @($data.tables.$table).Count
    }
    $sizeKb = [math]::Round($backupFile.Length / 1KB, 1)
    Write-Log "Verified $($backupFile.Name) ($sizeKb KB): $(($counts.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ', ')"

    if ($counts['users'] -eq 0) {
        Write-Log "No staff accounts in the backup -- restoring this would lock everyone out." 'WARN'
    }
    if ($counts['families'] -eq 0) {
        Write-Log "No families in the backup. Correct if none are entered yet; otherwise investigate." 'WARN'
    }

    # Retention: keep the newest N, delete the rest.
    $all = Get-ChildItem -Path $OutputDir -Filter "daycare-crm-backup-*.json" | Sort-Object LastWriteTime -Descending
    if ($all.Count -gt $KeepCount) {
        foreach ($old in $all | Select-Object -Skip $KeepCount) {
            Remove-Item $old.FullName -Force
            Write-Log "Removed old backup: $($old.Name)"
        }
    }
    Write-Log "Backup complete. $([math]::Min($all.Count, $KeepCount)) backup(s) retained in $OutputDir"
    exit 0
}
catch {
    Write-Log "BACKUP FAILED: $($_.Exception.Message)" 'ERROR'
    exit 1
}
