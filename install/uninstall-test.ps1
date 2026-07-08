# RedBeacon_test uninstaller wrapper (Windows).
$ErrorActionPreference = "Stop"
function Pause-OnFailure(){
  if($env:CI -eq "true" -or $env:GITHUB_ACTIONS -eq "true" -or $env:REDBEACON_NO_PAUSE -eq "1"){ return }
  try { Read-Host "Press Enter to close this window" | Out-Null } catch {}
}
trap {
  Write-Host ""
  Write-Host "xx RedBeacon_test uninstaller bootstrap failed. Details:" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  Pause-OnFailure
  exit 1
}
$oss = if($env:REDBEACON_OSS){ $env:REDBEACON_OSS } else { "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com" }
$env:REDBEACON_CHANNEL = "test"
irm "$oss/uninstall.ps1" | iex
