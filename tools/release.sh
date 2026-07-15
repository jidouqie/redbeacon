#!/usr/bin/env bash
# RedBeacon 发布阶段脚本（对外分发源 = 阿里云 OSS bytestaff-redbeacon 桶，上海，公共读）。
#
# 固定流程：
#   0. 永远先发 test 给用户测。用户明确确认通过前，不允许发 stable。
#      如果 test 发布后改过客户端/CLI/skill/安装更新卸载/发布脚本，必须重发 test。
#   1. 先在 cli/ 子仓库改版本、提交并推到 ci/bundle（或手动触发 GitHub Actions
#      "Build desktop bundles"）。GitHub Actions 只作为三端构建机，打 PyInstaller 客户端包：
#      stable: app/releases/<version>/RedBeacon-{win-x64,mac-arm64,linux-x64}.zip
#      test  : app/test/releases/<version>/RedBeacon_test-{win-x64,mac-arm64,linux-x64}.zip
#      并上传到 OSS。
#   2. 等三端 job 全绿后，再运行本脚本：
#      stable：打 wheel(cli/) → 传 OSS pip/simple/redbeacon/ → 重建 PEP503 index
#              → 生成 latest.json → 上传安装/卸载脚本和 skill。
#      test  ：跳过正式 wheel 源 → 生成 latest-test.json → 上传测试 skill 和测试安装入口。
#
# 注意：GitHub 不是发布源，不用 GitHub Release；GitHub Actions 只是构建和上传 OSS 的工具。
# skill 也发布到 OSS（tarball 给装机、散装 md 给升级），不走 GitHub raw。
# stable 和 test 的客户端打包流程必须完全一致：同一个 workflow、同一个 PyInstaller spec、
# 同一份代码；只允许 channel 改应用名/命令名/bundle id/数据目录/manifest/OSS 路径/skill 名。
#
# 前置：
#   1. 改 cli/src/redbeacon/__init__.py 的 __version__（版本单一源）。
#   2. GitHub Actions 三端客户端包已构建成功并上传 OSS app/ 或 app/test/。
#      Windows runner 会先做 bundle smoke：解压 zip、跑 --version、初始化桌面端；
#      Traceback / ModuleNotFoundError / ImportError 必须让 smoke 失败，过了才上传 OSS。
#   3. 根仓库 Windows installer smoke 已通过（解析 install/uninstall ps1，并用假 OSS 跑安装卸载）。
#   4. 本机 ossutil 已配好 profile `redbeacon-release`（~/.ossutilconfig，chmod 600）。
# 用法：
#   tools/release.sh --channel test "测试版更新说明"
#   REDBEACON_STABLE_APPROVED=1 tools/release.sh "正式版更新说明（仅用户确认测试版通过后）"
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

CHANNEL="${REDBEACON_CHANNEL:-stable}"
NOTES=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --channel)
      [ "$#" -ge 2 ] || { echo "xx --channel 需要 stable/test"; exit 1; }
      CHANNEL="$2"; shift 2 ;;
    --test)
      CHANNEL="test"; shift ;;
    *)
      if [ -z "$NOTES" ]; then NOTES="$1"; else NOTES="${NOTES} $1"; fi
      shift ;;
  esac
done
case "$CHANNEL" in test|testing|beta) CHANNEL="test" ;; stable|"") CHANNEL="stable" ;; *) echo "xx channel 只能是 stable/test"; exit 1 ;; esac
if [ "$CHANNEL" = "stable" ] && [ "${REDBEACON_STABLE_APPROVED:-}" != "1" ]; then
  echo "xx 正式版发布被保护：必须先发布测试版并由用户确认测试通过。"
  echo "   如果测试版发布后改过客户端/CLI/skill/安装更新卸载/发布脚本，请先重新发布测试版。"
  echo "   用户确认通过后再运行：REDBEACON_STABLE_APPROVED=1 tools/release.sh \"正式版更新说明\""
  exit 1
fi

OU="${OSSUTIL:-$HOME/.local/bin/ossutil}"
PROFILE="${OSS_PROFILE:-redbeacon-release}"
BUCKET="${OSS_BUCKET:-bytestaff-redbeacon}"
PREFIX="pip/simple/redbeacon"
BASE_URL="https://${BUCKET}.oss-cn-shanghai.aliyuncs.com"
if [ "$CHANNEL" = "test" ]; then
  APP_NAME="RedBeacon_test"
  APP_PREFIX="app/test"
  MANIFEST_NAME="latest-test.json"
  SKILL_PREFIX="skill-test"
