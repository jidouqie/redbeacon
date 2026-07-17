# 封存的 skill（不分发、不可达）

这里放**暂时封存、不对用户公开**的 skill 真源。放在这个目录（而非 `.claude/commands/`）意味着：

- **Claude Code 不会把它当斜杠命令**（只扫 `.claude/commands/`）；
- **Codex 派生跳过它**（`tools/sync-codex-skills.py` 只 glob `.claude/commands/redbeacon*.md`）；
- **构建不收集**（不进入当前通道的 `skill/redbeacon-skill.tar.gz`）；现有装机下次全量安装或更新时会按新 Skill 包收敛本地文件。

即：用户在任何端都**调不到、看不到**这些 skill。文件保留仅供将来重启时拿回。

## 当前封存清单

- `redbeacon-feishu.md` —— 飞书多维表格绑定（2026-07 封存）。飞书云端数据源整体搁置、客户端默认纯本机；相关 CLI 命令（`feishu setup/test/perms`、`config test-feishu/feishu-users`）代码仍在，只是不通过任何 skill 暴露给用户。

## 重启某个 skill 的步骤

1. 把文件 `git mv` 回 `.claude/commands/`；
2. 把各 skill 里「飞书搁置/纯本机」的口径改回「随数据源」，onboarding 重新插入相关关卡；
3. 运行发布前测试和 `tools/build_desktop_local.sh --channel test`，确认它进入测试版 Skill 制品；
4. 只通过全局 `bytestaff-digital-employee-publish` Skill 发布测试版，用户验收后再走正式版。
