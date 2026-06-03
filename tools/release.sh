#!/usr/bin/env bash
# 一键发版（纯 git push，不碰官网/OSS）：
#   打 wheel → 更新 pip/ 索引 → 生成 latest.json → commit & push。
#
# 发版前：改 cli/src/redbeacon/__init__.py 的 __version__（版本单一源）。
# 用法：    tools/release.sh "本次更新说明"
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
NOTES="${1:-}"

VER="$(python -c "import re,pathlib;print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', pathlib.Path('cli/src/redbeacon/__init__.py').read_text()).group(1))")"
echo "==> 发版 v$VER"

# 1) 打 wheel（从闭源 cli/ 源码）
( cd cli && rm -rf dist && uv build >/dev/null )
WHL="cli/dist/redbeacon-${VER}-py3-none-any.whl"
[ -f "$WHL" ] || { echo "xx 找不到 $WHL（__version__ 与构建产物对不上？）"; exit 1; }

# 2) 更新仓内 PEP503 索引（只留最新一版 wheel，保持仓库精简）
OUT="pip/simple/redbeacon"
mkdir -p "$OUT"; rm -f "$OUT"/*.whl
cp "$WHL" "$OUT/"
SHA="$(shasum -a 256 "$WHL" | awk '{print $1}')"
cat > "$OUT/index.html" <<EOF
<!DOCTYPE html>
<html><head><meta name="pypi:repository-version" content="1.0"><title>Links for redbeacon</title></head>
<body><h1>Links for redbeacon</h1>
<a href="redbeacon-${VER}-py3-none-any.whl#sha256=${SHA}">redbeacon-${VER}-py3-none-any.whl</a><br/>
</body></html>
EOF

# 3) 生成版本清单
python tools/gen_latest.py --notes "$NOTES" >/dev/null

# 4) 提交并推送（GitHub raw 是主源，约几分钟 CDN 生效）
git add -A
git commit -q -m "release: v${VER}${NOTES:+ — ${NOTES}}"
git push origin main
echo "==> v$VER 已发布并推送。用户下次 redbeacon update 即可升到此版（raw 缓存数分钟生效）。"