else
  APP_NAME="RedBeacon"
  APP_PREFIX="app"
  MANIFEST_NAME="latest.json"
  SKILL_PREFIX="skill"
fi

# -1) 发布契约检查：防止安装/更新/卸载/skill 通道再次出现“测试版装了但
#     Codex 扫不到 redbeacon-test skill”这类流程漂移。这个检查只读本地文件，
#     失败时不上传任何内容到 OSS。
python3 tools/check_release_contracts.py

command -v "$OU" >/dev/null 2>&1 || { echo "xx 未找到 ossutil（$OU）；装它并配好 profile $PROFILE 后重试"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "xx 未找到 curl；需要用它检查 OSS 客户端包"; exit 1; }

# Browser packages are version-coupled to the locked Playwright/CloakBrowser
# dependencies. Probe the exact three-platform OSS objects with a real Range
# GET before any release upload, so a missing/slow-fallback-only runtime can
# never reach users.
( cd cli && uv run --frozen python ../tools/check_browser_mirrors.py )

VER="$(python3 -c "import re,pathlib;print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', pathlib.Path('cli/src/redbeacon/__init__.py').read_text()).group(1))")"
APP_BUILD_PREFIX="${APP_PREFIX}/releases/${VER}"
echo "==> 发版 v$VER [$CHANNEL] → OSS $BUCKET"

TMPAPP="$(mktemp -d)"
SKILLTMP=""
trap 'rm -rf "$TMPAPP"; [ -z "$SKILLTMP" ] || rm -rf "$SKILLTMP"' EXIT
APP_SHA_ARGS=()

# 0) 只有三端矩阵全部成功，workflow 的 mark-complete job 才会写此标记。
#    同时核对 commit，防止同一版本号反复构建时拼到旧平台包。
MARKER_URL="${BASE_URL}/${APP_BUILD_PREFIX}/build-complete.json"
MARKER_FILE="${TMPAPP}/build-complete.json"
curl -fsSL --connect-timeout 20 --max-time 60 --retry 3 "$MARKER_URL" -o "$MARKER_FILE" || {
  echo "xx 缺少三端构建完成标记：$MARKER_URL"
  echo "   必须等 GitHub Actions 的 Windows/macOS/Linux 和 mark-complete 全部通过。"
  exit 1
}
CURRENT_COMMIT="$(git -C cli rev-parse HEAD)"
python3 - "$MARKER_FILE" "$CHANNEL" "$VER" "$CURRENT_COMMIT" <<'PY'
import json, sys
path, channel, version, commit = sys.argv[1:]
marker = json.load(open(path, encoding="utf-8"))
expected = {"channel": channel, "version": version, "commit": commit}
actual = {key: str(marker.get(key, "")) for key in expected}
if actual != expected:
    raise SystemExit(f"xx 三端构建标记不匹配：expected={expected}, actual={actual}")
PY
echo "  ✓ 三端构建完成标记已核对：commit ${CURRENT_COMMIT}"

# 1) 客户端包由 GitHub Actions 先打并上传。本脚本只做发布阶段，确认三端包可公开访问，
#    并对 OSS 上的实际包计算 sha256 写进 latest.json，供安装/更新时校验。
for plat in win-x64 mac-arm64 linux-x64; do
  url="${BASE_URL}/${APP_BUILD_PREFIX}/${APP_NAME}-${plat}.zip"
  pkg="${TMPAPP}/${APP_NAME}-${plat}.zip"
  curl -fsSL --connect-timeout 20 --max-time 300 --retry 3 --retry-delay 2 --retry-connrefused "$url" -o "$pkg" || {
    echo "xx 找不到客户端包：$url"
    echo "   请先推 cli/ci/bundle 或手动触发 GitHub Actions「Build desktop bundles」，等三端上传 OSS 成功后再跑本脚本。"
    exit 1
  }
  sha="$(python3 - "$pkg" <<'PY'
import hashlib, sys
p = sys.argv[1]
h = hashlib.sha256()
with open(p, "rb") as f:
    for chunk in iter(lambda: f.read(1024 * 1024), b""):
        h.update(chunk)
print(h.hexdigest())
PY
)"
  APP_SHA_ARGS+=(--app-sha256 "${plat}=${sha}")
