# RedBeacon_test uninstaller wrapper (Windows).
$ErrorActionPreference = "Stop"
$oss = if($env:REDBEACON_OSS){ $env:REDBEACON_OSS } else { "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com" }
$env:REDBEACON_CHANNEL = "test"
irm "$oss/uninstall.ps1" | iex
