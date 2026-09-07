# Skill 通道模板契约

`.claude/commands/redbeacon*.md` 是唯一正文模板源，不能直接当发布字节分发。
`tools/build_channel_skills.py` 为 stable 和 test 分别渲染命令文件和标准 `SKILL.md`；Codex、OpenClaw、Hermes、WorkBuddy 消费同一份标准文件。

| 占位符 | 用途 |
| --- | --- |
| `{{CLI}}` | 当前通道 CLI 名称；斜杠命令写为 `/{{CLI}}-review` |
| `{{DATA_DIR}}` | 当前通道业务数据根目录 |
| `{{TOKEN_DIR}}` | 当前通道 ByteStaff 令牌目录 |
| `{{MANIFEST_URL}}` | 当前通道中央 canonical 清单 |
| `{{INSTALL_URL}}` | 官网固定安装入口，追加 `.ps1` 或 `.sh` |
| `{{INSTALL_PS1_KEY}}` / `{{INSTALL_SH_KEY}}` | 清单内当前通道安装脚本的精确条目名 |
| `{{APP_NAME}}` | 当前通道应用/包名称 |
| `{{COPY_CONTRACT}}` | 两通道共用的平台文案契约名，保持 `redbeacon_copy_v1` |

新增通道坐标必须使用表内变量。模板中的裸 CLI 名、数据路径或安装坐标、未知变量和未闭合变量都会使构建失败；产物还会检查另一通道的命令、路径及下载坐标。用户需要填写的单花括号示例以及嵌套 JSON 保持原样。

在仓库根目录运行 `python tools/build_channel_skills.py --channel test --out-dir <生成目录>` 生成测试版；正式版选择 `stable`。输出完整校验通过后才替换旧输出。`python tools/sync-codex-skills.py --workspace-only` 会先渲染 stable，再派生仓库工作台副本，不修改已安装的用户 skill。

仓库工作台副本继续入库，公开 CI 用 `python tools/sync-codex-skills.py --check` 逐字校验。该检查不依赖私有 CLI，且不会改写文件；取舍与回执保留规则见 [仓库产物规则](repository-artifact-policy.md)。

本契约不改变官网安装 URL、安装脚本或客户端 updater。
