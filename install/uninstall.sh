#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# RedBeacon uninstaller (Mac/Linux). Run:
#     Fetch installers/uninstall.sh from the current central manifest and run it.
#
# Removes the software bundle, update leftovers, CLI shim, skills, desktop entry,
# and browser cache.
# Your BUSINESS DATA is KEPT by default:
#     ~/.redbeacon   (accounts / cookies / generated content / local DB)
#     ~/.bytestaff   (platform login / device token)
# To also wipe that data, run:
#     Fetch the same central uninstaller, then run it with REDBEACON_PURGE=1.
# All output is English on purpose (avoids garbled text on some consoles).
# ------------------------------------------------------------------------------
set -uo pipefail
say()  { printf '\033[36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!! %s\033[0m\n' "$*"; }

case "${REDBEACON_PURGE:-}" in
  1|true|TRUE|yes|YES|on|ON) PURGE=1 ;;
  *) PURGE="" ;;
esac
CHANNEL="${REDBEACON_CHANNEL:-stable}"
case "$CHANNEL" in test|testing|beta) CHANNEL="test" ;; *) CHANNEL="stable" ;; esac
if [ "$CHANNEL" = "test" ]; then
  APP_NAME="RedBeacon_test"
  CMD_NAME="redbeacon-test"
  CLI_NAME="redbeacon-test-cli"
  SHARE_NAME="redbeacon-test"
  DESKTOP_ID="redbeacon-test"
  DATA_HOME="$HOME/.redbeacon_test"
  TOKEN_HOME="$HOME/.bytestaff_test"
  SKILL_DIR="${REDBEACON_SKILL_DIR:-$HOME/.claude/commands-redbeacon-test}"
  CODEX_SKILL_GLOB="redbeacon-test*"
else
  APP_NAME="RedBeacon"
  CMD_NAME="redbeacon"
  CLI_NAME="redbeacon-cli"
  SHARE_NAME="redbeacon"
  DESKTOP_ID="redbeacon"
  DATA_HOME="$HOME/.redbeacon"
  TOKEN_HOME="$HOME/.bytestaff"
  SKILL_DIR="${REDBEACON_SKILL_DIR:-$HOME/.claude/commands}"
  CODEX_SKILL_GLOB="redbeacon*"
fi
PORTABLE_SKILL_DIRS="
${REDBEACON_CODEX_SKILL_DIR:-$HOME/.codex/skills}
${REDBEACON_OPENCLAW_SKILL_DIR:-$HOME/.openclaw/skills}
${REDBEACON_HERMES_SKILL_DIR:-$HOME/.hermes/skills}
${REDBEACON_WORKBUDDY_SKILL_DIR:-$HOME/.workbuddy/skills}
"

refresh_macos_app_registration() {
  app="$1"
  [ "$(uname -s 2>/dev/null || true)" = "Darwin" ] || return 0
  lsreg="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
  if [ -x "$lsreg" ] && [ -d "$app" ]; then "$lsreg" -u "$app" >/dev/null 2>&1 || true; fi
  if command -v qlmanage >/dev/null 2>&1; then qlmanage -r cache >/dev/null 2>&1 || true; fi
  killall Dock >/dev/null 2>&1 || true
}

# 1) stop running app processes if possible
say "Stopping $APP_NAME..."
if [ "${REDBEACON_SKIP_PROCESS_STOP:-}" != "1" ]; then
  pkill -f "$APP_NAME" >/dev/null 2>&1 || true
  pkill -f "$CLI_NAME" >/dev/null 2>&1 || true
fi

# 2) bundled app, update leftovers + CLI shim
say "Removing $APP_NAME app and CLI..."
refresh_macos_app_registration "$HOME/Applications/$APP_NAME.app"
rm -rf "$HOME/Applications/$APP_NAME.app" 2>/dev/null || true           # macOS bundle
rm -rf "$HOME/Applications/$APP_NAME.app.previous-update" 2>/dev/null || true
rm -rf "$HOME/.local/share/$SHARE_NAME" 2>/dev/null || true             # Linux bundle
rm -rf "$HOME/.local/share/$SHARE_NAME.previous-update" 2>/dev/null || true
rm -f  "$HOME/.local/bin/$CMD_NAME" 2>/dev/null || true
[ "$CHANNEL" = "stable" ] && rm -f "$HOME"/.local/bin/redbeacon-app 2>/dev/null || true

say "Removing update staging files..."
rm -rf "$DATA_HOME/data/updates" 2>/dev/null || true
if [ -n "${REDBEACON_UPDATE_WORKDIR:-}" ]; then
  rm -rf "$REDBEACON_UPDATE_WORKDIR" 2>/dev/null || true
fi

# Legacy uv-tool install leftovers (kept for users who installed older builds).
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
if [ "$CHANNEL" = "stable" ] && [ -x "$UV" ]; then
  "$UV" tool uninstall redbeacon >/dev/null 2>&1 || warn "  redbeacon was not installed via uv (or already removed)"
fi
[ "$CHANNEL" = "stable" ] && rm -rf "$HOME/.local/share/uv/tools/redbeacon" 2>/dev/null || true

# 3) skills (Claude command dir + portable Agent Skills hosts)
say "Removing skills..."
rm -f  "$SKILL_DIR"/redbeacon*.md 2>/dev/null || true
printf '%s\n' "$PORTABLE_SKILL_DIRS" | while IFS= read -r skill_root; do
  [ -n "$skill_root" ] && [ -d "$skill_root" ] || continue
  if [ "$CHANNEL" = "test" ]; then
    find "$skill_root" -maxdepth 1 -type d -name "$CODEX_SKILL_GLOB" -exec rm -rf {} + 2>/dev/null || true
  else
    find "$skill_root" -maxdepth 1 -type d -name "$CODEX_SKILL_GLOB" ! -name 'redbeacon-test*' -exec rm -rf {} + 2>/dev/null || true
  fi
done

# 4) desktop entry
say "Removing desktop entry..."
rm -f  "$HOME/.local/share/applications/$DESKTOP_ID.desktop" 2>/dev/null || true

# 5) channel-owned browser engine cache (re-downloadable). Never remove the
# global Playwright/CloakBrowser caches: other apps or the other RedBeacon
# channel may still own and use them.
say "Removing browser engine cache..."
rm -rf "$DATA_HOME/browser" 2>/dev/null || true

# 6) business data -- only when REDBEACON_PURGE=1
if [ -n "$PURGE" ]; then
  say "PURGE: removing your $APP_NAME data ($DATA_HOME, $TOKEN_HOME)..."
  rm -rf "$DATA_HOME" 2>/dev/null || true
  rm -rf "$TOKEN_HOME" 2>/dev/null || true
else
  warn "Kept your data: $DATA_HOME (accounts/content) + $TOKEN_HOME (login)."
  warn "To wipe it too, set REDBEACON_PURGE=1 and run the current central uninstaller again."
fi

say "$APP_NAME uninstalled."