done
echo "  ✓ 客户端包已在 OSS ${APP_BUILD_PREFIX}/ 就绪，sha256 已计算（GitHub Actions 负责构建上传）"

# 2-4) 正式通道保留 wheel 兼容升级源；测试通道只走独立整包，避免污染正式 CLI 源。
if [ "$CHANNEL" = "stable" ]; then
  ( cd cli && rm -rf dist && uv build >/dev/null )
  WHL="cli/dist/redbeacon-${VER}-py3-none-any.whl"
  [ -f "$WHL" ] || { echo "xx 找不到 $WHL（__version__ 与构建产物对不上？）"; exit 1; }

  "$OU" cp "$WHL" "oss://${BUCKET}/${PREFIX}/" --profile "$PROFILE" -f >/dev/null
  echo "  ✓ wheel 上传：$(basename "$WHL")"

  TMPIDX="$(mktemp)"
  {
    echo '<!DOCTYPE html><html><head><meta name="pypi:repository-version" content="1.0"><title>Links for redbeacon</title></head><body><h1>Links for redbeacon</h1>'
    "$OU" ls "oss://${BUCKET}/${PREFIX}/" --profile "$PROFILE" 2>/dev/null \
      | grep -oE '[^/]+\.whl$' | sort -u \
      | while read -r w; do echo "<a href=\"$w\">$w</a><br/>"; done
    echo '</body></html>'
  } > "$TMPIDX"
  "$OU" cp "$TMPIDX" "oss://${BUCKET}/${PREFIX}/index.html" --profile "$PROFILE" -f >/dev/null
  rm -f "$TMPIDX"
  echo "  ✓ PEP503 索引已重建（含历史版本）"
else
  echo "  ✓ 测试通道跳过 wheel/PEP503（只发布独立整包 + 独立 skill + latest-test.json）"
fi

