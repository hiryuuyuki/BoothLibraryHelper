<#  tools/clean.ps1
BoothLibraryHelper maintenance tool (SAFE by default)

Default policy (accident-proof):
  - NO deletion by default (move to stash only)
  - Only touch "safe-to-remove" artifacts:
      __pycache__ folders, *.bak* files
  - Optional: include *.log / *.tmp only when explicitly requested
  - Purge old _stash/_audit folders ONLY when -Purge is specified

Usage:
  # preview (no changes)
  .\tools\clean.ps1 -WhatIf

  # audit + stash (safe default)
  .\tools\clean.ps1

  # audit only / clean only
  .\tools\clean.ps1 -AuditOnly
  .\tools\clean.ps1 -CleanOnly

  # purge old folders (deletion happens ONLY here)
  .\tools\clean.ps1 -Purge -KeepDays 3
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
  [switch]$AuditOnly,
  [switch]$CleanOnly,

  # Purge old _stash_* and _audit_* folders (OFF by default)
  [switch]$Purge,
  [ValidateRange(1, 3650)]
  [int]$KeepDays = 3,

  # Optional: include these into stash when specified
  [switch]$IncludeLogs,
  [switch]$IncludeTmp
)

$ErrorActionPreference = "Stop"

function New-Timestamp { (Get-Date -Format "yyyyMMdd_HHmmss") }

