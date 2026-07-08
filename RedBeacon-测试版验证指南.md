# RedBeacon 测试版验证指南

最后核对：2026-07-08

当前线上测试版：`0.1.55`
当前线上正式版：`0.1.53`

测试版是正式发布前的缓冲通道。它和正式版可以同时安装，互不覆盖，用来先排除安装、启动、更新、skill 隔离和 Windows 低级脚本错误。

发布纪律：

- **必须先发布测试版，等用户人工测试确认通过后，才允许发布正式版。**
- 测试版和正式版的客户端打包必须走同一个 GitHub Actions `Build desktop bundles`、同一个 PyInstaller spec、同一份代码；只能因为 channel 不同导致名字、命令、bundle id、数据目录、manifest、OSS 路径和 skill 名不同。
- 测试版发布后，只要改过客户端、CLI、skill、安装/更新/卸载脚本或发布脚本，之前的测试结论立刻作废，必须重新发测试版。不能拿“改过后的代码”直接发正式版。
- 正式版发布是“把已经测通过的测试版同一套代码切到 stable 通道再打一次包”，不是另起一套打包流程。
- 测试版 skill 必须安装到 Codex 真正扫描的 `~/.codex/skills/redbeacon-test*/SKILL.md`，不能再放到 `~/.codex/skills-redbeacon-test` 这类独立根目录。发布脚本和 Windows smoke 都会检查这一点。

## 测试版安装

macOS / Linux：

```bash
curl -fsSL https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install-test.sh | bash
```

Windows PowerShell：

```powershell
irm https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install-test.ps1 | iex
```

如果是从“运行窗口 / cmd / 平台按钮”触发，建议用留窗版命令，避免安装失败时一闪而过看不到错误：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -NoExit -Command "$env:REDBEACON_FORCE_INSTALL='1'; irm 'https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install-test.ps1' | iex"
```

如果本机已经装过同版本，安装脚本会只下载很小的 `latest-test.json` 做版本判断，然后跳过大包下载。要强制重新拉客户端包和测试版 skill，用：

```bash
curl -fsSL https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install-test.sh | REDBEACON_FORCE_INSTALL=1 bash
```

Windows PowerShell：

```powershell
$env:REDBEACON_FORCE_INSTALL=1; irm https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install-test.ps1 | iex
```

## 测试版更新与卸载

命令行更新：

```bash
redbeacon-test update
```

macOS / Linux 卸载：

```bash
curl -fsSL https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/uninstall-test.sh | bash
```

Windows PowerShell 卸载：

```powershell
irm https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/uninstall-test.ps1 | iex
```

默认卸载会保留测试数据。要连测试数据一起清理：

```bash
curl -fsSL https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/uninstall-test.sh | REDBEACON_PURGE=1 bash
```

Windows PowerShell：

```powershell
$env:REDBEACON_PURGE=1; irm https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/uninstall-test.ps1 | iex
```

## 直接下载路径

测试版 manifest：

```text
https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/latest-test.json
```

测试版客户端 zip：

```text
https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/app/test/RedBeacon_test-win-x64.zip
https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/app/test/RedBeacon_test-mac-arm64.zip
https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/app/test/RedBeacon_test-linux-x64.zip
```

测试版 skill：

```text
https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/skill-test/redbeacon-skill.tar.gz
https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/skill-test/commands/redbeacon-test.md
```

正式版对应路径：

```text
https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/latest.json
https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/app/RedBeacon-win-x64.zip
https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/app/RedBeacon-mac-arm64.zip
https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/app/RedBeacon-linux-x64.zip
```

## 隔离矩阵

| 项目 | 正式版 | 测试版 |
|---|---|---|
| 应用名 | `RedBeacon` | `RedBeacon_test` |
| 命令 | `redbeacon` | `redbeacon-test` |
| 打包内 CLI | `redbeacon-cli` | `redbeacon-test-cli` |
| 本机业务数据 | `~/.redbeacon` | `~/.redbeacon_test` |
| 平台 token | `~/.bytestaff` | `~/.bytestaff_test` |
| manifest | `latest.json` | `latest-test.json` |
| 客户端包 | `app/RedBeacon-*.zip` | `app/test/RedBeacon_test-*.zip` |
| skill 源 | `skill/` | `skill-test/` |
| 默认命令目录 | `~/.claude/commands` | `~/.claude/commands-redbeacon-test` |
| Codex 派生目录 | `~/.codex/skills/redbeacon*` | `~/.codex/skills/redbeacon-test*` |

## GitHub 冒烟覆盖

发布前的低级错误检查分两层：

- `cli/.github/workflows/build-bundle.yml`：三端 PyInstaller 打包。Windows runner 会解压真实 zip、检查 exe、跑 `--version`，并做桌面端最小启动冒烟；通过后才上传 OSS。
- `.github/workflows/windows-installer-smoke.yml`：用 Windows runner 解析 PowerShell 脚本，并用本地假 OSS 验证正式版 / 测试版安装卸载路径；同时检查测试版会生成 `~/.codex/skills/redbeacon-test/SKILL.md`，正式版和测试版 skill 可以共存，卸载测试版不会删正式版 skill。这个 workflow 需要已经存在于 GitHub 默认分支后，才能在分支上手动触发。
- `tools/release.sh` 会先运行 `tools/check_release_contracts.py`。如果安装脚本没有写 Codex 扫描目录，或测试版 skill 文件名不是 `redbeacon-test*`，发布会在上传 OSS 前直接中止。

这两层只保证“能下载、能解压、能启动到第一步、脚本没有低级语法错误”。完整业务功能仍需要人工在测试版客户端里测。

## 手动验收清单

1. 安装测试版，确认桌面 / 启动台里出现 `RedBeacon_test`。
2. 运行 `redbeacon-test --version`，确认版本是测试版 manifest 里的版本。
3. 打开客户端，确认第一屏不崩，不再出现 `main_entry` / logger 这类启动异常。
4. 确认正式版 `RedBeacon` 仍可独立存在，正式版数据没有被测试版读取或覆盖。
5. 在测试版里点更新，确认有进度、会关闭旧客户端并整包替换。
6. 再执行一次测试版安装命令，确认同版本会跳过大包下载。
7. 用 `REDBEACON_FORCE_INSTALL=1` 再装一次，确认测试版 skill 会被重新拉取。
8. 检查 `ls ~/.codex/skills/redbeacon-test*/SKILL.md | wc -l`，数量应和 `latest-test.json` 的 `skill_files` 一致；重启 Codex 或新开线程后能看到 `redbeacon-test`。
9. 卸载测试版，确认正式版应用、正式版命令、正式版数据和 `~/.codex/skills/redbeacon*/SKILL.md` 还在。

## 从测试版转正式版

测试通过后，再发布正式通道：

1. 等用户明确确认测试版通过。用户还在测试时，不发布正式版。
2. 确认没有在测试版发布后改过客户端、CLI、skill、安装/更新/卸载脚本或发布脚本；如改过，回到测试版重新发布和测试。
3. 确认 `cli/` 版本号、代码提交和测试通过的测试版一致。
4. 用同一个 GitHub Actions `Build desktop bundles` 触发 `channel=stable`，把 `RedBeacon-win-x64.zip`、`RedBeacon-mac-arm64.zip`、`RedBeacon-linux-x64.zip` 上传到 OSS `app/`。
5. 运行 `REDBEACON_STABLE_APPROVED=1 tools/release.sh "正式版更新说明"`。
6. 验证 `latest.json`、正式版安装脚本、正式版三端 zip、正式版 skill 都来自 OSS。
