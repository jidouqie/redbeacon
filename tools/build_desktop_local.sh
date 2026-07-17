#!/usr/bin/env bash
# Build and test the two RedBeacon client packages. Publication is owned only by
# the global bytestaff-digital-employee-publish Skill.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLI_ROOT="$ROOT/cli"
CHANNEL="test"
WINDOWS_HOST="${REDBEACON_WINDOWS_BUILD_HOST:-diaojiawang@10.211.55.3}"
OUTPUT_ROOT="${REDBEACON_LOCAL_BUILD_OUTPUT:-$ROOT/dist/local-build}"

usage() {
  cat <<'EOF'
Usage:
  tools/build_desktop_local.sh [--channel test|stable] [--windows-host USER@IP] [--output-dir DIR]

The command only creates a tested artifact directory. It never reads release
credentials, uploads objects, or changes a public manifest.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --channel) CHANNEL="$2"; shift 2 ;;
    --windows-host) WINDOWS_HOST="$2"; shift 2 ;;
    --output-dir) OUTPUT_ROOT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$CHANNEL" in
  test|testing|beta) CHANNEL="test" ;;
  stable) CHANNEL="stable" ;;
  *) echo "Channel must be stable or test" >&2; exit 2 ;;
esac
if [ "$CHANNEL" = "stable" ] && [ "${REDBEACON_STABLE_APPROVED:-}" != "1" ]; then
  echo "Stable build blocked: approve the completed test release first." >&2
  exit 1
fi

for command_name in git python3 uv ssh scp tar shasum; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Missing local build command: $command_name" >&2
    exit 1
  }
done
if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "The dual-platform build must run on an Apple Silicon Mac." >&2
  exit 1
fi
if [ ! -d "$CLI_ROOT/.git" ]; then
  echo "CLI repository not found: $CLI_ROOT" >&2
  exit 1
fi
ROOT_STATUS="$(git -C "$ROOT" status --porcelain --untracked-files=all)"
if [ -n "$ROOT_STATUS" ]; then
  echo "Project worktree must be clean before a dual-platform build:" >&2
  printf '%s\n' "$ROOT_STATUS" >&2
  exit 1
fi
CLI_STATUS="$(git -C "$CLI_ROOT" status --porcelain)"
if [ -n "$CLI_STATUS" ]; then
  echo "CLI worktree must be clean before a dual-platform build:" >&2
  printf '%s\n' "$CLI_STATUS" >&2
  exit 1
fi

cd "$ROOT"
python3 tools/check_release_contracts.py
if [ ! -x "$CLI_ROOT/.venv/bin/python" ]; then
  echo "The locked CLI virtual environment is missing: $CLI_ROOT/.venv" >&2
  exit 1
fi
"$CLI_ROOT/.venv/bin/python" tools/check_release_dependency_contract.py

SSH_OPTIONS=(
  -o BatchMode=yes
  -o ConnectTimeout=10
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=6
)
SCP_OPTIONS=(
  -o BatchMode=yes
  -o ConnectTimeout=10
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=6
)

echo "==> Checking Windows build VM: $WINDOWS_HOST"
ssh "${SSH_OPTIONS[@]}" "$WINDOWS_HOST" 'cmd.exe /d /c "where uv.exe && uv --version"'

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
CLI_ARCHIVE="$WORK/redbeacon-cli.tar"
RELEASE_ARCHIVE="$WORK/redbeacon-release-source.tar"
MAC_SOURCE="$WORK/mac-source"
mkdir -p "$MAC_SOURCE" "$OUTPUT_ROOT"

git -C "$CLI_ROOT" archive --format=tar HEAD -o "$CLI_ARCHIVE"
tar -xf "$CLI_ARCHIVE" -C "$MAC_SOURCE"
git -C "$ROOT" archive --format=tar HEAD install tools -o "$RELEASE_ARCHIVE"

CLI_COMMIT="$(git -C "$CLI_ROOT" rev-parse HEAD)"
ROOT_COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
SOURCE_SHA="$(shasum -a 256 "$CLI_ARCHIVE" | awk '{print $1}')"
RELEASE_SOURCE_SHA="$(shasum -a 256 "$RELEASE_ARCHIVE" | awk '{print $1}')"
VERSION="$(python3 -c "import pathlib,re; print(re.search(r'__version__\\s*=\\s*\"([^\"]+)\"', pathlib.Path('$MAC_SOURCE/src/redbeacon/__init__.py').read_text()).group(1))")"
APP_NAME="RedBeacon"
if [ "$CHANNEL" = "test" ]; then APP_NAME="RedBeacon_test"; fi
LOCAL_OUT="$OUTPUT_ROOT/$CHANNEL"
rm -rf "$LOCAL_OUT"
mkdir -p "$LOCAL_OUT"

