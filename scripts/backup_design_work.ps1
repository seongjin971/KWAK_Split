param(
    [string]$Label = "design",
    [switch]$IncludeRelease
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$safeLabel = ($Label -replace "[^A-Za-z0-9._-]", "_").Trim("_")
if ([string]::IsNullOrWhiteSpace($safeLabel)) {
    $safeLabel = "design"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRoot = Join-Path $projectRoot "backups\design"
$backupDir = Join-Path $backupRoot "$timestamp`_$safeLabel"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

$launcherName = "KWAK Split " + [char]0xC2E4 + [char]0xD589 + ".cmd"
$files = @(
    "StemSamplePrep.py",
    "README.txt",
    "THIRD_PARTY_NOTICES.txt",
    $launcherName,
    "backend\__init__.py",
    "backend\app_paths.py",
    "backend\audio_processing\__init__.py",
    "backend\audio_processing\ffmpeg_tools.py",
    "backend\audio_processing\separation.py",
    "build.ps1",
    "settings.json"
)

foreach ($file in $files) {
    $source = Join-Path $projectRoot $file
    if (Test-Path -LiteralPath $source) {
        $target = Join-Path $backupDir $file
        $targetParent = Split-Path $target -Parent
        New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -Force
    }
}

if ($IncludeRelease) {
    foreach ($releaseName in @("KWAK Split", "StemSamplePrep")) {
        $releaseSource = Join-Path $projectRoot "release\$releaseName"
        if (-not (Test-Path -LiteralPath $releaseSource)) {
            continue
        }
        $releaseTarget = Join-Path $backupDir "release\$releaseName"
        New-Item -ItemType Directory -Path $releaseTarget -Force | Out-Null
        & robocopy $releaseSource $releaseTarget /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -gt 7) {
            throw "robocopy failed while backing up release. Exit code: $LASTEXITCODE"
        }
    }
}

$manifest = @(
    "KWAK Split design backup",
    "Created: $(Get-Date -Format o)",
    "Label: $safeLabel",
    "Project: $projectRoot",
    "Includes release: $IncludeRelease",
    "",
    "Files:",
    ($files | ForEach-Object { "  - $_" })
)
$manifest | Set-Content -Path (Join-Path $backupDir "BACKUP.txt") -Encoding UTF8

Write-Host "Design backup created:"
Write-Host "  $backupDir"
