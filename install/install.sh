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
  RUNTIME_ROOT="$HOME/.redbeacon_test"
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
  RUNTIME_ROOT="$HOME/.redbeacon"
fi
BINDIR="$HOME/.local/bin"
RUNTIME_DATA_DIR="$RUNTIME_ROOT/data"
RUNTIME_PLAYWRIGHT_DIR="$RUNTIME_ROOT/browser/ms-playwright"
RUNTIME_CLOAK_DIR="$RUNTIME_ROOT/browser/cloakbrowser"

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

skill_matches_channel() {
  stem="$1"
  if [ "$CHANNEL" = "test" ]; then
    case "$stem" in redbeacon-test*) return 0 ;; *) return 1 ;; esac
  fi
  case "$stem" in redbeacon-test*) return 1 ;; redbeacon*) return 0 ;; *) return 1 ;; esac
}

install_codex_skills() {
  src="$1"
  [ -n "$src" ] && [ -d "$src" ] || return 0
  codex_dir="$HOME/.codex/skills"
  mkdir -p "$codex_dir" || return 1
  for f in "$src"/redbeacon*.md; do
    [ -f "$f" ] || continue
    stem="$(basename "$f" .md)"
    skill_matches_channel "$stem" || continue
    folder="$codex_dir/$stem"
    mkdir -p "$folder" || return 1
    desc="$(sed -n 's/^[[:space:]]*description:[[:space:]]*//p' "$f" | head -1)"
    desc="${desc#\"}"; desc="${desc%\"}"; desc="${desc#\'}"; desc="${desc%\'}"
    [ -n "$desc" ] || desc="RedBeacon ability: $stem"
    qdesc="$(yaml_quote "$desc")"
    skill_tmp="$folder/SKILL.md.new.$$"
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
    } > "$skill_tmp" || return 1
    mv -f "$skill_tmp" "$folder/SKILL.md" || return 1
  done
}

PREPARED_SKILL_SRC=""
SKILL_TRANSACTION_ACTIVE=""
SKILL_BACKUP_ROOT=""

remove_managed_skills() {
  for f in "$SKILL_DEST"/redbeacon*.md; do
    [ -f "$f" ] || continue
    stem="$(basename "$f" .md)"
    skill_matches_channel "$stem" || continue
    rm -f "$f" || return 1
  done
  codex_dir="$HOME/.codex/skills"
  for d in "$codex_dir"/redbeacon*; do
    [ -d "$d" ] || continue
    stem="$(basename "$d")"
    skill_matches_channel "$stem" || continue
    rm -rf "$d" || return 1
  done
}

begin_skill_transaction() {
  [ -z "$SKILL_TRANSACTION_ACTIVE" ] || return 0
  SKILL_BACKUP_ROOT="$TMP/skill-backup"
  rm -rf "$SKILL_BACKUP_ROOT"
  mkdir -p "$SKILL_BACKUP_ROOT/claude" "$SKILL_BACKUP_ROOT/codex" || return 1
  for f in "$SKILL_DEST"/redbeacon*.md; do
    [ -f "$f" ] || continue
    stem="$(basename "$f" .md)"
    skill_matches_channel "$stem" || continue
    cp -p "$f" "$SKILL_BACKUP_ROOT/claude/" || return 1
  done
  for d in "$HOME/.codex/skills"/redbeacon*; do
    [ -d "$d" ] || continue
    stem="$(basename "$d")"
    skill_matches_channel "$stem" || continue
    cp -R "$d" "$SKILL_BACKUP_ROOT/codex/" || return 1
  done
  SKILL_TRANSACTION_ACTIVE=1
}

