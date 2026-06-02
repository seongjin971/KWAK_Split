param(
    [string]$PythonExe = "D:\DevTools\Python\Python313\python.exe"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

$env:TEMP = Join-Path $Root "temp"
$env:TMP = Join-Path $Root "temp"
$env:PYTHONPYCACHEPREFIX = Join-Path $Root "temp\pycache"
$env:TORCH_HOME = Join-Path $Root "models\torch"
$env:XDG_CACHE_HOME = Join-Path $Root "models\cache"
$env:HF_HOME = Join-Path $Root "models\huggingface"
$env:DEMUCS_CACHE = Join-Path $Root "models\demucs"
$env:PIP_CACHE_DIR = "D:\DevCache\pip"
$env:PYTHONUSERBASE = "D:\DevData\PythonUserBase"
$env:PATH = (Join-Path $Root "bin") + ";" + $env:PATH

New-Item -ItemType Directory -Force -Path $env:TEMP, $env:PIP_CACHE_DIR, $env:PYTHONUSERBASE | Out-Null
Set-Location $Root
& $PythonExe ".\StemSamplePrep.py"
