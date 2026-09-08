$scriptPath = Join-Path $PSScriptRoot 'WifiClashGuard.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath -Settings
