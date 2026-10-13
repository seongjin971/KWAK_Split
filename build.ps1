param(
    [string]$PythonExe = "",
    [ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$ReleaseName = "compact",
    [switch]$SkipDependencyInstall,
    [string]$PreparedRuntime = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $PythonExe) { $PythonExe = (Get-Command python.exe -ErrorAction Stop).Source }
$BuildRoot = Join-Path $Root ".build"
$Venv = Join-Path $BuildRoot "venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$ReleaseRoot = Join-Path $Root "release\$ReleaseName"
$AppName = "KWAK Split"
$AppExe = "$AppName.exe"
$AppOut = Join-Path $ReleaseRoot $AppName
if (Test-Path -LiteralPath $AppOut) {
    throw "Preserving existing release: $AppOut. Choose a new -ReleaseName."
}

$env:TEMP = Join-Path $Root "temp"
$env:TMP = Join-Path $Root "temp"
$env:PIP_CACHE_DIR = Join-Path $Root "temp\pip-cache"
$env:PYTHONPYCACHEPREFIX = Join-Path $BuildRoot "pycache"
$env:PYINSTALLER_CONFIG_DIR = Join-Path $BuildRoot "pyinstaller-cache"

New-Item -ItemType Directory -Force -Path `
    $BuildRoot, `
    $ReleaseRoot, `
    $env:TEMP, `
    $env:PIP_CACHE_DIR, `
    $env:PYINSTALLER_CONFIG_DIR | Out-Null

if (-not (Test-Path $VenvPython)) {
    & $PythonExe -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Build environment creation failed." }
}

if (-not $SkipDependencyInstall) {
    & $VenvPython -m pip install -r (Join-Path $Root "requirements-build.txt")
    if ($LASTEXITCODE -ne 0) { throw "Build dependencies could not be installed." }
}

Set-Location $Root
& $VenvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name $AppName `
    --distpath $ReleaseRoot `
    --workpath (Join-Path $BuildRoot "pyinstaller-work") `
    --specpath (Join-Path $BuildRoot "pyinstaller-spec") `
    ".\StemSamplePrep.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

foreach ($folder in @("bin", "models")) {
    $source = Join-Path $Root $folder
    $dest = Join-Path $AppOut $folder
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    if (Test-Path $source) {
        # Skip the numba JIT cache: leftover from the removed Beat/BPM (librosa) feature, unused at runtime.
        Get-ChildItem -LiteralPath $source -Force |
            Where-Object { -not ($folder -eq "models" -and $_.Name -eq "numba") } |
            ForEach-Object {
                Copy-Item -LiteralPath $_.FullName -Destination $dest -Recurse -Force
            }
    }
}

foreach ($folder in @("temp", "output", "logs")) {
    $source = Join-Path $Root $folder
    $dest = Join-Path $AppOut $folder
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    $gitkeep = Join-Path $source ".gitkeep"
    if (Test-Path $gitkeep) {
        Copy-Item -LiteralPath $gitkeep -Destination (Join-Path $dest ".gitkeep") -Force
    }
}

$backendDest = Join-Path $AppOut "backend"
New-Item -ItemType Directory -Force -Path $backendDest | Out-Null
Copy-Item -LiteralPath (Join-Path $Root "backend\demucs_runner.py") -Destination $backendDest

$runtimeSource = Join-Path $Root "backend\demucs_runtime"
if (Test-Path $runtimeSource) {
    $runtimeDest = Join-Path $AppOut "backend\demucs_runtime"
    New-Item -ItemType Directory -Force -Path $runtimeDest | Out-Null
    if ($PreparedRuntime) {
        $preparedPath = (Resolve-Path -LiteralPath $PreparedRuntime).Path
        if (-not (Test-Path -LiteralPath (Join-Path $preparedPath 'bundle-info.json'))) {
            throw "PreparedRuntime must be a previously verified app-local runtime."
        }
        & robocopy.exe $preparedPath $runtimeDest /E /MT:8 /R:1 /W:1 /NFL /NDL /NJH /NJS /XD __pycache__ /XF '*.pyc'
        if ($LASTEXITCODE -ge 8) { throw "Prepared runtime copy failed." }
        & (Join-Path $runtimeDest 'python.exe') -B -c "import demucs, torch, torchaudio; print('Copied app-local runtime imports verified.')"
        if ($LASTEXITCODE -ne 0) { throw "Copied runtime verification failed." }
    } else {
        & $VenvPython -B (Join-Path $Root "scripts\bundle_demucs_runtime.py") --source $runtimeSource --destination $runtimeDest
        if ($LASTEXITCODE -ne 0) { throw "App-local Demucs runtime bundling failed." }
    }
}

Get-ChildItem -LiteralPath $AppOut -Recurse -Directory -Filter "__pycache__" -Force -ErrorAction SilentlyContinue |
    ForEach-Object {
        $BuildCleanupPath = [IO.Path]::GetFullPath($_.FullName)
        $BuildAllowedRoot = [IO.Path]::GetFullPath($AppOut) + [IO.Path]::DirectorySeparatorChar
        if (-not $BuildCleanupPath.StartsWith($BuildAllowedRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Unsafe build cleanup target: $BuildCleanupPath"
        }
        Remove-Item -LiteralPath $BuildCleanupPath -Recurse -Force
    }
Get-ChildItem -LiteralPath $AppOut -Recurse -File -Filter "*.pyc" -Force -ErrorAction SilentlyContinue |
    Remove-Item -Force

# Ship a clean default settings.json instead of copying the dev copy, which holds a machine-specific output_dir.
@'
{
  "delete_temp_after_render": false,
  "output_dir": ""
}
'@ | Set-Content -LiteralPath (Join-Path $AppOut "settings.json") -Encoding ASCII
foreach ($doc in @("README.txt", "THIRD_PARTY_NOTICES.txt", "project.md")) {
    $docPath = Join-Path $Root $doc
    if (Test-Path -LiteralPath $docPath) {
        Copy-Item -LiteralPath $docPath -Destination (Join-Path $AppOut $doc) -Force
    }
}

$qaDocsSource = Join-Path $Root "docs"
if (Test-Path -LiteralPath $qaDocsSource) {
    Copy-Item -LiteralPath $qaDocsSource -Destination $AppOut -Recurse -Force
}

$licensesSource = Join-Path $Root "LICENSES"
if (Test-Path -LiteralPath $licensesSource) {
    $licensesDest = Join-Path $AppOut "LICENSES"
    New-Item -ItemType Directory -Force -Path $licensesDest | Out-Null
    Get-ChildItem -LiteralPath $licensesSource -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $licensesDest -Recurse -Force
    }
}

$LauncherName = "Run $AppName.cmd"
$LauncherPath = Join-Path $AppOut $LauncherName
@(
    "@echo off",
    "start """" ""%~dp0$AppExe"""
) | Set-Content -LiteralPath $LauncherPath -Encoding ASCII

Write-Host "Build complete with app-local Python (verify on each target PC):"
Write-Host "  $AppOut\$AppExe"
