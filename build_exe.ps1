param(
    [string]$Version = 'v0.1'
)

$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) { $pythonPath = $pythonCommand.Source }
}
if (-not (Test-Path -LiteralPath $pythonPath)) { throw '找不到 Python。请先安装 Python 3.10+。' }

Push-Location $PSScriptRoot
try {
    & $pythonPath -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw '安装依赖失败。' }
    & $pythonPath -m PyInstaller --noconfirm --clean --onefile --windowed --name WifiClashGuard wifi_clash_guard.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 构建失败。' }
    $target = Join-Path $PSScriptRoot "dist\WifiClashGuard-$Version-windows-x64.exe"
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'dist\WifiClashGuard.exe') -Destination $target -Force
    Write-Output "Built: $target"
}
finally {
    Pop-Location
}