restore_skills() {
  [ -n "$SKILL_TRANSACTION_ACTIVE" ] || return 0
  remove_managed_skills >/dev/null 2>&1 || true
  mkdir -p "$SKILL_DEST" "$HOME/.codex/skills" 2>/dev/null || true
  for f in "$SKILL_BACKUP_ROOT/claude"/*; do
    [ -f "$f" ] || continue
    cp -p "$f" "$SKILL_DEST/" 2>/dev/null || true
  done
  for d in "$SKILL_BACKUP_ROOT/codex"/*; do
    [ -d "$d" ] || continue
    cp -R "$d" "$HOME/.codex/skills/" 2>/dev/null || true
  done
  SKILL_TRANSACTION_ACTIVE=""
}

prepare_skills() {
  say "Preparing the matching skill bundle ..."
  skill_stage="$TMP/skill-stage"
  rm -rf "$skill_stage"; mkdir -p "$skill_stage"
  skok=""
  for t in 1 2 3; do
    rm -rf "$skill_stage"; mkdir -p "$skill_stage"
    if curl -fsSL --connect-timeout 10 --max-time 90 "$SKILL_URL" -o "$TMP/skill.tar.gz"; then
      if [ -n "$SKILL_SHA" ]; then
        skill_got="$(sha256_file "$TMP/skill.tar.gz" 2>/dev/null || true)"
        if [ "$skill_got" != "$SKILL_SHA" ]; then
          warn "  skill checksum mismatch, retrying..."
          continue
        fi
      fi
      if tar -xzf "$TMP/skill.tar.gz" -C "$skill_stage" 2>/dev/null; then
        skok=1; break
      fi
    fi
    warn "  skills fetch failed, retrying..."
  done
  [ -n "$skok" ] || die "Could not prepare the matching skill bundle. The existing installation was not changed."
  PREPARED_SKILL_SRC="$(find "$skill_stage" -type d -path '*/.claude/commands' | head -1)"
  [ -n "$PREPARED_SKILL_SRC" ] || die "Skill bundle is incomplete. The existing installation was not changed."
  find "$PREPARED_SKILL_SRC" -type f -name 'redbeacon*.md' | grep -q . \
    || die "Skill bundle contains no RedBeacon skills. The existing installation was not changed."
  if [ -n "$SKILL_VERSION" ]; then
    skill_meta="$(find "$skill_stage" -type f -name 'redbeacon-skill-manifest.json' | head -1)"
    [ -n "$skill_meta" ] || die "Skill bundle has no release metadata. The existing installation was not changed."
    meta_version="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$skill_meta" | head -1)"
    meta_channel="$(sed -n 's/.*"channel"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$skill_meta" | head -1)"
    [ "$meta_version" = "$SKILL_VERSION" ] && [ "$meta_channel" = "$CHANNEL" ] \
      || die "Skill bundle version/channel does not match the client manifest. The existing installation was not changed."
  fi
}

install_skills() {
  cli="$1"
  [ -n "$PREPARED_SKILL_SRC" ] && [ -d "$PREPARED_SKILL_SRC" ] \
    || die "Prepared skill bundle is unavailable."
  say "Installing the matching skills ..."
  begin_skill_transaction || die "Could not back up the existing skills."
  remove_managed_skills || die "Could not prepare the managed skill directories."
  mkdir -p "$SKILL_DEST" || die "Could not create the skill directory."
  cp -f "$PREPARED_SKILL_SRC"/redbeacon*.md "$SKILL_DEST"/ \
    || die "Could not install the matching skills."
  install_codex_skills "$PREPARED_SKILL_SRC" \
    || die "Could not install the matching Codex skills."
  for f in "$PREPARED_SKILL_SRC"/redbeacon*.md; do
    [ -f "$f" ] || continue
    stem="$(basename "$f" .md)"
    skill_matches_channel "$stem" || continue
    [ -f "$SKILL_DEST/$(basename "$f")" ] \
      || die "Claude-style skill verification failed: $stem"
    cmp -s "$f" "$SKILL_DEST/$(basename "$f")" \
      || die "Claude-style skill content verification failed: $stem"
    [ -f "$HOME/.codex/skills/$stem/SKILL.md" ] \
      || die "Codex skill verification failed: $stem"
  done
  "$cli" config set skill_install_dir "$SKILL_DEST" >/dev/null 2>&1 || true
}

