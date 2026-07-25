$ErrorActionPreference = "Stop"
$LegacyManifestUrl = "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/latest.json"
$LegacyInstallerUrl = "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install.ps1"
$CurrentInstallerUrl = "https://bytestaff.jiomig.com/redbeacon/install.ps1"

$Manifest = Invoke-RestMethod -Uri $LegacyManifestUrl -UseBasicParsing
if([version]$Manifest.version -le [version]"0.1.73") {
  throw "Legacy manifest does not advertise a version newer than 0.1.73"
}

$Bridge = [string](Invoke-RestMethod -Uri $LegacyInstallerUrl -UseBasicParsing)
if(-not $Bridge.Contains($CurrentInstallerUrl)) {
  throw "Legacy Windows installer does not delegate to the permanent website installer"
}

$CurrentInstaller = [string](Invoke-RestMethod -Uri $CurrentInstallerUrl -UseBasicParsing)
if(-not $CurrentInstaller.Contains("bytestaff-download-releases")) {
  throw "Permanent website installer did not resolve to the current central release installer"
}

Write-Output "legacy-upgrade-smoke-ok current=0.1.73 latest=$($Manifest.version)"
