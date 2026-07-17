$ErrorActionPreference = "Stop"
$oldChannel = $env:REDBEACON_CHANNEL
function Assert-TestWrapperUrl([string]$Url, [string]$Label){
  try { $uri = [Uri]$Url } catch { throw "$Label URL is invalid." }
  $safeHttps = ($uri.Scheme -eq "https" -and -not $uri.UserInfo -and -not $uri.Query -and -not $uri.Fragment)
  $safeLoopback = ($env:REDBEACON_INSTALLER_TEST_MODE -eq "1" -and $uri.Scheme -eq "http" -and $uri.Host -eq "127.0.0.1")
  if(-not $safeHttps -and -not $safeLoopback){ throw "$Label URL is unsafe." }
}
try {
  $env:REDBEACON_CHANNEL = "test"
  $origin = "https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com"
  $manifestUrl = if($env:REDBEACON_UPDATE_URL){ $env:REDBEACON_UPDATE_URL } else { "$origin/projects/redbeacon/test/latest.json" }
  Assert-TestWrapperUrl $manifestUrl "Manifest"
  $manifest = Invoke-RestMethod -Uri $manifestUrl -UseBasicParsing -TimeoutSec 20
  $entry = @($manifest.artifacts | Where-Object { ([string]$_.path) -eq "installers/uninstall.ps1" })
  if($entry.Count -ne 1){ throw "RedBeacon test uninstaller is missing from the central manifest." }
  $uninstallerUrl = [string]$entry[0].url
  Assert-TestWrapperUrl $uninstallerUrl "Uninstaller"
  Invoke-Expression (Invoke-WebRequest -Uri $uninstallerUrl -UseBasicParsing -TimeoutSec 60).Content
}
finally {
  if($null -eq $oldChannel){ Remove-Item Env:\REDBEACON_CHANNEL -ErrorAction SilentlyContinue }
  else { $env:REDBEACON_CHANNEL = $oldChannel }
}
