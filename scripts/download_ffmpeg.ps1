param(
    [string]$Url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$TempRoot = Join-Path $Root "temp"
$DownloadDir = Join-Path $TempRoot "downloads"
$ExtractDir = Join-Path $DownloadDir "ffmpeg_extract"
$ZipPath = Join-Path $DownloadDir "ffmpeg-release-essentials.zip"
$BinDir = Join-Path $Root "bin"

$env:TEMP = $TempRoot
$env:TMP = $TempRoot

New-Item -ItemType Directory -Force -Path $TempRoot, $DownloadDir, $BinDir | Out-Null

Write-Host "Downloading FFmpeg essentials build..."
Invoke-WebRequest -Uri $Url -OutFile $ZipPath

if (Test-Path $ExtractDir) {
    $resolvedExtract = (Resolve-Path $ExtractDir).Path
    $resolvedTemp = (Resolve-Path $TempRoot).Path
    if (-not $resolvedExtract.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe extract cleanup path: $resolvedExtract"
    }
    Remove-Item -LiteralPath $ExtractDir -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null
Expand-Archive -LiteralPath $ZipPath -DestinationPath $ExtractDir -Force

$tools = @("ffmpeg.exe", "ffprobe.exe", "ffplay.exe")
foreach ($tool in $tools) {
    $found = Get-ChildItem -LiteralPath $ExtractDir -Recurse -Filter $tool | Select-Object -First 1
    if ($null -eq $found) {
        throw "Could not find $tool in downloaded archive."
    }
    Copy-Item -LiteralPath $found.FullName -Destination (Join-Path $BinDir $tool) -Force
    Write-Host "Copied $tool to bin/"
}

Write-Host "FFmpeg is ready in $BinDir"
