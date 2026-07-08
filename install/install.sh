#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# RedBeacon installer (Mac/Linux). Run:
#     curl -fsSL https://bytestaff.jiomig.com/install.sh | bash
#
# Installs a SELF-CONTAINED bundle (Python + all deps + Playwright driver already
# inside). No uv / no pip / no compiling -- just download + unzip + place.
# Gives you both:
#   - a double-click desktop app (RedBeacon)
#   - the `redbeacon` command (for an AI assistant to drive it)
# The browser engine (Chromium) downloads on first run via a China mirror.
# All output is English on purpose (avoids garbled text on some consoles).
# ------------------------------------------------------------------------------
set -uo pipefail

OSS="${REDBEACON_OSS:-https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com}"
SKILL_DEST="${REDBEACON_SKILL_DIR:-$HOME/.claude/commands}"
BINDIR="$HOME/.local/bin"

say()  { printf '\033[36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!! %s\033[0m\n' "$*"; }
die()  { printf '\033[31mxx %s\033[0m\n' "$*" >&2; exit 1; }

refresh_macos_app_registration() {
  app="$1"
  [ "$OS" = "Darwin" ] || return 0
  [ -d "$app" ] || return 0
  touch "$app" "$app/Contents" "$app/Contents/Info.plist" 2>/dev/null || true
  lsreg="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
  if [ -x "$lsreg" ]; then
    "$lsreg" -u "$app" >/dev/null 2>&1 || true
    "$lsreg" -f "$app" >/dev/null 2>&1 || true
  fi
  if command -v qlmanage >/dev/null 2>&1; then qlmanage -r cache >/dev/null 2>&1 || true; fi
  killall Dock >/dev/null 2>&1 || true
}

# 1) pick the bundle for this OS/arch
OS="$(uname -s)"; ARCH="$(uname -m)"
case "$OS" in
  Darwin) case "$ARCH" in arm64|aarch64) PLAT=mac-arm64 ;; *) PLAT=mac-x64 ;; esac ;;
  Linux)  PLAT=linux-x64 ;;
  *) die "Unsupported OS: $OS (use the Windows installer on Windows)" ;;
esac
BUNDLE_URL="$OSS/app/RedBeacon-$PLAT.zip"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$BINDIR"

# 2) Fast no-op for repeat installs: fetch only the tiny manifest, then skip the
# large bundle when the installed client is already current.
LATEST=""
if curl -fsSL --connect-timeout 8 --max-time 20 "$OSS/latest.json" -o "$TMP/latest.json" 2>/dev/null; then
  LATEST="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$TMP/latest.json" | head -1)"
fi
if [ "$OS" = "Darwin" ]; then
  LOCAL_CLI="$HOME/Applications/RedBeacon.app/Contents/MacOS/redbeacon-cli"
else
  LOCAL_CLI="$HOME/.local/share/redbeacon/RedBeacon/redbeacon-cli"
fi
CURRENT=""
if [ -x "$LOCAL_CLI" ]; then
  CURRENT="$("$LOCAL_CLI" --version 2>/dev/null | awk '{print $NF}' | head -1)"
fi
if [ -z "${REDBEACON_FORCE_INSTALL:-}" ] && [ -n "$LATEST" ] && [ "$CURRENT" = "$LATEST" ]; then
  if [ "$OS" = "Darwin" ]; then
    refresh_macos_app_registration "$HOME/Applications/RedBeacon.app"
  fi
  say "RedBeacon $CURRENT is already installed. Skipping bundle download."
  say "To reinstall anyway: curl -fsSL https://bytestaff.jiomig.com/install.sh | REDBEACON_FORCE_INSTALL=1 bash"
  exit 0
fi

# 3) download the bundle (OSS is fast in China; retry a few times)
say "[1/3] Downloading RedBeacon ($PLAT) ..."
ok=""
for t in 1 2 3; do
  if curl -fSL --connect-timeout 15 -o "$TMP/rb.zip" "$BUNDLE_URL"; then ok=1; break; fi
  warn "  download attempt $t failed, retrying..."; sleep 2
done
[ -n "$ok" ] || die "Could not download $BUNDLE_URL -- check your network and re-run."

# 4) extract + place + wire the `redbeacon` command
say "[2/3] Installing ..."
mkdir -p "$TMP/x"
unzip -q "$TMP/rb.zip" -d "$TMP/x" || die "unzip failed (corrupt download?)"
if [ "$OS" = "Darwin" ]; then
  APP="$HOME/Applications/RedBeacon.app"
  mkdir -p "$HOME/Applications"; rm -rf "$APP"
  mv "$TMP/x/RedBeacon.app" "$APP"
  xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true   # locally placed -> no Gatekeeper prompt
  ln -sf "$APP/Contents/MacOS/redbeacon-cli" "$BINDIR/redbeacon"
  refresh_macos_app_registration "$APP"
  OPEN_HINT="Launchpad / Spotlight -> RedBeacon (or ~/Applications/RedBeacon.app)"
else
  DEST="$HOME/.local/share/redbeacon"
  rm -rf "$DEST"; mkdir -p "$DEST"
  mv "$TMP/x/RedBeacon" "$DEST/RedBeacon"
  ln -sf "$DEST/RedBeacon/redbeacon-cli" "$BINDIR/redbeacon"
  ICON_PATH="$DEST/RedBeacon/_internal/assets/RedBeacon.png"
  [ -f "$ICON_PATH" ] || ICON_PATH="$DEST/RedBeacon/assets/RedBeacon.png"
  D="$HOME/.local/share/applications/redbeacon.desktop"; mkdir -p "$(dirname "$D")"
  cat > "$D" <<EOF
[Desktop Entry]
Type=Application
Name=RedBeacon
Comment=Xiaohongshu operations digital worker
Exec=$DEST/RedBeacon/RedBeacon
Icon=$ICON_PATH
Terminal=false
Categories=Office;Utility;
EOF
  chmod +x "$D" 2>/dev/null || true
  OPEN_HINT="your app menu -> RedBeacon"
fi

# 5) skills -> AI assistant command dir (from OSS; non-blocking)
say "[3/3] Fetching skills ..."
skok=""
for t in 1 2 3; do
  if curl -fsSL --max-time 90 "$OSS/skill/redbeacon-skill.tar.gz" | tar -xz -C "$TMP" 2>/dev/null; then skok=1; break; fi
done
if [ -n "$skok" ]; then
  SRC="$(find "$TMP" -type d -path '*/.claude/commands' | head -1)"
  mkdir -p "$SKILL_DEST"
  [ -n "$SRC" ] && cp -f "$SRC"/*.md "$SKILL_DEST"/ 2>/dev/null || true
  "$BINDIR/redbeacon" config set skill_install_dir "$SKILL_DEST" >/dev/null 2>&1 || true
else
  warn "  skills not fetched this time (UI/app unaffected); re-run this command later to add them."
fi

echo
say "RedBeacon installed."
echo "  - Double-click the app:  $OPEN_HINT"
echo "  - Or drive it via CLI:   redbeacon   (with an AI assistant: /redbeacon)"
case ":$PATH:" in
  *":$BINDIR:"*) ;;
  *) warn "Note: $BINDIR is not on your PATH yet. Add it (or reopen your terminal) to use the 'redbeacon' command."
     warn "  e.g.  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc" ;;
esac
echo "  (The browser engine downloads on first run -- give it a minute the first time.)"
