# RedBeacon_test installer wrapper (Windows).
$ErrorActionPreference = "Stop"
$oss = if($env:REDBEACON_OSS){ $env:REDBEACON_OSS } else { "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com" }
$env:REDBEACON_CHANNEL = "test"
irm "$oss/install.ps1" | iex
