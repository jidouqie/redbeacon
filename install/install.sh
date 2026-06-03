#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# RedBeacon 一键安装（零环境也能跑）。由用户的个人 AI 助手执行：
#     curl -fsSL https://redbeacon.jiomig.com/install.sh | bash
#
# 干三件事：① 装 uv（自带 Python）② 装闭源 CLI（打包 wheel）+ 下浏览器内核
#          ③ 从 GitHub 拉开源 skill 拷进 AI 助手命令目录
# 全程幂等：再跑一次即升级。装好后也可对 AI 助手说"升级 RedBeacon"（跑 redbeacon update）。
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── 可配置项 ─────────────────────────────────────────────────────────────────
# 闭源 redbeacon 本体（打包 wheel）的获取地址。主源走 GitHub raw 的 PEP503 索引页，
# 用 --find-links 指向 index.html（靠相对链接定位 wheel）。依赖从 PyPI 拉。
# uv 会把此源记进 tool receipt，之后 `redbeacon update`（uv tool upgrade）自动复用。
# 备用源（将来提速可切阿里云 OSS）：https://redbeacon.oss-cn-shanghai.aliyuncs.com/simple/redbeacon/index.html
REDBEACON_FIND_LINKS="${REDBEACON_FIND_LINKS:-https://raw.githubusercontent.com/jidouqie/redbeacon/main/pip/simple/redbeacon/index.html}"
# 开源 skill 源（GitHub 主项目仓的 tarball）。
SKILL_TARBALL="${SKILL_TARBALL:-https://github.com/jidouqie/redbeacon/archive/refs/heads/main.tar.gz}"
# AI 助手命令目录（默认 Claude Code 用户级目录），可用环境变量覆盖。
SKILL_DEST="${REDBEACON_SKILL_DIR:-$HOME/.claude/commands}"

say() { printf '\033[36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!! %s\033[0m\n' "$*"; }
die() { printf '\033[31mxx %s\033[0m\n' "$*" >&2; exit 1; }

# ── 1. uv（带 Python，无需预装 Python）──────────────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
  say "[1/4] 安装 uv（自带 Python 运行时）"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  command -v uv >/dev/null 2>&1 || die "uv 安装后仍不在 PATH，请重开终端再试"
else
  say "[1/4] uv 已存在，跳过"
fi

# ── 2. 闭源 CLI（打包 wheel）+ 浏览器内核 ────────────────────────────────────
say "[2/4] 安装 / 升级 redbeacon CLI"
uv tool install --force --find-links "$REDBEACON_FIND_LINKS" redbeacon
export PATH="$HOME/.local/bin:$PATH"
command -v redbeacon >/dev/null 2>&1 || die "redbeacon 未上 PATH；请重开终端或检查 uv tool 路径"

say "[2/4] 下载浏览器内核（首次较慢，请耐心）"
redbeacon setup || warn "浏览器内核安装未完成，可稍后重跑 'redbeacon setup'"

# ── 3. 开源 skill → AI 助手命令目录 ─────────────────────────────────────────
say "[3/4] 拉取 skill 并安装到 $SKILL_DEST"
mkdir -p "$SKILL_DEST"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "$SKILL_TARBALL" | tar -xz -C "$TMP"
SRC="$(find "$TMP" -type d -path '*/.claude/commands' | head -1)"
[ -n "$SRC" ] || die "skill 包结构异常，找不到 .claude/commands"
cp -f "$SRC"/*.md "$SKILL_DEST"/

# 把 skill 目录写进 CLI 配置，供 `redbeacon update` 刷新用
redbeacon config set skill_install_dir "$SKILL_DEST" >/dev/null 2>&1 || true

# ── 4. 完成 ─────────────────────────────────────────────────────────────────
say "[4/4] 安装完成 🎉"
cat <<'EOF'

  RedBeacon 已就绪。回到你的 AI 助手，对它说：

      /redbeacon

  开始配置与使用。以后想升级，对 AI 助手说"升级 RedBeacon"即可
  （它会帮你跑 redbeacon update，CLI 和 skill 一起更新）。
EOF