# 4) skill 也使用版本化不可变路径，并和客户端版本、channel、commit 绑定。
#    固定别名要等 manifest 切换后再更新，发布窗口内运行安装器的旧版本用户
#    仍会拿到旧 app + 旧 skill，不会出现跨版本混装。
SKILLTMP="$(mktemp -d)"
SKILL_RELEASE_PREFIX="${SKILL_PREFIX}/releases/${VER}"
python3 tools/build_channel_skills.py --channel "$CHANNEL" --out-dir "$SKILLTMP" >/dev/null
SKILL_COUNT="$(find "${SKILLTMP}/.claude/commands" -maxdepth 1 -name 'redbeacon*.md' | wc -l | tr -d ' ')"
python3 - "${SKILLTMP}/redbeacon-skill-manifest.json" "$CHANNEL" "$VER" "$CURRENT_COMMIT" <<'PY'
import json, pathlib, sys
path, channel, version, commit = sys.argv[1:]
files = sorted(p.name for p in (pathlib.Path(path).parent / ".claude" / "commands").glob("redbeacon*.md"))
pathlib.Path(path).write_text(json.dumps({
    "channel": channel,
    "version": version,
    "commit": commit,
    "skill_files": files,
}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
PY
tar -czf "${SKILLTMP}/redbeacon-skill.tar.gz" -C "$SKILLTMP" .claude/commands redbeacon-skill-manifest.json
SKILL_SHA="$(python3 - "${SKILLTMP}/redbeacon-skill.tar.gz" <<'PY'
import hashlib, sys
h = hashlib.sha256()
with open(sys.argv[1], "rb") as f:
    for chunk in iter(lambda: f.read(1024 * 1024), b""):
        h.update(chunk)
print(h.hexdigest())
PY
)"
"$OU" cp "${SKILLTMP}/redbeacon-skill.tar.gz" \
  "oss://${BUCKET}/${SKILL_RELEASE_PREFIX}/redbeacon-skill.tar.gz" --profile "$PROFILE" -f >/dev/null
for f in "${SKILLTMP}"/.claude/commands/redbeacon*.md; do
  "$OU" cp "$f" "oss://${BUCKET}/${SKILL_RELEASE_PREFIX}/commands/$(basename "$f")" --profile "$PROFILE" -f >/dev/null
done
echo "  ✓ 版本化 skill 已上传：${SKILL_RELEASE_PREFIX}/（sha256=${SKILL_SHA}）"

# 5) 生成清单；skill URL + SHA 与当前版本客户端一起成为安装事务真源。
python3 tools/gen_latest.py --channel "$CHANNEL" --notes "$NOTES" --out "$MANIFEST_NAME" \
  --skill-sha256 "$SKILL_SHA" "${APP_SHA_ARGS[@]}" >/dev/null

# 6) 安装/卸载脚本上传 OSS：一键命令直指 OSS，不依赖官网/服务器（官网已废弃，介绍页并入平台）
"$OU" cp install/install.sh  "oss://${BUCKET}/install.sh"  --profile "$PROFILE" -f >/dev/null
"$OU" cp install/install.ps1 "oss://${BUCKET}/install.ps1" --profile "$PROFILE" -f >/dev/null
"$OU" cp install/install-test.sh  "oss://${BUCKET}/install-test.sh"  --profile "$PROFILE" -f >/dev/null
"$OU" cp install/install-test.ps1 "oss://${BUCKET}/install-test.ps1" --profile "$PROFILE" -f >/dev/null
"$OU" cp install/uninstall.sh  "oss://${BUCKET}/uninstall.sh"  --profile "$PROFILE" -f >/dev/null
"$OU" cp install/uninstall.ps1 "oss://${BUCKET}/uninstall.ps1" --profile "$PROFILE" -f >/dev/null
"$OU" cp install/uninstall-test.sh  "oss://${BUCKET}/uninstall-test.sh"  --profile "$PROFILE" -f >/dev/null
"$OU" cp install/uninstall-test.ps1 "oss://${BUCKET}/uninstall-test.ps1" --profile "$PROFILE" -f >/dev/null
echo "  ✓ 安装/卸载脚本上传（正式 + 测试入口）"

# 7) 原子切换版本清单。安装/更新入口只在这一刻开始看到新版本。
"$OU" cp "$MANIFEST_NAME" "oss://${BUCKET}/${MANIFEST_NAME}" --profile "$PROFILE" -f >/dev/null
echo "  ✓ ${MANIFEST_NAME} 最后上传，正式切换到 v${VER}"

# 8) manifest 切换后再更新 app/skill 固定别名，仅供旧入口兼容。当前安装器
#    始终使用 manifest 中带版本号和 SHA 的不可变路径。
for plat in win-x64 mac-arm64 linux-x64; do
  "$OU" cp \
    "oss://${BUCKET}/${APP_BUILD_PREFIX}/${APP_NAME}-${plat}.zip" \
    "oss://${BUCKET}/${APP_PREFIX}/${APP_NAME}-${plat}.zip" \
    --profile "$PROFILE" -f >/dev/null
done
echo "  ✓ 固定客户端直链已更新（安装器仍使用版本化包）"
"$OU" cp \
  "oss://${BUCKET}/${SKILL_RELEASE_PREFIX}/redbeacon-skill.tar.gz" \
  "oss://${BUCKET}/${SKILL_PREFIX}/redbeacon-skill.tar.gz" --profile "$PROFILE" -f >/dev/null
for f in "${SKILLTMP}"/.claude/commands/redbeacon*.md; do
  "$OU" cp \
    "oss://${BUCKET}/${SKILL_RELEASE_PREFIX}/commands/$(basename "$f")" \
    "oss://${BUCKET}/${SKILL_PREFIX}/commands/$(basename "$f")" --profile "$PROFILE" -f >/dev/null
done
if [ "$CHANNEL" = "test" ]; then
  for f in .claude/commands/redbeacon*.md; do
    "$OU" rm "oss://${BUCKET}/${SKILL_PREFIX}/commands/$(basename "$f")" --profile "$PROFILE" -f >/dev/null 2>&1 || true
  done
fi
echo "  ✓ 固定 skill 兼容别名已更新（安装器仍使用版本化 skill）"

# 9) 从用户实际访问的公网入口反向读取一次。上传命令成功不代表对象路径、
#    文件名和最终清单一定一致；这里把缺包、命名漂移和半发布状态挡在发布端。
PUBLISHED_MANIFEST="${TMPAPP}/published-${MANIFEST_NAME}"
curl -fsSL --connect-timeout 10 --max-time 30 --retry 3 \
  "${BASE_URL}/${MANIFEST_NAME}" -o "$PUBLISHED_MANIFEST"
cmp -s "$MANIFEST_NAME" "$PUBLISHED_MANIFEST" || {
  echo "xx 公网 ${MANIFEST_NAME} 与本地发布清单不一致"
  exit 1
}

PUBLISHED_SKILLS="${TMPAPP}/redbeacon-skill.tar.gz"
curl -fsSL --connect-timeout 10 --max-time 90 --retry 3 \
  "${BASE_URL}/${SKILL_RELEASE_PREFIX}/redbeacon-skill.tar.gz" -o "$PUBLISHED_SKILLS"
PUBLISHED_SKILL_SHA="$(python3 - "$PUBLISHED_SKILLS" <<'PY'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)"
[ "$PUBLISHED_SKILL_SHA" = "$SKILL_SHA" ] || {
  echo "xx 公网版本化 skill 哈希不一致"
  exit 1
}
PUBLISHED_SKILL_COUNT="$(tar -tzf "$PUBLISHED_SKILLS" | grep -cE '/redbeacon[^/]*\.md$' | tr -d ' ')"
[ "$PUBLISHED_SKILL_COUNT" = "$SKILL_COUNT" ] || {
  echo "xx 公网 skill tarball 数量不对：expected=${SKILL_COUNT}, actual=${PUBLISHED_SKILL_COUNT}"
  exit 1
}

python3 - "$PUBLISHED_MANIFEST" <<'PY' | while IFS= read -r skill_file; do
import json, sys
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
for name in manifest.get("skill_files", []):
    print(name)
PY
  curl -fsSI --connect-timeout 10 --max-time 30 --retry 3 \
    "${BASE_URL}/${SKILL_RELEASE_PREFIX}/commands/${skill_file}" >/dev/null
  curl -fsSI --connect-timeout 10 --max-time 30 --retry 3 \
    "${BASE_URL}/${SKILL_PREFIX}/commands/${skill_file}" >/dev/null
done

for plat in win-x64 mac-arm64 linux-x64; do
  curl -fsSI --connect-timeout 10 --max-time 30 --retry 3 \
    "${BASE_URL}/${APP_BUILD_PREFIX}/${APP_NAME}-${plat}.zip" >/dev/null
  curl -fsSI --connect-timeout 10 --max-time 30 --retry 3 \
    "${BASE_URL}/${APP_PREFIX}/${APP_NAME}-${plat}.zip" >/dev/null
done
rm -rf "$SKILLTMP"
echo "  ✓ 公网发布结果已验证（manifest / 三端包 / 版本化 skill 哈希 + ${SKILL_COUNT} 个命令）"

echo "==> v${VER} [$CHANNEL] 已发布到 OSS。"
if [ "$CHANNEL" = "test" ]; then
  echo "   测试一键装(Mac/Linux): curl -fsSL ${BASE_URL}/install-test.sh | bash"
  echo "   测试一键装(Windows)  : irm ${BASE_URL}/install-test.ps1 | iex"
  echo "   测试一键卸载(Mac/Linux): curl -fsSL ${BASE_URL}/uninstall-test.sh | bash"
  echo "   测试一键卸载(Windows)  : irm ${BASE_URL}/uninstall-test.ps1 | iex"
else
  echo "   一键装(Mac/Linux): curl -fsSL ${BASE_URL}/install.sh | bash"
  echo "   一键装(Windows)  : irm ${BASE_URL}/install.ps1 | iex"
  echo "   一键卸载(Mac/Linux): curl -fsSL ${BASE_URL}/uninstall.sh | bash"
  echo "   一键卸载(Windows)  : irm ${BASE_URL}/uninstall.ps1 | iex"
  echo "   wheel 源 : ${BASE_URL}/${PREFIX}/index.html"
fi
echo "   版本清单 : ${BASE_URL}/${MANIFEST_NAME}"
echo "   skill 真源 : ${BASE_URL}/${SKILL_RELEASE_PREFIX}/（版本化 tarball + commands/）"
echo "   客户端包 : ${BASE_URL}/${APP_PREFIX}/${APP_NAME}-{win-x64,mac-arm64,linux-x64}.zip"
if [ "$CHANNEL" = "test" ]; then
  echo "   客户端：测试版新装和更新都只看 latest-test.json / app/test / skill-test，不影响正式用户。GitHub Actions 只参与打包，不作为发布源。"
else
  echo "   客户端：新装走上面一键命令；老用户按 latest.json / wheel / skill 通道升级。GitHub Actions 只参与打包，不作为发布源。"
fi
