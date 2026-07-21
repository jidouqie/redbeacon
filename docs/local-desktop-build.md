# RedBeacon 本地双平台构建与 Windows 虚拟机部署

最后核对：2026-07-17

## 结论

当前桌面交付只构建两个包：

| 交付平台 | 构建位置 | 强制目标 |
|---|---|---|
| macOS | Apple Silicon Mac 本机 | `mac-arm64` |
| Windows | Windows 11 ARM64 Parallels 虚拟机 | `win-x64 / AMD64` |

Linux 客户端暂停构建和分发，不进入 manifest、下载页和发布检查。

当前唯一有效的客户端构建入口是 `tools/build_desktop_local.sh`。旧 GitHub 打包方案已封装为不可直接索引的冷归档；日常开发、搜索、发布检查和 agent 上下文均不得读取或恢复，只有用户明确要求时才允许人工解档。

Windows 11 on Arm 支持运行 x86/x64 用户态程序，因此 ARM64 虚拟机可以运行 x64 Python、PyInstaller 和最终 x64 客户端。它不等于跨平台编译：PyInstaller 会跟随当前 Python 解释器的系统和架构，所以 Windows 包必须在 Windows 内用 **x64 Python** 构建，不能用 ARM64 Python 打包后改文件名。

参考：

- [Microsoft：Windows on Arm 的 x86/x64 仿真](https://learn.microsoft.com/en-ca/windows/arm/apps-on-arm-x86-emulation)
- [PyInstaller：不是跨编译器，产物跟随活动 Python](https://www.pyinstaller.org/en/stable/operating-mode.html)
- [uv：ARM64 Windows 可管理并运行 x64 Python](https://docs.astral.sh/uv/concepts/python-versions/)

## 构建纪律

1. `cli/` 必须先提交且工作区干净。
2. 编排器只创建一次 `git archive HEAD`；Mac 本机与 Windows VM 必须使用这一个归档。
3. 工具链版本来自 `cli/packaging/build-versions.env`，两端都不能临时升级。
4. Mac 和 Windows 各自跑全量测试、PyInstaller、浏览器预热、真实卡片渲染和桌面启动 smoke。
5. Windows 还要确认 GUI、CLI、渲染器三个 PE 都是 `0x8664 (AMD64)`，并运行 PowerShell 安装事务 smoke。
6. 两端全部成功后才组装完整 `release-artifacts/` 并写 `metadata/build-evidence.json`。构建过程不读取 OSS 凭据、不上传、不切 canonical manifest。
7. 永远先构建和发布测试版；人工确认后，不改代码，再用同一套脚本构建正式版。

## Windows VM 一次性配置

当前虚拟机：

```text
Parallels 名称：Windows 11 (1)
当前地址：10.211.55.3
默认构建用户：diaojiawang
```

Parallels 使用共享网络即可，不需要把 22 端口暴露到公网。IP 由虚拟网络分配，重建网络或迁移虚拟机后可能变化；变化时通过 `--windows-host USER@IP` 或 `REDBEACON_WINDOWS_BUILD_HOST` 覆盖。

### 1. 防止虚拟机自动暂停

在 Parallels 虚拟机配置中：

- 关闭“空闲时暂停 Windows / Pause Windows when possible”；
- “关闭窗口时”选择“保持运行”；
- Windows 电源设置里，接通电源时不要自动睡眠。

否则宿主机能 ping 通，但 `ssh` 或长时间浏览器下载会在中途突然断开。

当前虚拟机也可以在 Mac 终端直接设置：

```bash
prlctl set "{3c9308f9-3cfa-4496-8e3f-e2ad16f19cdd}" --pause-idle off
prlctl set "{3c9308f9-3cfa-4496-8e3f-e2ad16f19cdd}" --on-window-close keep-running
```

这里使用 VM ID 而不是带括号的显示名称，避免部分 Parallels CLI 版本静默忽略设置。

### 2. 准备宿主机公钥

Mac 终端查看现有公钥：

```bash
cat ~/.ssh/id_ed25519.pub
```

只把 `.pub` 的一整行交给 Windows；不要复制没有 `.pub` 后缀的私钥。

### 3. 在 Windows 管理员 PowerShell 执行初始化

项目 `code` 目录已由 Parallels 共享时，可以直接运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
& "\\Mac\code\auto-redbook\redbeacon\tools\setup_windows_build_vm.ps1" `
  -BuildUser "diaojiawang" `
  -PublicKey "粘贴完整的 ssh-ed25519 公钥"
```

脚本会：

- 安装并启动 Windows OpenSSH Server；
- 在 Windows 公用网络配置文件开放 TCP 22，但只允许 Mac 宿主 `10.211.55.2`；
- 把公钥写入管理员密钥文件并收紧 ACL；
- 安装固定版本的 x64 `uv` 到 `C:\RedBeaconBuildTools`；
- 把该目录加入机器 PATH；
- 关闭接通电源时的自动睡眠；
- 打印用户名、IPv4 和 `SSH_READY=true`。

OpenSSH 设置依据：[Microsoft OpenSSH Server 安装](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse) 与 [Microsoft 公钥管理](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement)。

### 4. Windows 自检

```powershell
Get-Service sshd
Get-NetFirewallRule -Name OpenSSH-Server-In-TCP
Test-NetConnection 127.0.0.1 -Port 22
uv --version
```

期望：`sshd` 为 `Running`，22 端口成功，`uv` 版本与 `build-versions.env` 一致。

### 5. Mac 连接自检

```bash
ssh -o BatchMode=yes diaojiawang@10.211.55.3 "cmd.exe /c ver"
```

成功后可选写入 `~/.ssh/config`：

```sshconfig
Host redbeacon-win
  HostName 10.211.55.3
  User diaojiawang
  IdentityFile ~/.ssh/id_ed25519
  ServerAliveInterval 30
  ServerAliveCountMax 6
```

然后可把构建目标写成 `redbeacon-win`：

```bash
REDBEACON_WINDOWS_BUILD_HOST=redbeacon-win tools/build_desktop_local.sh --channel test
```

## 日常构建

测试版：

```bash
tools/build_desktop_local.sh --channel test
```

该命令永远只构建和测试，产出 `release-artifacts/`，不读取发布凭据、不上传、不切换线上版本。公开发布仅能在项目根目录调用全局 `bytestaff-digital-employee-publish` Skill。

用户明确确认由全局 Skill 发布的测试版通过后，且中间没有改代码：

```bash
REDBEACON_STABLE_APPROVED=1 tools/build_desktop_local.sh --channel stable
```

完成 stable 构建后，仍由同一全局 Skill 持有独立的 stable 批准凭证发布。

本地产物保留在：

```text
dist/local-build/<channel>/release-artifacts/
```

## 常见故障

### ping 通但 SSH 超时

依次检查：虚拟机没有暂停、`sshd` 正在运行、防火墙规则启用、IP 没变化。22 端口未通时不要开始 Mac 打包，编排脚本会先做 SSH/uv 预检。

### Windows 构建显示 ARM64

宿主系统和 Python 的 `platform.machine()` 显示 ARM64 都可能是正常的，因为它们可能报告原生系统架构。可靠门禁是读取 `python.exe` 的 PE 头：必须为 `0x8664`，同时 Python 指针宽度必须为 64 位。任何一项不符，都删除构建环境并让脚本按 `cpython-3.12.11-windows-x86_64-none` 重建，禁止继续打包。

### PyInstaller 成功但双击崩溃

成功退出不等于可发布。必须通过冻结包桌面启动、浏览器安装与启动、真实卡片 PNG、PowerShell 安装事务和错误日志扫描；任一失败都不得产出可交付给全局 Skill 的干净制品树。

### 普通 INFO 日志被 PowerShell 当成错误

PowerShell 5.1 在 `$ErrorActionPreference = "Stop"` 时会把原生程序写到 stderr 的日志包装成 `NativeCommandError`。冒烟脚本必须先完整捕获输出，再依据真实退出码和明确崩溃关键字判定；不能因为日志走了 stderr 就提前中止。

### Playwright 解压后提示拒绝访问

Windows 可能在 Chromium 关闭后短暂持有文件句柄。安装器必须先把新 revision 放到最终目录，再从最终目录启动验证；目录移动和删除有限重试，失败恢复旧 revision。不要从临时目录启动后立刻重命名整个临时目录。

### 客户端版本和包元数据显示不同

动态版本写在源码里时，旧 editable 元数据可能被本机缓存。两端构建都使用 `uv sync --frozen --reinstall-package redbeacon`，并在打包前比较 `importlib.metadata.version("redbeacon")` 与 `redbeacon.__version__`；不一致立即阻断。

### 构建后线上没有变化

这是正常设计。项目构建器不做任何线上变更；只有全局 `bytestaff-digital-employee-publish` Skill 完成不可变制品上传、真实客户端验收和 canonical manifest 原子切换后，用户才会看到新版本。

## 给平台下载页的口径

- 显示 Windows x64 与 macOS Apple Silicon 两个入口。
- 暂时隐藏 Linux，不提供旧 Linux 固定直链。
- manifest 来自中央上海 OSS `https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com/projects/redbeacon/<channel>/latest.json`。
- 大文件按 manifest 的 `download_urls` 先试统一下载节点一次，失败后回落不可变中央 OSS `url`。
- 测试版和正式版 canonical 路径分开，不得交叉消费。
