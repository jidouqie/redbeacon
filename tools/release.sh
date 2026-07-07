#!/usr/bin/env bash
# RedBeacon 固定自动化发版（主源 = 阿里云 OSS bytestaff-redbeacon 桶，上海，公共读）。
#
#   打 wheel(cli/) → 传 OSS pip/simple/redbeacon/ → 重建 PEP503 index（含历史版本）
#   → 生成 latest.json 传 OSS。**全程不碰 git**（wheel/版本清单都在 OSS）。
#
# skill 是另一条通道：开源在 GitHub jidouqie/redbeacon，改了 .claude/commands 才 git push，
# 与本脚本解耦（客户端 `redbeacon update` 从 OSS 读版本、从 GitHub 刷 skill）。
#
# 前置：
#   1. 改 cli/src/redbeacon/__init__.py 的 __version__（版本单一源）。
#   2. 本机 ossutil 已配好 profile `redbeacon-release`（~/.ossutilconfig，chmod 600）。
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

VER="$(python3 -c "import re,pathlib;print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', pathlib.Path('cli/src/redbeacon/__init__.py').read_text()).group(1))")"
echo "==> 发版 v$VER → OSS $BUCKET"

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

# 4) 生成 latest.json（版本清单，skill_raw_base 仍指 GitHub）→ 上传 OSS
python3 tools/gen_latest.py --notes "$NOTES" >/dev/null
"$OU" cp latest.json "oss://${BUCKET}/latest.json" --profile "$PROFILE" -f >/dev/null
echo "  ✓ latest.json 上传（v${VER}）"

echo "==> v${VER} 已发布到 OSS。"
echo "   wheel 源 : ${BASE_URL}/${PREFIX}/index.html"
echo "   版本清单 : ${BASE_URL}/latest.json"
echo "   客户端：新装走 install.sh（find-links 指向上面 wheel 源）；老用户 redbeacon update / uv tool upgrade 即可升级。"
echo "   ⚠ 若本次也改了 skill（.claude/commands/*.md），记得 git push 到 GitHub main 让 skill 通道同步。"
