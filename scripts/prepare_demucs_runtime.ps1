param(
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
if (-not $PythonExe) { $PythonExe = (Get-Command python.exe -ErrorAction Stop).Source }
$RuntimeDir = Join-Path $Root "backend\demucs_runtime"
$RuntimePython = Join-Path $RuntimeDir "Scripts\python.exe"

$env:TEMP = Join-Path $Root "temp"
$env:TMP = Join-Path $Root "temp"
$env:PIP_CACHE_DIR = Join-Path $Root "temp\pip-cache"
$env:PYTHONPYCACHEPREFIX = Join-Path $Root "temp\pycache"
$env:TORCH_HOME = Join-Path $Root "models\torch"
$env:XDG_CACHE_HOME = Join-Path $Root "models\cache"
$env:HF_HOME = Join-Path $Root "models\huggingface"
$env:DEMUCS_CACHE = Join-Path $Root "models\demucs"
$env:PATH = (Join-Path $Root "bin") + ";" + $env:PATH

New-Item -ItemType Directory -Force -Path `
    $env:TEMP, `
    $env:PIP_CACHE_DIR, `
    $env:TORCH_HOME, `
    $env:HF_HOME, `
    $env:DEMUCS_CACHE | Out-Null

if (-not (Test-Path $RuntimePython)) {
    Write-Host "Creating app-local Demucs runtime..."
    & $PythonExe -m venv $RuntimeDir
    if ($LASTEXITCODE -ne 0) { throw "Failed to create Demucs environment." }
}

Write-Host "Installing Demucs into backend/demucs_runtime. This can take a while and may use several GB."
& $RuntimePython -B -c "import sys; assert sys.version_info[:2] == (3, 11), 'The audited runtime requires CPython 3.11.'"
if ($LASTEXITCODE -ne 0) { throw "Unsupported Python version for the audited runtime." }
& $RuntimePython -m pip install -r (Join-Path $Root "requirements-demucs.txt")
if ($LASTEXITCODE -ne 0) { throw "Failed to install Demucs." }
& $RuntimePython (Join-Path $ScriptDir "patch_demucs_audio.py") $RuntimeDir
if ($LASTEXITCODE -ne 0) { throw "Failed to patch Demucs WAV output." }

Write-Host "Demucs runtime is ready:"
Write-Host "  $RuntimePython -m demucs --help"