run_browser_setup() {
  cli="$1"
  [ -n "$cli" ] && [ -x "$cli" ] || die "CLI executable not found for browser setup: $cli"
  if [ "${REDBEACON_SKIP_BROWSER_SETUP:-}" = "1" ] \
     && { [ "${CI:-}" = "true" ] || [ "${GITHUB_ACTIONS:-}" = "true" ]; }; then
    warn "  browser engine setup skipped by REDBEACON_SKIP_BROWSER_SETUP=1"
    return 0
  fi
  say "[3/4] Preparing browser engine (this can take a while on first install) ..."
  if REDBEACON_CHANNEL="$CHANNEL" \
     REDBEACON_DATA_DIR="$RUNTIME_DATA_DIR" \
     REDBEACON_PLAYWRIGHT_DIR="$RUNTIME_PLAYWRIGHT_DIR" \
     REDBEACON_CLOAKBROWSER_DIR="$RUNTIME_CLOAK_DIR" \
     PLAYWRIGHT_BROWSERS_PATH="$RUNTIME_PLAYWRIGHT_DIR" \
     CLOAKBROWSER_CACHE_DIR="$RUNTIME_CLOAK_DIR" \
     CLOAKBROWSER_BINARY_PATH= CLOAKBROWSER_VERSION= CLOAKBROWSER_SKIP_CHECKSUM= \
     REDBEACON_OUT=compact "$cli" setup; then
    say "Browser engine is ready."
  else
    die "Browser engine setup failed. Re-run the installer after checking network/proxy."
  fi
}

verify_bundle() {
  cli="$1"
  renderer="$2"
  expected_version="${3:-}"
  [ -x "$cli" ] || die "Bundle verification cannot start the CLI: $cli"
  [ -x "$renderer" ] || die "Bundle verification cannot start the card renderer: $renderer"
  verify_root="$TMP/bundle-verify-$(basename "$cli")"
  rm -rf "$verify_root"; mkdir -p "$verify_root/cards"

  version_text="$(REDBEACON_CHANNEL="$CHANNEL" REDBEACON_DATA_DIR="$RUNTIME_DATA_DIR" "$cli" --version 2>&1)" \
    || die "The new client failed its version check: $version_text"
  actual_version="$(printf '%s\n' "$version_text" | awk '{print $NF}' | head -1)"
  if [ -n "$expected_version" ] && [ "$actual_version" != "$expected_version" ]; then
    die "Downloaded client version $actual_version does not match manifest version $expected_version."
  fi

  desktop_smoke="$(REDBEACON_CHANNEL="$CHANNEL" \
    REDBEACON_DATA_DIR="$RUNTIME_DATA_DIR" \
    REDBEACON_PLAYWRIGHT_DIR="$RUNTIME_PLAYWRIGHT_DIR" \
    REDBEACON_CLOAKBROWSER_DIR="$RUNTIME_CLOAK_DIR" \
    REDBEACON_DESKTOP_SMOKE=1 "$cli" 2>&1)" \
    || die "The new client failed desktop initialization: $desktop_smoke"
  printf '%s\n' "$desktop_smoke" | grep -F 'RedBeacon desktop smoke ok' >/dev/null \
    || die "The new client did not reach the desktop-ready marker."

  printf '%s\n' '---' 'title: Install Verification' 'emoji: test' '---' '' \
    '# Runtime verification' '' 'This card verifies the packaged renderer and exact browser revision.' \
    > "$verify_root/note.md"
  REDBEACON_CHANNEL="$CHANNEL" \
    REDBEACON_DATA_DIR="$RUNTIME_DATA_DIR" \
    REDBEACON_PLAYWRIGHT_DIR="$RUNTIME_PLAYWRIGHT_DIR" \
    REDBEACON_CLOAKBROWSER_DIR="$RUNTIME_CLOAK_DIR" \
    PLAYWRIGHT_BROWSERS_PATH="$RUNTIME_PLAYWRIGHT_DIR" \
    "$renderer" "$verify_root/note.md" --output-dir "$verify_root/cards" --style default >/dev/null 2>&1 \
    || die "The new client failed its offline card-render verification."
  [ -s "$verify_root/cards/cover.png" ] \
    || die "The new renderer did not create a cover image."
  find "$verify_root/cards" -type f -name 'card_*.png' -size +0c | grep -q . \
    || die "The new renderer did not create a body card image."
  say "New client runtime verification passed."
}

