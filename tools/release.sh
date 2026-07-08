#!/usr/bin/env bash
# RedBeacon 发布阶段脚本（对外分发源 = 阿里云 OSS bytestaff-redbeacon 桶，上海，公共读）。
#
# 固定流程：
#   1. 先在 cli/ 子仓库改版本、提交并推到 ci/bundle（或手动触发 GitHub Actions
#      "Build desktop bundles"）。GitHub Actions 只作为三端构建机，打 PyInstaller 客户端包：
#      app/RedBeacon-win-x64.zip、app/RedBeacon-mac-arm64.zip、app/RedBeacon-linux-x64.zip，
#      并上传到 OSS。
#   2. 等三端 job 全绿后，再运行本脚本：打 wheel(cli/) → 传 OSS pip/simple/redbeacon/
#      → 重建 PEP503 index（含历史版本）→ 生成 latest.json → 上传安装/卸载脚本和 skill。
#
# 注意：GitHub 不是发布源，不用 GitHub Release；GitHub Actions 只是构建和上传 OSS 的工具。
# skill 也发布到 OSS（tarball 给装机、散装 md 给升级），不走 GitHub raw。
#
# 前置：
#   1. 改 cli/src/redbeacon/__init__.py 的 __version__（版本单一源）。
#   2. GitHub Actions 三端客户端包已构建成功并上传 OSS app/。
#   3. 本机 ossutil 已配好 profile `redbeacon-release`（~/.ossutilconfig，chmod 600）。
# 用法：  tools/release.sh "本次更新说明（人话，给用户看）"
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
NOTES="${1:-}"

OU="${OSSUTIL:-$HOME/.local/bin/ossutil}"
PROFILE="${OSS_PROFILE:-redbeacon-release}"
BUCKET="${OSS_BUCKET:-bytestaff-redbeacon}"
PREFIX="pip/simple/redbeacon"
BASE_URL="https://${BUCKET}.oss-cn-shanghai.aliyuncs.com"

command -v "$OU" >/dev/null 2>&1 || { echo "xx 未找到 ossutil（$OU）；装它并配好 profile $PROFILE 后重试"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "xx 未找到 curl；需要用它检查 OSS 客户端包"; exit 1; }

VER="$(python3 -c "import re,pathlib;print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', pathlib.Path('cli/src/redbeacon/__init__.py').read_text()).group(1))")"
echo "==> 发版 v$VER → OSS $BUCKET"

# 0) 客户端包由 GitHub Actions 先打并上传。本脚本只做发布阶段，先确认三端包可公开访问。
for plat in win-x64 mac-arm64 linux-x64; do
  url="${BASE_URL}/app/RedBeacon-${plat}.zip"
  curl -fsSI "$url" >/dev/null || {
    echo "xx 找不到客户端包：$url"
    echo "   请先推 cli/ci/bundle 或手动触发 GitHub Actions「Build desktop bundles」，等三端上传 OSS 成功后再跑本脚本。"
    exit 1
  }
done
echo "  ✓ 客户端包已在 OSS app/ 就绪（GitHub Actions 负责构建上传）"

# 1) 打 wheel（从闭源 cli/ 源码，py3-none-any）
( cd cli && rm -rf dist && uv build >/dev/null )
WHL="cli/dist/redbeacon-${VER}-py3-none-any.whl"
[ -f "$WHL" ] || { echo "xx 找不到 $WHL（__version__ 与构建产物对不上？）"; exit 1; }

# 2) 上传 wheel（保留历史版本，便于 pin/回滚）
"$OU" cp "$WHL" "oss://${BUCKET}/${PREFIX}/" --profile "$PROFILE" -f >/dev/null
echo "  ✓ wheel 上传：$(basename "$WHL")"

# 3) 重建 PEP503 索引：列 OSS 上现有全部 wheel，生成 index.html 覆盖上传
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

# 4) 生成 latest.json（版本清单，skill_raw_base 指 OSS）→ 上传 OSS
python3 tools/gen_latest.py --notes "$NOTES" >/dev/null
"$OU" cp latest.json "oss://${BUCKET}/latest.json" --profile "$PROFILE" -f >/dev/null
echo "  ✓ latest.json 上传（v${VER}）"

# 5) 安装/卸载脚本上传 OSS：一键命令直指 OSS，不依赖官网/服务器（官网已废弃，介绍页并入平台）
"$OU" cp install/install.sh  "oss://${BUCKET}/install.sh"  --profile "$PROFILE" -f >/dev/null
"$OU" cp install/install.ps1 "oss://${BUCKET}/install.ps1" --profile "$PROFILE" -f >/dev/null
"$OU" cp install/uninstall.sh  "oss://${BUCKET}/uninstall.sh"  --profile "$PROFILE" -f >/dev/null
"$OU" cp install/uninstall.ps1 "oss://${BUCKET}/uninstall.ps1" --profile "$PROFILE" -f >/dev/null
echo "  ✓ 安装/卸载脚本上传（install.sh / install.ps1 / uninstall.sh / uninstall.ps1）"

# 6) skill → OSS（彻底不依赖 GitHub）：tarball 给装机(install.sh 解 .claude/commands/*.md)，
#    散装 md 给 redbeacon update（按 skill_raw_base/<文件名> 逐个拉，见 gen_latest RAW_BASE）。
SKILLTMP="$(mktemp -d)"
tar -czf "${SKILLTMP}/redbeacon-skill.tar.gz" .claude/commands/redbeacon*.md
"$OU" cp "${SKILLTMP}/redbeacon-skill.tar.gz" "oss://${BUCKET}/skill/redbeacon-skill.tar.gz" --profile "$PROFILE" -f >/dev/null
for f in .claude/commands/redbeacon*.md; do
  "$OU" cp "$f" "oss://${BUCKET}/skill/commands/$(basename "$f")" --profile "$PROFILE" -f >/dev/null
done
rm -rf "$SKILLTMP"
echo "  ✓ skill 上传（tarball + 散装 md，共 $(ls .claude/commands/redbeacon*.md | wc -l | tr -d ' ') 个命令）"

echo "==> v${VER} 已发布到 OSS。"
echo "   一键装(Mac/Linux): curl -fsSL ${BASE_URL}/install.sh | bash"
echo "   一键装(Windows)  : irm ${BASE_URL}/install.ps1 | iex"
echo "   一键卸载(Mac/Linux): curl -fsSL ${BASE_URL}/uninstall.sh | bash"
echo "   一键卸载(Windows)  : irm ${BASE_URL}/uninstall.ps1 | iex"
echo "   wheel 源 : ${BASE_URL}/${PREFIX}/index.html"
echo "   版本清单 : ${BASE_URL}/latest.json"
echo "   skill 源 : ${BASE_URL}/skill/（tarball + commands/ 散装 md）"
echo "   客户端包 : ${BASE_URL}/app/RedBeacon-{win-x64,mac-arm64,linux-x64}.zip"
echo "   客户端：新装走上面一键命令；老用户按 latest.json / wheel / skill 通道升级。GitHub Actions 只参与打包，不作为发布源。"
