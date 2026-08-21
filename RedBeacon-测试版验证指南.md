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
4. 新建一个测试账号，完成平台登录、小红书扫码、账号定位、选题、内容方案、文案和图片生成，并确认生成任务严格逐篇串行。
5. 在审稿台自主添加一篇笔记，测试回车添加标签、增删换图和图片排序；标题超过 20 字、正文超过 888 字或图片删空时都必须阻止通过。
6. 分别学习一个对标账号和一篇对标笔记：自动化浏览器弹出后客户端会重新置前并解释当前动作；未登录时浏览器自动关闭并引导到账号管理；完成结果切页后仍保留，用户可选择写入或取消。
7. 通过 Skill 提交一篇宿主生成的文案与图片，确认图片先净化再进入同一审稿台；宿主能力缺失或失败时应直接使用平台能力兜底，不再要求用户额外确认。
8. 自动化页面所有设置实时保存，时间和批次控件具有明确可点击状态，“立即试跑”位于顶部。开启后系统进入防空闲休眠；测试到点触发、手动试跑、关闭后释放防休眠，以及补题、自动通过、自动发布开关的实际边界。
9. 分别验证立即发布和逐篇定时发布。发布前应显示平台确认与点数预留阶段；只有明确成功才结算并归档，失败时取消预留且稿件仍可重试。
10. 从旧版更新后，账号、定位、方案、选题、审稿、自动化设置和登录态保留；更新前快照存在。
11. 断开下载节点后重新安装，应自动回落中央 OSS；节点返回错误内容时也必须校验失败并回落。
12. 卸载测试版不影响正式版，不带 `PURGE` 时重装后数据仍在。

## 发布纪律

项目只运行 `tools/build_desktop_local.sh --channel test` 生成已测试的 `release-artifacts/`。OSS 上传、下载节点准备、canonical manifest 切换和回滚全部由统一发布系统负责，项目代码不持有上传或删除权限。

普通发布会把本机同一份制品树分别直传中央 OSS 和下载节点；两端成功后直接原子切换 test canonical 并完成发布，不让节点从 OSS 拉取，也不从 OSS 或节点全量下载制品复验。测试版切换后由用户按本指南手动安装和完整试用；用户明确确认测试通过前，不得发布 stable。发布后若再修改客户端、CLI、Skill、安装器或制品结构，原测试结论立即作废，必须重新发布测试版。
