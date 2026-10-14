param(
    [switch]$ValidateOnly,
    [string]$DestinationRelativePath = "bin",
    [string]$ArchivePath = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$RootPrefix = $Root.TrimEnd('\') + '\'
$ManifestPath = Join-Path $Root "LICENSES\ffmpeg\manifest.json"
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json

function Get-WorkspacePath([string]$RelativePath) {
    if ([IO.Path]::IsPathRooted($RelativePath)) { throw "Use a path relative to the project root." }
    $Path = [IO.Path]::GetFullPath((Join-Path $Root $RelativePath))
    if (-not $Path.StartsWith($RootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside the project workspace: $RelativePath"
    }
    $Current = $Path
    while ($Current -and $Current -ne $Root) {
        if ((Test-Path -LiteralPath $Current) -and
            ((Get-Item -LiteralPath $Current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Refusing to install through a reparse point: $RelativePath"
        }
        $Current = Split-Path -Parent $Current
    }
    return $Path
}

function Assert-Hash([string]$Path, [string]$Expected) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required file is missing: $Path" }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Expected) {
        throw "SHA-256 mismatch: $Path. Validation stopped."
    }
}

function Assert-Tools([string]$Directory) {
    # Check every hash before executing any downloaded binary.
    foreach ($Tool in $Manifest.binaries) {
        Assert-Hash (Join-Path $Directory $Tool.name) $Tool.sha256
    }
    foreach ($Tool in $Manifest.binaries) {
        $Output = (& (Join-Path $Directory $Tool.name) -version 2>&1 | Out-String)
        if ($LASTEXITCODE -ne 0 -or -not $Output.Contains($Manifest.version)) {
            throw "Unexpected FFmpeg tool version: $($Tool.name)"
        }
        if ($Output.Contains("--enable-nonfree")) { throw "Nonredistributable FFmpeg configuration detected." }
        if ($Output.Contains("--enable-libdvd")) { throw "DVD support (libdvdcss) must not be built into the bundled FFmpeg." }
    }
    $Ffmpeg = Join-Path $Directory "ffmpeg.exe"
    $Filters = (& $Ffmpeg -hide_banner -filters 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect FFmpeg filters." }
    foreach ($Filter in @("azmq", "rubberband")) {
        if ($Filters -notmatch ("(?m)\s" + $Filter + "\s")) { throw "Required FFmpeg filter is absent: $Filter" }
    }
    $Encoders = (& $Ffmpeg -hide_banner -encoders 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or $Encoders -notmatch '(?m)\slibmp3lame\s') {
        throw "The required MP3 encoder is absent."
    }
}

$Destination = Get-WorkspacePath $DestinationRelativePath
if ($ValidateOnly) {
    Assert-Tools $Destination
    Write-Host "Pinned FFmpeg tools and required audio features verified: $Destination"
    exit 0
}

New-Item -ItemType Directory -Force -Path (Get-WorkspacePath "temp\downloads\ffmpeg") | Out-Null
if ($ArchivePath) {
    $ZipPath = [IO.Path]::GetFullPath($ArchivePath)
} else {
    # The no-DVD build is produced by .github/workflows/ffmpeg-nodvd.yml; its
    # package is preserved locally because workflow artifacts expire.
    $ZipPath = Get-WorkspacePath $Manifest.archive.local_path
    if (-not (Test-Path -LiteralPath $ZipPath -PathType Leaf)) {
        throw "The pinned FFmpeg package is missing: $($Manifest.archive.local_path). Download artifact '$($Manifest.archive.workflow_artifact)' from $($Manifest.archive.workflow_run) or rebuild it with .github/workflows/ffmpeg-nodvd.yml, then pass -ArchivePath."
    }
}
Assert-Hash $ZipPath $Manifest.archive.sha256

# Each run extracts into a new confined staging folder; no recursive removal.
$StageRelativePath = "temp\downloads\ffmpeg\stage-" + [guid]::NewGuid().ToString("N")
$Stage = Get-WorkspacePath $StageRelativePath
New-Item -ItemType Directory -Path $Stage | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Zip = [IO.Compression.ZipFile]::OpenRead($ZipPath)
try {
    foreach ($Entry in $Zip.Entries) {
        $Target = [IO.Path]::GetFullPath((Join-Path $Stage $Entry.FullName))
        if (-not $Target.StartsWith($Stage + '\', [StringComparison]::OrdinalIgnoreCase) -or
            $Entry.FullName.Contains(':')) { throw "Unsafe ZIP member: $($Entry.FullName)" }
    }
} finally { $Zip.Dispose() }
[IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $Stage)
$Package = Join-Path $Stage $Manifest.archive.root_directory
$StagedBin = Join-Path $Package "bin"
Assert-Tools $StagedBin
if (-not (Test-Path -LiteralPath (Join-Path $Package "LICENSE.txt"))) {
    throw "The upstream FFmpeg license is missing from the package."
}

# Preserve previous binaries before the first overwrite. Existing files are
# never deleted, and receipts contain hashes rather than machine credentials.
$Existing = @($Manifest.binaries | Where-Object { Test-Path -LiteralPath (Join-Path $Destination $_.name) })
if ($Existing.Count) {
    $Backup = Get-WorkspacePath ("backups\ffmpeg-before-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $Backup | Out-Null
    $Records = foreach ($Tool in $Existing) {
        $Original = Join-Path $Destination $Tool.name
        $Saved = Join-Path $Backup $Tool.name
        $Hash = (Get-FileHash -LiteralPath $Original -Algorithm SHA256).Hash
        Copy-Item -LiteralPath $Original -Destination $Saved
        Assert-Hash $Saved $Hash
        [pscustomobject]@{ name = $Tool.name; sha256 = $Hash }
    }
    $Records | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Backup "hashes.json") -Encoding UTF8
}

$Notices = Get-WorkspacePath "LICENSES\ffmpeg\upstream"
New-Item -ItemType Directory -Force -Path $Notices, $Destination | Out-Null
Get-ChildItem -LiteralPath $Package -File | Where-Object {
    $_.Name -match '^(LICENSE|COPYING|NOTICE|README)'
} | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $Notices -Force }
foreach ($Tool in $Manifest.binaries) {
    Copy-Item -LiteralPath (Join-Path $StagedBin $Tool.name) -Destination (Join-Path $Destination $Tool.name) -Force
}
Assert-Tools $Destination
Write-Host "Pinned FFmpeg installed and checked. Previous binaries are preserved in backups/."
Write-Host "Public distribution additionally requires the verified source sidecar and the project distribution checks."
