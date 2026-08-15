#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI_ROOT="$ROOT/cli"
PYTHON="$CLI_ROOT/.venv/bin/python"
CHANNEL="${1:-stable}"

case "$CHANNEL" in
  stable|test) ;;
  *)
    echo "usage: tools/run_desktop_dev.sh [stable|test]" >&2
    exit 2
    ;;
esac

if [ ! -x "$PYTHON" ]; then
  echo "RedBeacon development environment is missing: $PYTHON" >&2
  echo "Prepare cli/.venv from cli/uv.lock before launching the desktop client." >&2
  exit 1
fi

# A source client must never inherit another Python installation or release
# channel.  Importing a globally installed RedBeacon/Playwright can show an old
# UI and request the wrong browser revision even when the repository is current.
unset PYTHONHOME PYTHONPATH
unset REDBEACON_DATA_DIR REDBEACON_LOG_DIR BYTESTAFF_HOME
unset PLAYWRIGHT_BROWSERS_PATH PLAYWRIGHT_DOWNLOAD_HOST
unset PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST PLAYWRIGHT_NODEJS_PATH
unset CLOAKBROWSER_CACHE_DIR CLOAKBROWSER_BINARY_PATH
export PYTHONNOUSERSITE=1
export REDBEACON_CHANNEL="$CHANNEL"
export REDBEACON_BUILD_CHANNEL="$CHANNEL"

cd "$CLI_ROOT"
exec "$PYTHON" -I -m redbeacon.app_main