verify_macos_bundle_entry() {
  app="$1"
  [ "$OS" = "Darwin" ] || return 0
  plist="$app/Contents/Info.plist"
  [ -f "$plist" ] || die "The macOS bundle is missing Contents/Info.plist."
  bundle_executable="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$plist" 2>/dev/null || true)"
  [ "$bundle_executable" = "$APP_NAME" ] \
    || die "The macOS icon points to $bundle_executable instead of $APP_NAME."
  [ -x "$app/Contents/MacOS/$bundle_executable" ] \
    || die "The macOS icon target is not executable: $bundle_executable."
}

stop_running_redbeacon() {
  [ "${REDBEACON_SKIP_PROCESS_STOP:-}" != "1" ] || return 0
  say "Stopping running $APP_NAME processes ..."
  pkill -x "$APP_NAME" >/dev/null 2>&1 || true
  pkill -x "$CLI_NAME" >/dev/null 2>&1 || true
  sleep 1
}

refresh_macos_app_registration() {
  app="$1"
  [ "$OS" = "Darwin" ] || return 0
  [ "${REDBEACON_SKIP_OS_REFRESH:-}" != "1" ] || return 0
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
LEGACY_BUNDLE_URL="$OSS/$APP_PREFIX/$APP_NAME-$PLAT.zip"
BUNDLE_URL="$LEGACY_BUNDLE_URL"  # fallback for manifests published before versioned packages

TMP="$(mktemp -d)"
FINAL_PATH=""
BACKUP_PATH=""
COMMITTED=""
HAD_EXISTING_APP=""
cleanup_install() {
  if [ -z "$COMMITTED" ] && [ -n "$FINAL_PATH" ]; then
    if [ -n "$BACKUP_PATH" ] && [ -e "$BACKUP_PATH" ]; then
      rm -rf "$FINAL_PATH" 2>/dev/null || true
      mv "$BACKUP_PATH" "$FINAL_PATH" 2>/dev/null || true
    else
      rm -rf "$FINAL_PATH" 2>/dev/null || true
    fi
    if [ -z "$HAD_EXISTING_APP" ]; then
      rm -f "$BINDIR/$CMD_NAME" 2>/dev/null || true
      if [ "$OS" = "Linux" ]; then
        rm -f "$HOME/.local/share/applications/$DESKTOP_ID.desktop" 2>/dev/null || true
      fi
    fi
    if [ "$OS" = "Darwin" ] && [ -e "$FINAL_PATH" ]; then
      refresh_macos_app_registration "$FINAL_PATH"
    fi
  fi
  if [ -z "$COMMITTED" ]; then restore_skills; fi
  rm -rf "$TMP" 2>/dev/null || true
}
trap cleanup_install EXIT
mkdir -p "$BINDIR"

# 2) Fast no-op for repeat installs: fetch only the tiny manifest, then skip the
# large bundle when the installed client is already current.
LATEST=""
SHA=""
SKILL_URL="$OSS/$SKILL_PREFIX/redbeacon-skill.tar.gz"
SKILL_SHA=""
SKILL_VERSION=""
HAS_VERSIONED_APP=""
if curl -fsSL --connect-timeout 8 --max-time 20 "$OSS/$MANIFEST_NAME" -o "$TMP/latest.json" 2>/dev/null; then
  LATEST="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$TMP/latest.json" | head -1)"
  SHA="$(sed -n 's/.*"'"$PLAT"'"[[:space:]]*:[[:space:]]*"\([0-9a-fA-F]\{64\}\)".*/\1/p' "$TMP/latest.json" | head -1 | tr 'A-F' 'a-f')"
  manifest_skill_url="$(sed -n 's/.*"skill_bundle_url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$TMP/latest.json" | head -1)"
  SKILL_SHA="$(sed -n 's/.*"skill_sha256"[[:space:]]*:[[:space:]]*"\([0-9a-fA-F]\{64\}\)".*/\1/p' "$TMP/latest.json" | head -1 | tr 'A-F' 'a-f')"
  SKILL_VERSION="$(sed -n 's/.*"skill_version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$TMP/latest.json" | head -1)"
  [ -z "$manifest_skill_url" ] || SKILL_URL="$manifest_skill_url"
  grep -q '"app"[[:space:]]*:' "$TMP/latest.json" && HAS_VERSIONED_APP=1 || true
