param([string]$PythonExe = "")
$ErrorActionPreference = "Stop"
$TestRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $PythonExe) { $PythonExe = (Get-Command python.exe -ErrorAction Stop).Source }
$TestPython = Join-Path $TestRoot ".build\qa\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $TestPython)) {
    & $PythonExe -m venv (Join-Path $TestRoot ".build\qa")
    if ($LASTEXITCODE -ne 0) { throw "Could not create the test environment." }
}
$env:PIP_CACHE_DIR = Join-Path $TestRoot "temp\pip-cache"
& $TestPython -m pip install -r (Join-Path $TestRoot "requirements-dev.txt")
if ($LASTEXITCODE -ne 0) { throw "Could not install test dependencies." }
Set-Location $TestRoot
& $TestPython -B -m pytest tests -q --capture=sys -p no:cacheprovider
exit $LASTEXITCODE
