#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# RedBeacon installer (Mac/Linux). Run:
#     curl -fsSL https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install.sh | bash
#
# Installs a SELF-CONTAINED bundle (Python + all deps + Playwright driver already
# inside). No uv / no pip / no compiling -- just download + unzip + place.
# Gives you both:
#   - a double-click desktop app (RedBeacon)
#   - the `redbeacon` command (for an AI assistant to drive it)
# The browser engine (Chromium) is prepared during install via mirrors.
# All output is English on purpose (avoids garbled text on some consoles).
# ------------------------------------------------------------------------------
set -uo pipefail

OSS="${REDBEACON_OSS:-https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com}"
CHANNEL="${REDBEACON_CHANNEL:-stable}"
case "$CHANNEL" in test|testing|beta) CHANNEL="test" ;; *) CHANNEL="stable" ;; esac
if [ "$CHANNEL" = "test" ]; then
  APP_NAME="RedBeacon_test"
  CMD_NAME="redbeacon-test"
  CLI_NAME="redbeacon-test-cli"
  APP_PREFIX="app/test"
  MANIFEST_NAME="latest-test.json"
  SKILL_PREFIX="skill-test"
  SHARE_NAME="redbeacon-test"
  DESKTOP_ID="redbeacon-test"
  SKILL_DEST="${REDBEACON_SKILL_DIR:-$HOME/.claude/commands-redbeacon-test}"
else
  APP_NAME="RedBeacon"
  CMD_NAME="redbeacon"
  CLI_NAME="redbeacon-cli"
  APP_PREFIX="app"
  MANIFEST_NAME="latest.json"
  SKILL_PREFIX="skill"
  SHARE_NAME="redbeacon"
  DESKTOP_ID="redbeacon"
  SKILL_DEST="${REDBEACON_SKILL_DIR:-$HOME/.claude/commands}"
fi
BINDIR="$HOME/.local/bin"

say()  { printf '\033[36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!! %s\033[0m\n' "$*"; }
die()  { printf '\033[31mxx %s\033[0m\n' "$*" >&2; exit 1; }

sha256_file() {
  f="$1"
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$f" | awk '{print $1}'; return 0; fi
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$f" | awk '{print $1}'; return 0; fi
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$f" <<'PY'
import hashlib, sys
h = hashlib.sha256()
with open(sys.argv[1], "rb") as f:
    for chunk in iter(lambda: f.read(1024 * 1024), b""):
        h.update(chunk)
print(h.hexdigest())
PY
    return 0
  fi
  return 1
}

yaml_quote() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

install_codex_skills() {
  src="$1"
  [ -n "$src" ] && [ -d "$src" ] || return 0
  codex_dir="$HOME/.codex/skills"
  mkdir -p "$codex_dir" 2>/dev/null || return 0
  for f in "$src"/redbeacon*.md; do
    [ -f "$f" ] || continue
    stem="$(basename "$f" .md)"
    folder="$codex_dir/$stem"
    mkdir -p "$folder" 2>/dev/null || continue
    desc="$(sed -n 's/^[[:space:]]*description:[[:space:]]*//p' "$f" | head -1)"
    desc="${desc#\"}"; desc="${desc%\"}"; desc="${desc#\'}"; desc="${desc%\'}"
    [ -n "$desc" ] || desc="RedBeacon ability: $stem"
    qdesc="$(yaml_quote "$desc")"
    {
      printf '%s\n' "---"
      printf 'name: %s\n' "$stem"
      printf 'description: "%s"\n' "$qdesc"
      printf '%s\n' "metadata:"
      printf '  short-description: "%s"\n' "$qdesc"
      printf '%s\n\n' "---"
      awk '
        NR==1 && $0=="---" { front=1; next }
        front && $0=="---" { front=0; next }
        !front { print }
      ' "$f"
    } > "$folder/SKILL.md"
  done
}

run_browser_setup() {
  cli="$1"
  [ -n "$cli" ] && [ -x "$cli" ] || die "CLI executable not found for browser setup: $cli"
  if [ "${REDBEACON_SKIP_BROWSER_SETUP:-}" = "1" ]; then
    warn "  browser engine setup skipped by REDBEACON_SKIP_BROWSER_SETUP=1"
    return 0
  fi
  say "[3/4] Preparing browser engine (this can take a while on first install) ..."
  if REDBEACON_OUT=compact "$cli" setup; then
    say "Browser engine is ready."
  else
    die "Browser engine setup failed. Re-run the installer after checking network/proxy."
  fi
}

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
BUNDLE_URL="$OSS/$APP_PREFIX/$APP_NAME-$PLAT.zip"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$BINDIR"

# 2) Fast no-op for repeat installs: fetch only the tiny manifest, then skip the
# large bundle when the installed client is already current.
LATEST=""
SHA=""
if curl -fsSL --connect-timeout 8 --max-time 20 "$OSS/$MANIFEST_NAME" -o "$TMP/latest.json" 2>/dev/null; then
  LATEST="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$TMP/latest.json" | head -1)"
  SHA="$(sed -n 's/.*"'"$PLAT"'"[[:space:]]*:[[:space:]]*"\([0-9a-fA-F]\{64\}\)".*/\1/p' "$TMP/latest.json" | head -1 | tr 'A-F' 'a-f')"
fi
if [ "$OS" = "Darwin" ]; then
  LOCAL_CLI="$HOME/Applications/$APP_NAME.app/Contents/MacOS/$CLI_NAME"
