# Skill Bridge Map（双宿主稳定映射）

RedBeacon 的 skill 真源是 `.claude/commands/redbeacon*.md`（Claude Code 斜杠命令）。
Codex 端是从真源派生的 bridge：`~/.codex/skills/<codex-name>/SKILL.md`（文件夹式）。

**真源唯一**：长逻辑只维护在 `.claude/commands/`。Codex 端是生成物，改动请改真源后重新生成，不要直接编辑 `~/.codex/skills/redbeacon*`。

## 名称映射

| 真源文件（Claude，去 .md） | Claude 触发 | Codex skill 名 | 说明 |
|---|---|---|---|
| `redbeacon` | `/redbeacon` | `redbeacon` | 主入口 |
| `redbeacon-config` | `/redbeacon-config` | `redbeacon-config` | |
| `redbeacon-accounts` | `/redbeacon-accounts` | `redbeacon-accounts` | |
| `redbeacon-login` | `/redbeacon-login` | `redbeacon-login` | |
| `redbeacon-feishu` | `/redbeacon-feishu` | `redbeacon-feishu` | |
| `redbeacon-generate` | `/redbeacon-generate` | `redbeacon-generate` | |
| `redbeacon-publish` | `/redbeacon-publish` | `redbeacon-publish` | |
| `redbeacon-定位` | `/redbeacon-定位` | `redbeacon-locate` | 中文→ASCII 别名 |
| `redbeacon-策略` | `/redbeacon-策略` | `redbeacon-strategy` | 中文→ASCII 别名 |
| `redbeacon-诊断` | `/redbeacon-诊断` | `redbeacon-diagnose` | 中文→ASCII 别名 |
| `redbeacon-选题` | `/redbeacon-选题` | `redbeacon-topics` | 中文→ASCII 别名 |
| `redbeacon-面板` | `/redbeacon-面板` | `redbeacon-panel` | 中文→ASCII 别名 |

> 映射的唯一事实源是 CLI 里的 `cli/src/redbeacon/services/updater.py::_CODEX_NAME_MAP`，
> `redbeacon update`（用户机）和 `tools/sync-codex-skills.py`（开发态）都从它派生，保持一致。

## frontmatter 转换

| Claude（真源） | Codex（派生） |
|---|---|
| `description: ...` | `name: <codex-name>` + `description: ...`（原样） + `metadata.short-description` |
| `argument-hint: ...` | （Codex 不用，省略） |
| 正文 | **原样保留**（调 `redbeacon` CLI，harness 无关） |

## 两端怎么刷新

- **用户机**：`redbeacon update` → 刷 Claude `.claude/commands/` + （装了 Codex 则）派生刷 `~/.codex/skills/`。
- **开发态**：改完真源 markdown 后跑 `python tools/sync-codex-skills.py` 本地重生成 Codex 端。
