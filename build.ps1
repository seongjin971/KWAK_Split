param(
    [string]$PythonExe = "D:\DevTools\Python\Python313\python.exe"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildRoot = Join-Path $Root ".build"
$Venv = Join-Path $BuildRoot "venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$ReleaseRoot = Join-Path $Root "release"
$AppName = "KWAK Split"
$AppExe = "$AppName.exe"
$AppOut = Join-Path $ReleaseRoot $AppName

$env:TEMP = Join-Path $Root "temp"
$env:TMP = Join-Path $Root "temp"
$env:PIP_CACHE_DIR = "D:\DevCache\pip"
$env:PYTHONUSERBASE = "D:\DevData\PythonUserBase"
$env:PYTHONPYCACHEPREFIX = Join-Path $BuildRoot "pycache"
$env:PYINSTALLER_CONFIG_DIR = Join-Path $BuildRoot "pyinstaller-cache"

New-Item -ItemType Directory -Force -Path `
    $BuildRoot, `
    $ReleaseRoot, `
    $env:TEMP, `
    $env:PIP_CACHE_DIR, `
    $env:PYTHONUSERBASE, `
    $env:PYINSTALLER_CONFIG_DIR | Out-Null

if (-not (Test-Path $VenvPython)) {
    & $PythonExe -m venv $Venv
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $Root "requirements-build.txt")

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

$runtimeSource = Join-Path $Root "backend\demucs_runtime"
if (Test-Path $runtimeSource) {
    $runtimeDest = Join-Path $AppOut "backend\demucs_runtime"
    New-Item -ItemType Directory -Force -Path $runtimeDest | Out-Null
    Get-ChildItem -LiteralPath $runtimeSource -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $runtimeDest -Recurse -Force
    }
}

Get-ChildItem -LiteralPath $AppOut -Recurse -Directory -Filter "__pycache__" -Force -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $AppOut -Recurse -File -Filter "*.pyc" -Force -ErrorAction SilentlyContinue |
    Remove-Item -Force

# Ship a clean default settings.json instead of copying the dev copy, which holds a machine-specific output_dir.
@'
{
  "delete_temp_after_render": false,
  "output_dir": ""
}
'@ | Set-Content -LiteralPath (Join-Path $AppOut "settings.json") -Encoding ASCII
foreach ($doc in @("README.txt", "THIRD_PARTY_NOTICES.txt")) {
    $docPath = Join-Path $Root $doc
    if (Test-Path -LiteralPath $docPath) {
        Copy-Item -LiteralPath $docPath -Destination (Join-Path $AppOut $doc) -Force
    }
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

Write-Host "Portable build complete:"
Write-Host "  $AppOut\$AppExe"
