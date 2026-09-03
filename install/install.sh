#!/bin/sh
# Fixed stable-channel bootstrap. The shared implementation lives in
# install-core.sh and receives its channel only from this entrypoint.
# BYTESTAFF_CHANNEL_IDENTITY: stable
# BYTESTAFF_CANONICAL_MANIFEST_URL: https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com/projects/redbeacon/stable/latest.json
# BYTESTAFF_FIXED_CHANNEL_ARGUMENT: stable
# BYTESTAFF_AMBIENT_CHANNEL_OVERRIDES: forbidden
set -eu

ENTRY_CHANNEL="stable"
CORE_ARTIFACT="installers/install-core.sh"
CENTRAL_ORIGIN="https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com"
MANIFEST_URL="https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com/projects/redbeacon/stable/latest.json"

[ "$#" -eq 0 ] || { printf 'xx This installer accepts no arguments.\n' >&2; exit 2; }

die() { printf 'xx %s\n' "$*" >&2; exit 1; }

resolve_trusted_home() {
  trusted_user="$(/usr/bin/id -un)" || return 1
  trusted_record="$(/usr/bin/id -P "$trusted_user")" || return 1
  printf '%s\n' "$trusted_record" | /usr/bin/awk -F: 'NR == 1 { print $9 }'
}

TRUSTED_HOME="$(resolve_trusted_home)" || die "Could not resolve the signed-in macOS user's home directory."
case "$TRUSTED_HOME" in /*) ;; *) die "The trusted macOS home directory is invalid." ;; esac
[ -d "$TRUSTED_HOME" ] || die "The trusted macOS home directory does not exist."
HOME="$TRUSTED_HOME"
PATH="/usr/bin:/bin:/usr/sbin:/sbin"
LC_ALL="C"
export HOME PATH LC_ALL
unset BASH_ENV ENV CDPATH GLOBIGNORE TAR_OPTIONS UNZIP UNZIPOPT ZIPOPT \
  DYLD_INSERT_LIBRARIES DYLD_LIBRARY_PATH LD_PRELOAD LD_LIBRARY_PATH \
  PYTHONHOME PYTHONPATH CURL_CA_BUNDLE SSL_CERT_FILE 2>/dev/null || true
umask 077

is_safe_url() {
  case "$1" in
    "$CENTRAL_ORIGIN"/*) return 0 ;;
    *) return 1 ;;
  esac
}

fetch_file() {
  url="$1" output="$2" timeout="$3"
  is_safe_url "$url" || die "Installer URL is unsafe."
  if [ "${CENTRAL_ORIGIN#https://}" != "$CENTRAL_ORIGIN" ]; then
    /usr/bin/curl -q -fsSL --proto '=https' --proto-redir '=https' \
      --connect-timeout 3 --max-time "$timeout" "$url" -o "$output"
  else
    /usr/bin/curl -q -fsSL --connect-timeout 3 --max-time "$timeout" "$url" -o "$output"
  fi
}

manifest_value() {
  field="$1"
  if [ -x /usr/bin/osascript ]; then
    /usr/bin/osascript -l JavaScript - "$MANIFEST_FILE" "$CORE_ARTIFACT" "$field" <<'JXA'
function run(argv) {
  const app = Application.currentApplication(); app.includeStandardAdditions = true;
  const data = JSON.parse(app.read(Path(argv[0])));
  if (["project", "channel", "schema", "version"].includes(argv[2])) return String(data[argv[2]] || "");
  const rows = (data.artifacts || []).filter(x => x.path === argv[1]);
  if (rows.length !== 1) throw new Error("installer core is missing");
  return String(rows[0][argv[2]] || "");
}
JXA
    return
  fi
  die "The trusted macOS JSON parser is unavailable."
}

sha256_file() {
  [ -x /usr/bin/shasum ] || return 1
  /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'
}

TMP="$(/usr/bin/mktemp -d /private/tmp/redbeacon-stable-install.XXXXXX)" \
  || die "Could not create a trusted installer directory."
trap '/bin/rm -rf "$TMP"' EXIT
TEMP="$TMP"
TMPDIR="$TMP"
CURL_HOME="$TMP/curl-home"
XDG_CONFIG_HOME="$TMP/xdg-config"
export TMP TEMP TMPDIR CURL_HOME XDG_CONFIG_HOME
MANIFEST_FILE="$TMP/latest.json"
CORE_FILE="$TMP/install-core.sh"

fetch_file "$MANIFEST_URL" "$MANIFEST_FILE" 20 \
  || die "Could not fetch the stable RedBeacon release manifest."
[ "$(manifest_value project)" = "redbeacon" ] \
  && [ "$(manifest_value channel)" = "$ENTRY_CHANNEL" ] \
  || die "Release manifest does not match RedBeacon stable."
manifest_schema="$(manifest_value schema)"
manifest_version="$(manifest_value version)"
[ "$manifest_schema" = "1" ] || die "Release manifest schema is invalid."
printf '%s\n' "$manifest_version" | /usr/bin/grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' \
  || die "Release manifest version is invalid."

core_url="$(manifest_value url)"
core_size="$(manifest_value size)"
core_sha="$(manifest_value sha256)"
case "$core_size" in ''|*[!0-9]*) die "Installer core size is invalid." ;; esac
[ "$core_size" -gt 0 ] || die "Installer core size is invalid."
case "$core_sha" in ''|*[!0-9a-f]*) die "Installer core SHA-256 is invalid." ;; esac
[ "${#core_sha}" -eq 64 ] || die "Installer core SHA-256 is invalid."
expected_core_url="$CENTRAL_ORIGIN/projects/redbeacon/stable/releases/$manifest_version/$CORE_ARTIFACT"
[ "$core_url" = "$expected_core_url" ] \
  || die "Installer core URL does not match the stable release."

fetch_file "$core_url" "$CORE_FILE" 60 || die "Could not fetch the stable installer core."
[ "$(/usr/bin/wc -c < "$CORE_FILE" | /usr/bin/tr -d '[:space:]')" = "$core_size" ] \
  || die "Installer core size verification failed."
[ "$(sha256_file "$CORE_FILE")" = "$core_sha" ] \
  || die "Installer core SHA-256 verification failed."

/bin/bash "$CORE_FILE" "stable" "$MANIFEST_FILE" "$CENTRAL_ORIGIN" "production"