echo "==> Running macOS installer transaction smoke"
python3 tools/smoke_unix_install_transaction.py

echo "==> Building macOS arm64 from CLI commit $CLI_COMMIT"
bash "$MAC_SOURCE/packaging/build_macos_local.sh" --channel "$CHANNEL" --output-dir "$LOCAL_OUT"

echo "==> Sending the identical CLI source snapshot to Windows"
ssh "${SSH_OPTIONS[@]}" "$WINDOWS_HOST" \
  'cmd.exe /d /c "if not exist RedBeaconBuild\incoming mkdir RedBeaconBuild\incoming"'
scp "${SCP_OPTIONS[@]}" "$CLI_ARCHIVE" \
  "${WINDOWS_HOST}:RedBeaconBuild/incoming/redbeacon-cli.tar"
scp "${SCP_OPTIONS[@]}" "$RELEASE_ARCHIVE" \
  "${WINDOWS_HOST}:RedBeaconBuild/incoming/redbeacon-release-source.tar"
scp "${SCP_OPTIONS[@]}" "$MAC_SOURCE/packaging/build_windows_local.ps1" \
  "${WINDOWS_HOST}:RedBeaconBuild/incoming/build_windows_local.ps1"

echo "==> Building Windows x64 inside the Windows 11 ARM64 VM"
ssh "${SSH_OPTIONS[@]}" "$WINDOWS_HOST" \
  "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File RedBeaconBuild\\incoming\\build_windows_local.ps1 -SourceArchive RedBeaconBuild\\incoming\\redbeacon-cli.tar -ReleaseSourceArchive RedBeaconBuild\\incoming\\redbeacon-release-source.tar -Channel $CHANNEL -OutputDir RedBeaconBuild\\out -WorkingRoot RedBeaconBuild"
scp "${SCP_OPTIONS[@]}" \
  "${WINDOWS_HOST}:RedBeaconBuild/out/${APP_NAME}-win-x64.zip" \
  "$LOCAL_OUT/${APP_NAME}-win-x64.zip"

MAC_PACKAGE="$LOCAL_OUT/${APP_NAME}-mac-arm64.zip"
WINDOWS_PACKAGE="$LOCAL_OUT/${APP_NAME}-win-x64.zip"
test -s "$MAC_PACKAGE"
test -s "$WINDOWS_PACKAGE"

ARTIFACT_DIR="$LOCAL_OUT/release-artifacts"
echo "==> Preparing the clean application, installer, skill, and runtime artifact tree"
"$MAC_SOURCE/.venv/bin/python" tools/prepare_release_artifacts.py \
  --channel "$CHANNEL" \
  --version "$VERSION" \
  --package-dir "$LOCAL_OUT" \
  --output-dir "$ARTIFACT_DIR"

# shellcheck disable=SC1090
source "$MAC_SOURCE/packaging/build-versions.env"
python3 - "$ARTIFACT_DIR/metadata/build-evidence.json" "$CHANNEL" "$VERSION" \
  "$CLI_COMMIT" "$ROOT_COMMIT" "$SOURCE_SHA" "$RELEASE_SOURCE_SHA" \
  "$UV_VERSION" "$PYTHON_VERSION" <<'PY'
import datetime
import json
import pathlib
import sys

(path, channel, version, cli_commit, root_commit, source_sha, release_sha,
 uv_version, python_version) = sys.argv[1:]
payload = {
    "schema": "redbeacon-local-build-evidence/v1",
    "channel": channel,
    "version": version,
    "cli_commit": cli_commit,
    "contract_commit": root_commit,
    "platforms": ["mac-arm64", "win-x64"],
    "source_archive_sha256": source_sha,
    "installer_source_sha256": release_sha,
    "uv_version": uv_version,
    "python_version": python_version,
    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
pathlib.Path(path).write_text(
    json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY
chmod 0644 "$ARTIFACT_DIR/metadata/build-evidence.json"
"$MAC_SOURCE/.venv/bin/python" tools/check_release_artifacts.py \
  "$ARTIFACT_DIR" --channel "$CHANNEL" --version "$VERSION"

echo "==> Dual-platform build and artifact preparation complete"
echo "    channel=$CHANNEL version=$VERSION cli_commit=$CLI_COMMIT"
echo "    artifact_dir=$ARTIFACT_DIR"
