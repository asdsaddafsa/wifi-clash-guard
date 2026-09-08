param([switch]$Launch, [switch]$Settings)
$scriptPath = Join-Path $PSScriptRoot 'WifiClashGuard.ps1'
if ($Launch) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath -Launch
}
elseif ($Settings) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath -Settings
}
else {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath
}
