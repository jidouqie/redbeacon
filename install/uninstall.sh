#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# RedBeacon uninstaller (Mac/Linux). Run:
#     curl -fsSL https://bytestaff.jiomig.com/uninstall.sh | bash
#
# Removes the software bundle, update leftovers, CLI shim, skills, desktop entry,
# and browser cache.
# Your BUSINESS DATA is KEPT by default:
#     ~/.redbeacon   (accounts / cookies / generated content / local DB)
#     ~/.bytestaff   (platform login / device token)
# To also wipe that data, run:
#     curl -fsSL https://bytestaff.jiomig.com/uninstall.sh | REDBEACON_PURGE=1 bash
# All output is English on purpose (avoids garbled text on some consoles).
# ------------------------------------------------------------------------------
set -uo pipefail
say()  { printf '\033[36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!! %s\033[0m\n' "$*"; }

PURGE="${REDBEACON_PURGE:-}"

refresh_macos_app_registration() {
  app="$1"
  [ "$(uname -s 2>/dev/null || true)" = "Darwin" ] || return 0
  lsreg="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
  if [ -x "$lsreg" ] && [ -d "$app" ]; then "$lsreg" -u "$app" >/dev/null 2>&1 || true; fi
  if command -v qlmanage >/dev/null 2>&1; then qlmanage -r cache >/dev/null 2>&1 || true; fi
  killall Dock >/dev/null 2>&1 || true
}

# 1) stop running app processes if possible
say "Stopping RedBeacon..."
pkill -f "RedBeacon" >/dev/null 2>&1 || true
pkill -f "redbeacon-cli" >/dev/null 2>&1 || true

# 2) bundled app, update leftovers + CLI shim
say "Removing RedBeacon app and CLI..."
refresh_macos_app_registration "$HOME/Applications/RedBeacon.app"
rm -rf "$HOME/Applications/RedBeacon.app" 2>/dev/null || true           # macOS bundle
rm -rf "$HOME/Applications/RedBeacon.app.previous-update" 2>/dev/null || true
rm -rf "$HOME/.local/share/redbeacon" 2>/dev/null || true               # Linux bundle
rm -rf "$HOME/.local/share/redbeacon.previous-update" 2>/dev/null || true
rm -f  "$HOME"/.local/bin/redbeacon "$HOME"/.local/bin/redbeacon-app 2>/dev/null || true

say "Removing update staging files..."
rm -rf "$HOME/.redbeacon/data/updates" 2>/dev/null || true
if [ -n "${REDBEACON_UPDATE_WORKDIR:-}" ]; then
  rm -rf "$REDBEACON_UPDATE_WORKDIR" 2>/dev/null || true
fi

# Legacy uv-tool install leftovers (kept for users who installed older builds).
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
if [ -x "$UV" ]; then
  "$UV" tool uninstall redbeacon >/dev/null 2>&1 || warn "  redbeacon was not installed via uv (or already removed)"
fi
rm -rf "$HOME/.local/share/uv/tools/redbeacon" 2>/dev/null || true

# 3) skills (Claude command dir + Codex derived skills)
say "Removing skills..."
rm -f  "$HOME"/.claude/commands/redbeacon*.md 2>/dev/null || true
rm -rf "$HOME"/.codex/skills/redbeacon* 2>/dev/null || true

# 4) desktop entry
say "Removing desktop entry..."
rm -f  "$HOME/.local/share/applications/redbeacon.desktop" 2>/dev/null || true

# 5) browser engine cache (Playwright Chromium; re-downloadable)
say "Removing browser engine cache..."
rm -rf "$HOME/Library/Caches/ms-playwright" 2>/dev/null || true   # macOS
rm -rf "$HOME/.cache/ms-playwright" 2>/dev/null || true           # Linux

# 6) business data -- only when REDBEACON_PURGE=1
if [ -n "$PURGE" ]; then
  say "PURGE: removing your RedBeacon data (~/.redbeacon, ~/.bytestaff)..."
  rm -rf "$HOME/.redbeacon" 2>/dev/null || true
  rm -rf "$HOME/.bytestaff" 2>/dev/null || true
else
  warn "Kept your data: ~/.redbeacon (accounts/content) + ~/.bytestaff (login)."
  warn "To wipe it too: curl -fsSL https://bytestaff.jiomig.com/uninstall.sh | REDBEACON_PURGE=1 bash"
fi

say "RedBeacon uninstalled."
