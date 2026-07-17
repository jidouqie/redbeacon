#!/bin/sh
set -eu
export REDBEACON_CHANNEL=test
origin="https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com"
manifest_url="${REDBEACON_UPDATE_URL:-$origin/projects/redbeacon/test/latest.json}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
case "$manifest_url" in
  http://127.0.0.1:*/*)
    [ "${REDBEACON_INSTALLER_TEST_MODE:-}" = "1" ] \
      || { echo "Unsafe test manifest URL" >&2; exit 1; }
    curl -fsSL --connect-timeout 3 --max-time 20 "$manifest_url" -o "$tmp/latest.json"
    ;;
  https://*)
    curl -fsSL --proto '=https' --proto-redir '=https' --connect-timeout 3 --max-time 20 \
      "$manifest_url" -o "$tmp/latest.json"
    ;;
  *) echo "Unsafe test manifest URL" >&2; exit 1 ;;
esac
uninstaller_url="$(/usr/bin/osascript -l JavaScript - "$tmp/latest.json" <<'JXA'
function run(argv) {
  const app = Application.currentApplication(); app.includeStandardAdditions = true;
  const data = JSON.parse(app.read(Path(argv[0])));
  const rows = (data.artifacts || []).filter(x => x.path === "installers/uninstall.sh");
  if (rows.length !== 1) throw new Error("test uninstaller is missing");
  return String(rows[0].url);
}
JXA
)"
case "$uninstaller_url" in
  http://127.0.0.1:*/*)
    [ "${REDBEACON_INSTALLER_TEST_MODE:-}" = "1" ] \
      || { echo "Unsafe test uninstaller URL" >&2; exit 1; }
    curl -fsSL --connect-timeout 3 --max-time 60 "$uninstaller_url" | bash
    ;;
  https://*)
    curl -fsSL --proto '=https' --proto-redir '=https' --connect-timeout 3 --max-time 60 \
      "$uninstaller_url" | bash
    ;;
  *) echo "Unsafe test uninstaller URL" >&2; exit 1 ;;
esac
