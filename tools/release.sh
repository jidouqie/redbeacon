#!/usr/bin/env bash
# RedBeacon 发布阶段脚本（对外分发源 = 阿里云 OSS bytestaff-redbeacon 桶，上海，公共读）。
#
# 固定流程：
#   1. 先在 cli/ 子仓库改版本、提交并推到 ci/bundle（或手动触发 GitHub Actions
#      "Build desktop bundles"）。GitHub Actions 只作为三端构建机，打 PyInstaller 客户端包：
#      stable: app/RedBeacon-win-x64.zip、app/RedBeacon-mac-arm64.zip、app/RedBeacon-linux-x64.zip
#      test  : app/test/RedBeacon_test-win-x64.zip、app/test/RedBeacon_test-mac-arm64.zip ...
#      并上传到 OSS。
#   2. 等三端 job 全绿后，再运行本脚本：
#      stable：打 wheel(cli/) → 传 OSS pip/simple/redbeacon/ → 重建 PEP503 index
#              → 生成 latest.json → 上传安装/卸载脚本和 skill。
#      test  ：跳过正式 wheel 源 → 生成 latest-test.json → 上传测试 skill 和测试安装入口。
#
# 注意：GitHub 不是发布源，不用 GitHub Release；GitHub Actions 只是构建和上传 OSS 的工具。
# skill 也发布到 OSS（tarball 给装机、散装 md 给升级），不走 GitHub raw。
#
# 前置：
#   1. 改 cli/src/redbeacon/__init__.py 的 __version__（版本单一源）。
#   2. GitHub Actions 三端客户端包已构建成功并上传 OSS app/ 或 app/test/。
#      Windows runner 会先做 bundle smoke：解压 zip、跑 --version、初始化桌面端，过了才上传 OSS。
#   3. 根仓库 Windows installer smoke 已通过（解析 install/uninstall ps1，并用假 OSS 跑安装卸载）。
#   4. 本机 ossutil 已配好 profile `redbeacon-release`（~/.ossutilconfig，chmod 600）。
# 用法：
#   tools/release.sh "本次更新说明（人话，给用户看）"
#   tools/release.sh --channel test "测试版更新说明"
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

command -v "$OU" >/dev/null 2>&1 || { echo "xx 未找到 ossutil（$OU）；装它并配好 profile $PROFILE 后重试"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "xx 未找到 curl；需要用它检查 OSS 客户端包"; exit 1; }

VER="$(python3 -c "import re,pathlib;print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', pathlib.Path('cli/src/redbeacon/__init__.py').read_text()).group(1))")"
echo "==> 发版 v$VER [$CHANNEL] → OSS $BUCKET"

TMPAPP="$(mktemp -d)"
trap 'rm -rf "$TMPAPP"' EXIT
APP_SHA_ARGS=()

