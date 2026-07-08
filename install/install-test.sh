#!/usr/bin/env bash
# RedBeacon_test installer wrapper (Mac/Linux).
set -euo pipefail

OSS="${REDBEACON_OSS:-https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com}"
curl -fsSL "$OSS/install.sh" | REDBEACON_CHANNEL=test bash