function Resolve-RepoRoot {
  # expect this script at <repo>\tools\clean.ps1
  (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Ensure-Exists([string]$path, [string]$label) {
  if (-not (Test-Path $path)) { throw "$label not found: $path" }
}

function Write-Section([string]$title) {
  Write-Host ""
  Write-Host "==== $title ====" -ForegroundColor Cyan
}

function Export-Audit([string]$root) {
  $ts = New-Timestamp
  $audit = Join-Path $root "_audit_$ts"
  if ($PSCmdlet.ShouldProcess($audit, "Create audit folder")) {
    New-Item -ItemType Directory -Force $audit | Out-Null
  }

  Write-Host "AUDIT: $audit"

  # 1) files.csv
  $filesCsv = Join-Path $audit "files.csv"
  Write-Host "-> files.csv"
  if ($PSCmdlet.ShouldProcess($filesCsv, "Export file list")) {
    Get-ChildItem $root -File -Recurse |
      Sort-Object FullName |
      Select-Object FullName, Length, LastWriteTime |
      Export-Csv $filesCsv -NoTypeInformation -Encoding UTF8
  }

  # 2) hashes.csv (limited extensions)
  $hashesCsv = Join-Path $audit "hashes.csv"
  Write-Host "-> hashes.csv (code/config only)"
  if ($PSCmdlet.ShouldProcess($hashesCsv, "Export hashes")) {
    Get-ChildItem $root -File -Recurse -Include *.py,*.json,*.txt,*.md,*.toml,*.ini,*.ps1 |
      Get-FileHash -Algorithm SHA256 |
      Sort-Object Path |
      Export-Csv $hashesCsv -NoTypeInformation -Encoding UTF8
  }

  # 3) src zip (include only existing items; do not fail if missing)
  $zipPath = Join-Path $audit "src_$ts.zip"
  $targets = @(
    (Join-Path $root "app"),
    (Join-Path $root "viewer.py"),
    (Join-Path $root "requirements.txt"),
    (Join-Path $root "README.md")
  ) | Where-Object { Test-Path $_ }

  Write-Host "-> src zip: $zipPath"
  if ($PSCmdlet.ShouldProcess($zipPath, "Compress sources")) {
    Compress-Archive -Path $targets -DestinationPath $zipPath -Force
  }

  return $audit
}

function Move-ToStash([string]$root) {
  $ts = New-Timestamp
  $stash = Join-Path $root "_stash_$ts"
  if ($PSCmdlet.ShouldProcess($stash, "Create stash folder")) {
    New-Item -ItemType Directory -Force $stash | Out-Null
  }
  Write-Host "STASH: $stash"

  $moved = 0

  function Move-PreservePath([string]$fullPath) {
    $rel = $fullPath.Substring($root.Length).TrimStart("\")
    $dst = Join-Path $stash $rel
    $dstParent = Split-Path $dst
    New-Item -ItemType Directory -Force $dstParent | Out-Null
    Move-Item $fullPath $dst -Force
  }

  # Move __pycache__ directories (safe)
  $pycaches = Get-ChildItem $root -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue
  foreach ($d in $pycaches) {
    if ($PSCmdlet.ShouldProcess($d.FullName, "Move __pycache__")) {
      Move-PreservePath $d.FullName
      $moved++
    }
  }

  # Move *.bak* files (safe)
  $baks = Get-ChildItem $root -File -Recurse -Filter "*.bak*" -ErrorAction SilentlyContinue
  foreach ($f in $baks) {
    if ($PSCmdlet.ShouldProcess($f.FullName, "Move *.bak*")) {
      Move-PreservePath $f.FullName
      $moved++
    }
  }

  # Optional: logs
  if ($IncludeLogs) {
    $logs = Get-ChildItem $root -File -Recurse -Include *.log -ErrorAction SilentlyContinue
    foreach ($f in $logs) {
      if ($PSCmdlet.ShouldProcess($f.FullName, "Move *.log")) {
        Move-PreservePath $f.FullName
        $moved++
      }
    }
  }

  # Optional: tmp
  if ($IncludeTmp) {
    $tmps = Get-ChildItem $root -File -Recurse -Include *.tmp -ErrorAction SilentlyContinue
    foreach ($f in $tmps) {
      if ($PSCmdlet.ShouldProcess($f.FullName, "Move *.tmp")) {
        Move-PreservePath $f.FullName
        $moved++
      }
    }
  }

  Write-Host ("Moved items: {0}" -f $moved)
  return @{ stash = $stash; moved = $moved }
}

function Purge-OldFolders([string]$root, [int]$keepDays) {
  $limit = (Get-Date).AddDays(-$keepDays)
  $targets = @()
  $targets += Get-ChildItem $root -Directory -Filter "_stash_*" -ErrorAction SilentlyContinue
  $targets += Get-ChildItem $root -Directory -Filter "_audit_*" -ErrorAction SilentlyContinue

  $old = $targets | Where-Object { $_.LastWriteTime -lt $limit } | Sort-Object LastWriteTime
  if (-not $old) {
    Write-Host "No old folders to purge (KeepDays=$keepDays)."
    return 0
  }

  Write-Host ("Purge candidates: {0} folder(s) (older than {1})" -f $old.Count, $limit.ToString("yyyy-MM-dd HH:mm:ss"))
  $removed = 0
  foreach ($d in $old) {
    if ($PSCmdlet.ShouldProcess($d.FullName, "Remove old folder")) {
      Remove-Item $d.FullName -Recurse -Force
      $removed++
    }
  }
  return $removed
}

# -----------------------
# Main
# -----------------------
$root = Resolve-RepoRoot
Ensure-Exists (Join-Path $root "app") "app folder"

Write-Section "BoothLibraryHelper clean tool"
Write-Host "Root: $root"
Write-Host ("Mode: {0}" -f ($(if ($AuditOnly) { "AuditOnly" } elseif ($CleanOnly) { "CleanOnly" } else { "Audit+Clean" })))
Write-Host ("KeepDays: {0} / Purge: {1}" -f $KeepDays, $Purge)
Write-Host ("IncludeLogs: {0} / IncludeTmp: {1}" -f $IncludeLogs, $IncludeTmp)
Write-Host "Policy: SAFE(default) = move only; no deletion unless -Purge"

$auditPath = $null
$stashInfo = $null
$purgedCount = 0

if (-not $CleanOnly) {
  Write-Section "1) Audit"
  $auditPath = Export-Audit $root
}

if (-not $AuditOnly) {
  Write-Section "2) Clean (move to stash)"
  $stashInfo = Move-ToStash $root
}

if ($Purge) {
  Write-Section "3) Purge old _stash/_audit"
  $purgedCount = Purge-OldFolders $root $KeepDays
}

Write-Section "Summary"
if ($auditPath) { Write-Host "Audit saved: $auditPath" }
if ($stashInfo) { Write-Host ("Stash saved: {0} (moved {1})" -f $stashInfo.stash, $stashInfo.moved) }
if ($Purge)     { Write-Host ("Purged folders: {0}" -f $purgedCount) }

Write-Host ""
Write-Host "Tip: First run with -WhatIf once, then run normally." -ForegroundColor DarkGray