else
  LOCAL_CLI="$HOME/.local/share/$SHARE_NAME/$APP_NAME/$CLI_NAME"
fi
CURRENT=""
if [ -x "$LOCAL_CLI" ]; then
  CURRENT="$("$LOCAL_CLI" --version 2>/dev/null | awk '{print $NF}' | head -1)"
fi
if [ -z "${REDBEACON_FORCE_INSTALL:-}" ] && [ -n "$LATEST" ] && [ "$CURRENT" = "$LATEST" ]; then
  if [ "$OS" = "Darwin" ]; then
    refresh_macos_app_registration "$HOME/Applications/$APP_NAME.app"
  fi
  say "$APP_NAME $CURRENT is already installed. Skipping bundle download."
  run_browser_setup "$LOCAL_CLI"
  say "To reinstall anyway: curl -fsSL $OSS/install.sh | REDBEACON_CHANNEL=$CHANNEL REDBEACON_FORCE_INSTALL=1 bash"
  exit 0
fi

# 3) download the bundle (OSS is fast in China; retry a few times)
say "[1/4] Downloading $APP_NAME ($PLAT) ..."
ok=""
for t in 1 2 3; do
  if curl -fSL --connect-timeout 15 -o "$TMP/rb.zip" "$BUNDLE_URL"; then ok=1; break; fi
  warn "  download attempt $t failed, retrying..."; sleep 2
done
[ -n "$ok" ] || die "Could not download $BUNDLE_URL -- check your network and re-run."
if [ -n "$SHA" ]; then
  GOT="$(sha256_file "$TMP/rb.zip" 2>/dev/null || true)"
  [ "$GOT" = "$SHA" ] || die "Package checksum mismatch. Please re-run later."
else
  warn "  package checksum missing in $MANIFEST_NAME; installing without checksum verification."
fi

# 4) extract + place + wire the `redbeacon` command
say "[2/4] Installing ..."
mkdir -p "$TMP/x"
unzip -q "$TMP/rb.zip" -d "$TMP/x" || die "unzip failed (corrupt download?)"
if [ "$OS" = "Darwin" ]; then
  APP="$HOME/Applications/$APP_NAME.app"
  mkdir -p "$HOME/Applications"; rm -rf "$APP"
  mv "$TMP/x/$APP_NAME.app" "$APP"
  xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true   # locally placed -> no Gatekeeper prompt
  ln -sf "$APP/Contents/MacOS/$CLI_NAME" "$BINDIR/$CMD_NAME"
  LOCAL_CLI="$APP/Contents/MacOS/$CLI_NAME"
  refresh_macos_app_registration "$APP"
  OPEN_HINT="Launchpad / Spotlight -> $APP_NAME (or ~/Applications/$APP_NAME.app)"
else
  DEST="$HOME/.local/share/$SHARE_NAME"
  rm -rf "$DEST"; mkdir -p "$DEST"
  mv "$TMP/x/$APP_NAME" "$DEST/$APP_NAME"
  ln -sf "$DEST/$APP_NAME/$CLI_NAME" "$BINDIR/$CMD_NAME"
  LOCAL_CLI="$DEST/$APP_NAME/$CLI_NAME"
  ICON_PATH="$DEST/$APP_NAME/_internal/assets/RedBeacon.png"
  [ -f "$ICON_PATH" ] || ICON_PATH="$DEST/$APP_NAME/assets/RedBeacon.png"
  D="$HOME/.local/share/applications/$DESKTOP_ID.desktop"; mkdir -p "$(dirname "$D")"
  cat > "$D" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Xiaohongshu operations digital worker
Exec=$DEST/$APP_NAME/$APP_NAME
Icon=$ICON_PATH
Terminal=false
Categories=Office;Utility;
EOF
  chmod +x "$D" 2>/dev/null || true
  OPEN_HINT="your app menu -> $APP_NAME"
fi

# 5) Browser engine -> required by QR login, publishing and card rendering.
run_browser_setup "$LOCAL_CLI"

# 6) skills -> AI assistant command dir (from OSS; non-blocking)
say "[4/4] Fetching skills ..."
skok=""
for t in 1 2 3; do
  if curl -fsSL --max-time 90 "$OSS/$SKILL_PREFIX/redbeacon-skill.tar.gz" | tar -xz -C "$TMP" 2>/dev/null; then skok=1; break; fi
done
if [ -n "$skok" ]; then
  SRC="$(find "$TMP" -type d -path '*/.claude/commands' | head -1)"
  mkdir -p "$SKILL_DEST"
  [ -n "$SRC" ] && cp -f "$SRC"/*.md "$SKILL_DEST"/ 2>/dev/null || true
  install_codex_skills "$SRC"
  "$BINDIR/$CMD_NAME" config set skill_install_dir "$SKILL_DEST" >/dev/null 2>&1 || true
else
  warn "  skills not fetched this time (UI/app unaffected); re-run this command later to add them."
fi

echo
say "$APP_NAME installed."
echo "  - Double-click the app:  $OPEN_HINT"
echo "  - Or drive it via CLI:   $CMD_NAME"
case ":$PATH:" in
  *":$BINDIR:"*) ;;
  *) warn "Note: $BINDIR is not on your PATH yet. Add it (or reopen your terminal) to use the '$CMD_NAME' command."
     warn "  e.g.  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc" ;;
esac
echo "  (The browser engine was prepared during install.)"