fi
if [ -n "$LATEST" ] && [ -n "$HAS_VERSIONED_APP" ]; then
  BUNDLE_URL="$OSS/$APP_PREFIX/releases/$LATEST/$APP_NAME-$PLAT.zip"
fi
if [ "$OS" = "Darwin" ]; then
  LOCAL_CLI="$HOME/Applications/$APP_NAME.app/Contents/MacOS/$CLI_NAME"
  LOCAL_RENDERER="$HOME/Applications/$APP_NAME.app/Contents/MacOS/RedBeaconRenderer"
else
  LOCAL_CLI="$HOME/.local/share/$SHARE_NAME/$APP_NAME/$CLI_NAME"
  LOCAL_RENDERER="$HOME/.local/share/$SHARE_NAME/$APP_NAME/RedBeaconRenderer"
fi
CURRENT=""
if [ -x "$LOCAL_CLI" ]; then
  CURRENT="$("$LOCAL_CLI" --version 2>/dev/null | awk '{print $NF}' | head -1)"
fi
if [ -z "${REDBEACON_FORCE_INSTALL:-}" ] && [ -n "$LATEST" ] && [ "$CURRENT" = "$LATEST" ]; then
  prepare_skills
  if (run_browser_setup "$LOCAL_CLI" \
      && verify_bundle "$LOCAL_CLI" "$LOCAL_RENDERER" "$LATEST" \
      && verify_macos_bundle_entry "$HOME/Applications/$APP_NAME.app"); then
    say "$APP_NAME $CURRENT is already installed and healthy. Skipping bundle download."
    # A repeated install is also the repair path for missing/outdated skills.
    # Keep the large app zip skipped, but always refresh the small skill bundle.
    install_skills "$LOCAL_CLI"
    if [ "$OS" = "Darwin" ]; then
      refresh_macos_app_registration "$HOME/Applications/$APP_NAME.app"
    fi
    COMMITTED=1
    SKILL_TRANSACTION_ACTIVE=""
    rm -rf "$SKILL_BACKUP_ROOT" 2>/dev/null || true
    say "To reinstall anyway: curl -fsSL $OSS/install.sh | REDBEACON_CHANNEL=$CHANNEL REDBEACON_FORCE_INSTALL=1 bash"
    exit 0
  fi
  warn "The installed copy reports the latest version but failed health verification; downloading a clean bundle."
fi

# 3) download the bundle (OSS is fast in China; retry a few times)
say "[1/4] Downloading $APP_NAME ($PLAT) ..."
ok=""
for t in 1 2 3; do
  if curl -fSL --connect-timeout 15 --max-time 600 -o "$TMP/rb.zip" "$BUNDLE_URL"; then ok=1; break; fi
  warn "  download attempt $t failed, retrying..."; sleep 2
done
if [ -z "$ok" ] && [ "$BUNDLE_URL" != "$LEGACY_BUNDLE_URL" ]; then
  warn "  versioned package unavailable; trying the compatible package URL..."
  for t in 1 2 3; do
    if curl -fSL --connect-timeout 15 --max-time 600 -o "$TMP/rb.zip" "$LEGACY_BUNDLE_URL"; then ok=1; BUNDLE_URL="$LEGACY_BUNDLE_URL"; break; fi
    warn "  compatible download attempt $t failed, retrying..."; sleep 2
  done
fi
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

# Prepare every version-coupled runtime with the NEW CLI while the old client is
# still untouched. Old browser revisions and inherited system caches are never
# trusted. A failure here leaves the existing installation fully operational.
if [ "$OS" = "Darwin" ]; then
  STAGED_APP="$TMP/x/$APP_NAME.app"
  STAGED_CLI="$STAGED_APP/Contents/MacOS/$CLI_NAME"
  STAGED_RENDERER="$STAGED_APP/Contents/MacOS/RedBeaconRenderer"
  xattr -dr com.apple.quarantine "$STAGED_APP" 2>/dev/null || true
