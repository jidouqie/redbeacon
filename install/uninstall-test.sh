#!/usr/bin/env bash
# RedBeacon_test uninstaller wrapper (Mac/Linux).
set -euo pipefail

OSS="${REDBEACON_OSS:-https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com}"
curl -fsSL "$OSS/uninstall.sh" | REDBEACON_CHANNEL=test bash
