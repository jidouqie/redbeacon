# RedBeacon 测试版验证指南

测试版和正式版可以同时安装，应用名、命令、数据、平台令牌、浏览器缓存和 skill 都互相隔离。用户始终使用官网固定入口；线上实际版本只以中央 canonical manifest 为准：

- 测试版：`https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com/projects/redbeacon/test/latest.json`
- 正式版：`https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com/projects/redbeacon/stable/latest.json`

## 安装测试版

macOS：

```bash
curl -fsSL https://bytestaff.jiomig.com/redbeacon-test/install.sh | bash
```

Windows PowerShell：

```powershell
irm https://bytestaff.jiomig.com/redbeacon-test/install.ps1 | iex
```

已经安装同版本时，脚本会先验证本地客户端、浏览器依赖和 skill；全部健康则跳过客户端大包。强制重装时先设置 `REDBEACON_FORCE_INSTALL=1`。

## 卸载测试版

macOS：

```bash
curl -fsSL https://bytestaff.jiomig.com/redbeacon-test/uninstall.sh | bash
```

Windows PowerShell：

```powershell
irm https://bytestaff.jiomig.com/redbeacon-test/uninstall.ps1 | iex
```

默认只卸载程序、命令和测试版 skill，保留 `~/.redbeacon_test` 业务数据。只有明确设置 `REDBEACON_PURGE=1` 才删除测试版数据和登录令牌。

## 发布前验收

1. Mac 和 Windows 安装后都能从图标打开，重复点图标只唤醒已有窗口。
2. `redbeacon-test --version` 与 test manifest 的 `version` 一致。
3. Claude Code、Codex、OpenClaw、Hermes、WorkBuddy 都能识别 `redbeacon-test` 及其子 skill，正式版 skill 没有被覆盖；WorkBuddy 新建任务或重启后刷新技能列表。
4. 新建一个测试账号，完成平台登录、小红书扫码、文案和图片生成、审稿、立即/定时发布。
5. 从旧版更新后，账号、定位、方案、选题、审稿和登录态保留；更新前快照存在。
6. 断开下载节点后重新安装，应自动回落中央 OSS；节点返回错误内容时也必须校验失败并回落。
7. 卸载测试版不影响正式版，不带 `PURGE` 时重装后数据仍在。

## 发布纪律

项目只运行 `tools/build_desktop_local.sh --channel test` 生成已测试的 `release-artifacts/`。OSS 上传、下载节点准备、canonical manifest 切换、回滚和公网验证全部由全局 `bytestaff-digital-employee-publish` Skill 负责。

测试版在第一阶段上传完不会立即切流；必须先用真实客户端验证节点正常、节点失败回落、节点坏文件回落和旧 `url` 单源兼容，才能恢复同一发布 run 切换 test canonical。用户明确确认测试通过前，不得发布 stable。
