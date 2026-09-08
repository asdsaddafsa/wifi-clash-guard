param([switch]$Launch)
$scriptPath = Join-Path $PSScriptRoot 'WifiClashGuard.ps1'
if ($Launch) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath -Launch
}
else {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath
}
