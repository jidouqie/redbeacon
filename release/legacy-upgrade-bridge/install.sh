#!/bin/sh
set -eu

installer_url='https://bytestaff.jiomig.com/redbeacon/install.sh'
tmp_file="${TMPDIR:-/tmp}/redbeacon-current-installer.$$"
trap 'rm -f "$tmp_file"' EXIT HUP INT TERM

printf '%s\n' 'Redirecting this legacy RedBeacon updater to the current installer...'
curl -fsSL --connect-timeout 10 --max-time 60 "$installer_url" -o "$tmp_file"
/bin/sh "$tmp_file"
