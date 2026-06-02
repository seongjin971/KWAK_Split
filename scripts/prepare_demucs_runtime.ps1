param(
    [string]$PythonExe = "D:\DevTools\Python\Python313\python.exe"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$RuntimeDir = Join-Path $Root "backend\demucs_runtime"
$RuntimePython = Join-Path $RuntimeDir "Scripts\python.exe"

$env:TEMP = Join-Path $Root "temp"
$env:TMP = Join-Path $Root "temp"
$env:PIP_CACHE_DIR = "D:\DevCache\pip"
$env:PYTHONUSERBASE = "D:\DevData\PythonUserBase"
$env:PYTHONPYCACHEPREFIX = Join-Path $Root "temp\pycache"
$env:TORCH_HOME = Join-Path $Root "models\torch"
$env:XDG_CACHE_HOME = Join-Path $Root "models\cache"
$env:HF_HOME = Join-Path $Root "models\huggingface"
$env:DEMUCS_CACHE = Join-Path $Root "models\demucs"
$env:PATH = (Join-Path $Root "bin") + ";" + $env:PATH

New-Item -ItemType Directory -Force -Path `
    $env:TEMP, `
    $env:PIP_CACHE_DIR, `
    $env:PYTHONUSERBASE, `
    $env:TORCH_HOME, `
    $env:HF_HOME, `
    $env:DEMUCS_CACHE | Out-Null

if (-not (Test-Path $RuntimePython)) {
    Write-Host "Creating app-local Demucs runtime..."
    & $PythonExe -m venv $RuntimeDir
}

Write-Host "Installing Demucs into backend/demucs_runtime. This can take a while and may use several GB."
& $RuntimePython -m pip install --upgrade pip
& $RuntimePython -m pip install demucs torchcodec
& $RuntimePython (Join-Path $ScriptDir "patch_demucs_audio.py") $RuntimeDir

Write-Host "Demucs runtime is ready:"
Write-Host "  $RuntimePython -m demucs --help"