# 0) 客户端包由 GitHub Actions 先打并上传。本脚本只做发布阶段，确认三端包可公开访问，
#    并对 OSS 上的实际包计算 sha256 写进 latest.json，供安装/更新时校验。
for plat in win-x64 mac-arm64 linux-x64; do
  url="${BASE_URL}/${APP_PREFIX}/${APP_NAME}-${plat}.zip"
  pkg="${TMPAPP}/${APP_NAME}-${plat}.zip"
  curl -fsSL "$url" -o "$pkg" || {
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
echo "  ✓ 客户端包已在 OSS ${APP_PREFIX}/ 就绪，sha256 已计算（GitHub Actions 负责构建上传）"

# 1-3) 正式通道保留 wheel 兼容升级源；测试通道只走独立整包，避免污染正式 CLI 源。
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

# 4) 生成版本清单（skill_raw_base 指 OSS）→ 上传 OSS
python3 tools/gen_latest.py --channel "$CHANNEL" --notes "$NOTES" --out "$MANIFEST_NAME" "${APP_SHA_ARGS[@]}" >/dev/null
"$OU" cp "$MANIFEST_NAME" "oss://${BUCKET}/${MANIFEST_NAME}" --profile "$PROFILE" -f >/dev/null
echo "  ✓ ${MANIFEST_NAME} 上传（v${VER}）"

# 5) 安装/卸载脚本上传 OSS：一键命令直指 OSS，不依赖官网/服务器（官网已废弃，介绍页并入平台）
"$OU" cp install/install.sh  "oss://${BUCKET}/install.sh"  --profile "$PROFILE" -f >/dev/null
"$OU" cp install/install.ps1 "oss://${BUCKET}/install.ps1" --profile "$PROFILE" -f >/dev/null
"$OU" cp install/install-test.sh  "oss://${BUCKET}/install-test.sh"  --profile "$PROFILE" -f >/dev/null
"$OU" cp install/install-test.ps1 "oss://${BUCKET}/install-test.ps1" --profile "$PROFILE" -f >/dev/null
"$OU" cp install/uninstall.sh  "oss://${BUCKET}/uninstall.sh"  --profile "$PROFILE" -f >/dev/null
"$OU" cp install/uninstall.ps1 "oss://${BUCKET}/uninstall.ps1" --profile "$PROFILE" -f >/dev/null
"$OU" cp install/uninstall-test.sh  "oss://${BUCKET}/uninstall-test.sh"  --profile "$PROFILE" -f >/dev/null
"$OU" cp install/uninstall-test.ps1 "oss://${BUCKET}/uninstall-test.ps1" --profile "$PROFILE" -f >/dev/null
echo "  ✓ 安装/卸载脚本上传（正式 + 测试入口）"

# 6) skill → OSS（彻底不依赖 GitHub）：tarball 给装机(install.sh 解 .claude/commands/*.md)，
#    散装 md 给 update（按 skill_raw_base/<文件名> 逐个拉）。测试版会自动生成
#    redbeacon-test*.md，正文也调用 redbeacon-test，避免误驱动正式版。
SKILLTMP="$(mktemp -d)"
python3 tools/build_channel_skills.py --channel "$CHANNEL" --out-dir "$SKILLTMP" >/dev/null
SKILL_COUNT="$(find "${SKILLTMP}/.claude/commands" -maxdepth 1 -name 'redbeacon*.md' | wc -l | tr -d ' ')"
tar -czf "${SKILLTMP}/redbeacon-skill.tar.gz" -C "$SKILLTMP" .claude/commands
"$OU" cp "${SKILLTMP}/redbeacon-skill.tar.gz" "oss://${BUCKET}/${SKILL_PREFIX}/redbeacon-skill.tar.gz" --profile "$PROFILE" -f >/dev/null
for f in "${SKILLTMP}"/.claude/commands/redbeacon*.md; do
  "$OU" cp "$f" "oss://${BUCKET}/${SKILL_PREFIX}/commands/$(basename "$f")" --profile "$PROFILE" -f >/dev/null
done
if [ "$CHANNEL" = "test" ]; then
  # 清掉早期测试通道里误传的正式 skill 文件名；manifest 只保留 redbeacon-test*.md。
  for f in .claude/commands/redbeacon*.md; do
    "$OU" rm "oss://${BUCKET}/${SKILL_PREFIX}/commands/$(basename "$f")" --profile "$PROFILE" -f >/dev/null 2>&1 || true
  done
fi
rm -rf "$SKILLTMP"
echo "  ✓ skill 上传到 ${SKILL_PREFIX}/（tarball + 散装 md，共 ${SKILL_COUNT} 个命令）"

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
echo "   skill 源 : ${BASE_URL}/${SKILL_PREFIX}/（tarball + commands/ 散装 md）"
echo "   客户端包 : ${BASE_URL}/${APP_PREFIX}/${APP_NAME}-{win-x64,mac-arm64,linux-x64}.zip"
if [ "$CHANNEL" = "test" ]; then
  echo "   客户端：测试版新装和更新都只看 latest-test.json / app/test / skill-test，不影响正式用户。GitHub Actions 只参与打包，不作为发布源。"
else
  echo "   客户端：新装走上面一键命令；老用户按 latest.json / wheel / skill 通道升级。GitHub Actions 只参与打包，不作为发布源。"
fi