else
  STAGED_APP="$TMP/x/$APP_NAME"
  STAGED_CLI="$STAGED_APP/$CLI_NAME"
  STAGED_RENDERER="$STAGED_APP/RedBeaconRenderer"
fi
[ -d "$STAGED_APP" ] || die "Downloaded bundle does not contain $APP_NAME."
[ -x "$STAGED_CLI" ] || die "Downloaded bundle does not contain an executable $CLI_NAME."
verify_macos_bundle_entry "$STAGED_APP"
say "[2/4] Preparing and verifying new-version dependencies before replacement ..."
run_browser_setup "$STAGED_CLI"
verify_bundle "$STAGED_CLI" "$STAGED_RENDERER" "$LATEST"
prepare_skills
stop_running_redbeacon

if [ "$OS" = "Darwin" ]; then
  APP="$HOME/Applications/$APP_NAME.app"
  mkdir -p "$HOME/Applications"
  FINAL_PATH="$APP"
  BACKUP_PATH="$APP.redbeacon-rollback"
  rm -rf "$BACKUP_PATH"
  if [ -e "$APP" ]; then HAD_EXISTING_APP=1; mv "$APP" "$BACKUP_PATH" || die "Could not back up the existing client."; fi
  mv "$STAGED_APP" "$APP" || die "Could not place the new client."
  xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true   # locally placed -> no Gatekeeper prompt
  LOCAL_CLI="$APP/Contents/MacOS/$CLI_NAME"
  LOCAL_RENDERER="$APP/Contents/MacOS/RedBeaconRenderer"
  OPEN_HINT="Launchpad / Spotlight -> $APP_NAME (or ~/Applications/$APP_NAME.app)"
else
  DEST="$HOME/.local/share/$SHARE_NAME"
  APP="$DEST/$APP_NAME"
  mkdir -p "$DEST"
  FINAL_PATH="$APP"
  BACKUP_PATH="$APP.redbeacon-rollback"
  rm -rf "$BACKUP_PATH"
  if [ -e "$APP" ]; then HAD_EXISTING_APP=1; mv "$APP" "$BACKUP_PATH" || die "Could not back up the existing client."; fi
  mv "$STAGED_APP" "$APP" || die "Could not place the new client."
  LOCAL_CLI="$DEST/$APP_NAME/$CLI_NAME"
  LOCAL_RENDERER="$DEST/$APP_NAME/RedBeaconRenderer"
  OPEN_HINT="your app menu -> $APP_NAME"
fi

# 5) Browser engine -> required by QR login, publishing and card rendering.
# This second pass is normally instant; it verifies that the placed bundle sees
# exactly the same channel-owned runtimes prepared by the staged bundle.
run_browser_setup "$LOCAL_CLI"

# 6) skills -> AI assistant command dir (already downloaded and validated)
install_skills "$LOCAL_CLI"

# The final-path smoke happens after all version-coupled pieces are in place.
# Any failure still restores both the old app and the old skills.
verify_bundle "$LOCAL_CLI" "$LOCAL_RENDERER" "$LATEST"
verify_macos_bundle_entry "$FINAL_PATH"

# Launchers are switched last because they are the user's visible commit point.
if [ "$OS" = "Darwin" ]; then
  ln -sf "$LOCAL_CLI" "$BINDIR/$CMD_NAME" || die "Could not install the CLI launcher."
  refresh_macos_app_registration "$APP"
else
  ln -sf "$LOCAL_CLI" "$BINDIR/$CMD_NAME" || die "Could not install the CLI launcher."
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
fi

COMMITTED=1
SKILL_TRANSACTION_ACTIVE=""
rm -rf "$BACKUP_PATH" 2>/dev/null || true
rm -rf "$SKILL_BACKUP_ROOT" 2>/dev/null || true

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
