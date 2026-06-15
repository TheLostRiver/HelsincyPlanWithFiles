<#
.SYNOPSIS
  Build release zip packages for Helsincy Plan With Files.

.DESCRIPTION
  Produces two variants in dist/:
    HelsincyPlanWithFiles-v<version>-codex.zip
        Install package: .codex/, docs/, README*, CHANGELOG, LICENSE, VERSION.
        What an end user copies into their project.
    HelsincyPlanWithFiles-v<version>-full.zip
        Source package: everything in -codex plus tests/ and .gitignore.
        What a developer/contributor clones-equivalent wants.

  Version is read from VERSION. Override with -Version <x.y.z>.
  Re-running is safe: existing zips in dist/ for this version are overwritten.

.PARAMETER Variant
  codex | full | both (default: both).

.PARAMETER Version
  Override the version string (default: read from ./VERSION).

.EXAMPLE
  ./build-release.ps1
  ./build-release.ps1 -Variant codex
  ./build-release.ps1 -Version 0.3.0
#>
[CmdletBinding()]
param(
    [ValidateSet("codex", "full", "both")]
    [string]$Variant = "both",

    [string]$Version
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0

$RepoRoot = $PSScriptRoot | Resolve-Path
$DistDir = Join-Path $RepoRoot "dist"

if (-not $Version) {
    $versionFile = Join-Path $RepoRoot "VERSION"
    if (-not (Test-Path $versionFile)) {
        throw "VERSION file not found at $versionFile"
    }
    $Version = (Get-Content $versionFile -Raw).Trim()
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Invalid version '$Version' (expected x.y.z)"
}

# --- File manifest rules -----------------------------------------------------
# Paths are relative to repo root. Directories are included recursively.
# Exclusions always win over inclusions and apply to both variants.

$IncludeCommon = @(
    "VERSION",
    "README.md",
    "README.en.md",
    "CHANGELOG.md",
    "LICENSE"
)

# Directories included in BOTH variants.
$IncludeDirsBoth = @(
    ".codex",
    "docs"
)

# Extra top-level files / dirs only in -full.
$IncludeFullExtra = @(
    ".gitignore",
    "tests"
)

# Glob/substring exclusions applied to every collected path (both variants).
# Keeps dev/runtime artifacts out of release zips.
$ExcludePatterns = @(
    "__pycache__",
    "*.pyc",
    ".DS_Store",
    "Thumbs.db",
    "*.tmp",
    "*.swp"
)

# Directories under docs/ that the -codex variant historically omits
# (internal planning/archive notes not relevant to installers).
# NOTE: keep this in sync with what prior -codex zips shipped.
$CodexDocsExcludes = @(
    "archive",
    "superpowers"
)

function Test-Excluded {
    param([string]$RelativePath, [string[]]$Patterns)
    foreach ($pat in $Patterns) {
        if ($pat -like "*.*") {
            # treat as wildcard against the leaf name
            $leaf = Split-Path $RelativePath -Leaf
            if ($leaf -like $pat) { return $true }
        } else {
            # treat as a path segment substring (matches dir names anywhere)
            if ($RelativePath -match "(^|[\\/])$([regex]::Escape($pat))([\\/]|$)") { return $true }
        }
    }
    return $false
}

function Get-RelativeFiles {
    param([string]$AbsBase, [string]$RelBase)
    $items = Get-ChildItem -LiteralPath $AbsBase -Recurse -File -Force
    $result = New-Object System.Collections.Generic.List[string]
    foreach ($item in $items) {
        $rel = $item.FullName.Substring($AbsBase.Length).TrimStart("\", "/") -replace "\\", "/"
        if ($rel) { $result.Add("$RelBase/$rel") }
    }
    return $result
}

function Build-FileList {
    param([string]$ThisVariant)
    $files = New-Object System.Collections.Generic.List[string]

    foreach ($f in $IncludeCommon) {
        $abs = Join-Path $RepoRoot $f
        if (Test-Path $abs) { $files.Add($f) }
    }

    foreach ($dir in $IncludeDirsBoth) {
        $absDir = Join-Path $RepoRoot $dir
        if (-not (Test-Path $absDir)) { continue }
        foreach ($f in (Get-RelativeFiles $absDir $dir)) {
            # codex omits internal docs subdirs
            if ($ThisVariant -eq "codex" -and $dir -eq "docs") {
                $skip = $false
                foreach ($ex in $CodexDocsExcludes) {
                    if ($f -match "^docs/$([regex]::Escape($ex))/") { $skip = $true; break }
                }
                if ($skip) { continue }
            }
            $files.Add($f)
        }
    }

    if ($ThisVariant -eq "full") {
        foreach ($extra in $IncludeFullExtra) {
            $absExtra = Join-Path $RepoRoot $extra
            if (-not (Test-Path $absExtra)) { continue }
            if (Test-Path $absExtra -PathType Leaf) {
                $files.Add($extra)
            } else {
                foreach ($f in (Get-RelativeFiles $absExtra $extra)) {
                    $files.Add($f)
                }
            }
        }
    }

    # Apply global exclusions
    $filtered = New-Object System.Collections.Generic.List[string]
    foreach ($f in $files) {
        if (-not (Test-Excluded $f $ExcludePatterns)) { $filtered.Add($f) }
    }
    return $filtered
}

function New-ReleaseZip {
    param([string]$ThisVariant)
    $staging = Build-FileList -ThisVariant $ThisVariant
    $zipName = "HelsincyPlanWithFiles-v$Version-$ThisVariant.zip"
    $zipPath = Join-Path $DistDir $zipName
    $topDirInZip = "HelsincyPlanWithFiles-v$Version-$ThisVariant"

    if (-not (Test-Path $DistDir)) {
        New-Item -ItemType Directory -Path $DistDir | Out-Null
    }
    if (Test-Path $zipPath) {
        Remove-Item $zipPath -Force
    }

    # Stage into a temp dir so the zip has a single top-level folder.
    $tempStage = Join-Path $env:TEMP "hpf-build-$Version-$ThisVariant-$(Get-Random)"
    if (Test-Path $tempStage) { Remove-Item $tempStage -Recurse -Force }
    $stageRoot = Join-Path $tempStage $topDirInZip
    New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null

    $copied = 0
    foreach ($rel in $staging) {
        $src = Join-Path $RepoRoot $rel
        $dst = Join-Path $stageRoot $rel
        $dstDir = Split-Path $dst -Parent
        if (-not (Test-Path $dstDir)) {
            New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
        }
        Copy-Item -LiteralPath $src -Destination $dst -Force
        $copied++
    }

    Compress-Archive -Path (Join-Path $tempStage "*") -DestinationPath $zipPath -CompressionLevel Optimal -Force
    Remove-Item $tempStage -Recurse -Force

    $sizeKb = [math]::Round((Get-Item $zipPath).Length / 1KB, 1)
    Write-Host ("Built {0}  ({1} files, {2} KB)" -f $zipName, $copied, $sizeKb)
    return $zipPath
}

# --- main --------------------------------------------------------------------
Write-Host "Building release v$Version (variant: $Variant)`n"

$built = @()
if ($Variant -in @("codex", "both")) { $built += (New-ReleaseZip "codex") }
if ($Variant -in @("full", "both"))  { $built += (New-ReleaseZip "full")  }

Write-Host "`nDone. Output in $DistDir :"
foreach ($z in $built) { Write-Host ("  - {0}" -f (Split-Path $z -Leaf)) }
