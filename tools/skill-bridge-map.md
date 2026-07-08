# Skill Bridge Map（双宿主一致）

RedBeacon 的 skill 真源是 `.claude/commands/redbeacon*.md`（Claude Code 斜杠命令）。
Codex 端是从真源派生的 bridge：`~/.codex/skills/<name>/SKILL.md`（文件夹式）。

**两端 skill 名已完全统一为英文**，不再有中英差异/别名。

**真源唯一**：长逻辑只维护在 `.claude/commands/`。Codex 端是生成物，改动请改真源后重新生成，不要直接编辑 `~/.codex/skills/redbeacon*`。

## skill 清单（两端同名）

| skill 名 | Claude 触发 | Codex | 说明 |
|---|---|---|---|
| `redbeacon` | `/redbeacon` | `redbeacon` | 主入口 |
| `redbeacon-config` | `/redbeacon-config` | 同名 | 配置 |
| `redbeacon-accounts` | `/redbeacon-accounts` | 同名 | 账号管理 |
| `redbeacon-login` | `/redbeacon-login` | 同名 | 扫码登录 |
| `redbeacon-feishu` | `/redbeacon-feishu` | 同名 | 绑飞书表 |
| `redbeacon-generate` | `/redbeacon-generate` | 同名 | 生成内容 |
| `redbeacon-publish` | `/redbeacon-publish` | 同名 | 发布 |
| `redbeacon-locate` | `/redbeacon-locate` | 同名 | 账号定位（原 定位）|
| `redbeacon-strategy` | `/redbeacon-strategy` | 同名 | 策略微调（原 策略）|
| `redbeacon-diagnose` | `/redbeacon-diagnose` | 同名 | 诊断（原 诊断）|
| `redbeacon-topics` | `/redbeacon-topics` | 同名 | 选题规划（原 选题）|
| `redbeacon-panel` | `/redbeacon-panel` | 同名 | 可视化面板（原 面板）|

> 历史：locate/strategy/diagnose/topics/panel 这 5 个原是中文名（定位/策略/诊断/选题/面板），
> 0.1.16 起两端统一为英文。命名映射的事实源是 `cli/src/redbeacon/services/updater.py::_CODEX_NAME_MAP`
> （现为空＝恒等；若将来再引入非 ASCII 名，在此加别名即可，正文交叉引用会自动重写）。

## frontmatter 转换

| Claude（真源） | Codex（派生） |
|---|---|
| `description: ...` | `name: <name>` + `description: ...`（原样） + `metadata.short-description` |
| `argument-hint: ...` | （Codex 不用，省略） |
| 正文 | **原样保留**（调 `redbeacon` CLI，harness 无关） |

## 两端怎么刷新

- **用户机**：`redbeacon update` → 全量更新 RedBeacon（客户端整包、CLI 兼容通道、Claude `.claude/commands/` + Codex 派生 skill），并清理改名后残留的旧 skill 孤儿。
- **开发态**：改完真源 markdown 后跑 `python tools/sync-codex-skills.py` 本地重生成 Codex 端。
