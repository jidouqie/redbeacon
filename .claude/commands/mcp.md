---
description: MCP 连接管理 — 扫码登录小红书，查看运行日志，手动启停（调试用）
argument-hint: [login|status|logs|start|stop]
---

## 前置：账号选择

先获取账号列表：

```bash
curl -s http://localhost:8000/api/accounts
```

根据返回结果处理：
- **0 个账号**：告知用户没有账号，建议去 Web UI（`http://localhost:8000/login`）新增，或说"帮我创建账号"
- **1 个账号**：自动使用，记为 `ACCOUNT_ID`，无需询问
- **多个账号**：展示账号列表，若 `$ARGUMENTS` 已包含账号名或序号则自动匹配；否则请用户指定操作哪个账号

  | # | 账号名 | 小红书登录 |
  |---|---|---|
  | 1 | 账号A | 已登录 |
  | 2 | 账号B | 未登录 |

  账号名取 `display_name`，若为空则取 `nickname`，再为空则显示"账号 {id}"

---

> **【MCP 连接管理】** 完成小红书扫码登录，查看 MCP 日志排查问题。**MCP 进程是按需启动的，发布和验证登录时系统会自动管理，通常不需要手动启停。本 skill 的核心用途是处理登录。**

你是 RedBeacon 的 MCP 连接管理助手。后端运行在 `http://localhost:8000`，账号 ID 动态获取（执行前先调用 `GET /api/accounts` 取第一个账号的 `id`）。

MCP（xiaohongshu-mcp）是实际操作小红书的进程。**它是按需启动的**：发布任务开始时自动启动，发布完毕自动停止；验证登录时同理。通常看到 MCP"已停止"是正常状态，不代表有问题。

---

## 查看状态（status / 查看）

```bash
curl -s http://localhost:8000/api/accounts/{ACCOUNT_ID}/mcp/status
curl -s http://localhost:8000/api/accounts/{ACCOUNT_ID}
```

展示：
```
MCP 进程：运行中（端口 18060）/ 已停止
登录状态：已登录 / 未登录
账号：{nickname}
```

---

## 启动 MCP（start / 启动）

```bash
curl -s -X POST http://localhost:8000/api/accounts/{ACCOUNT_ID}/mcp/start
```

等待响应：
- 成功 → `{"ok": true}` → 告知 MCP 已启动
- 端口冲突 → 系统会自动清理残留进程后重试，如仍失败提示用户检查系统端口占用
- 其他错误 → 展示错误，提示检查 `MCP_BINARY` 路径是否正确

启动后验证：
```bash
curl -s http://localhost:8000/api/accounts/{ACCOUNT_ID}/mcp/status
```

---

## 停止 MCP（stop / 停止）

```bash
curl -s -X POST http://localhost:8000/api/accounts/{ACCOUNT_ID}/mcp/stop
```

---

## 登录小红书（login / 登录）

登录使用独立的登录程序（与 MCP 发布进程分离），**无需提前启动 MCP**。

### 1. 确保非 headless 模式并启动登录

```bash
# headless=true 时不会弹窗，先确认并关闭
HEADLESS=$(curl -s http://localhost:8000/api/accounts/{ACCOUNT_ID} | python3 -c "import json,sys; print(json.load(sys.stdin).get('mcp_headless', True))")
if [ "$HEADLESS" = "True" ]; then
  curl -s -X PATCH http://localhost:8000/api/accounts/{ACCOUNT_ID} \
    -H "Content-Type: application/json" \
    -d '{"mcp_headless": false}'
fi

curl -s -X POST http://localhost:8000/api/accounts/{ACCOUNT_ID}/login/start
```

调用后系统会在 macOS Terminal（或 Windows 命令窗口）弹出登录界面，二维码直接显示在弹出窗口中。

告知用户：

> 登录窗口已弹出，请在窗口中用小红书 APP 扫描二维码。
> 扫码并在 APP 中点击确认后，告诉我"已扫码"。
> （也可打开 Web UI：`http://localhost:8000/login` 操作，效果相同）

### 2. 等待用户扫码后轮询状态

每 3 秒轮询一次，最多等 5 分钟（二维码有效期约 300 秒）：

```bash
curl -s http://localhost:8000/api/accounts/{ACCOUNT_ID}/login/status
```

返回字段 `logged_in`（布尔值）：
- `{"logged_in": true, "nickname": "..."}` → ✓ 登录成功
- `{"logged_in": false}` → 仍在等待扫码确认，继续轮询
- `{"logged_in": false, "error": "..."}` → 异常，展示 error 并重新执行步骤 1-2

### 4. 验证登录

```bash
curl -s http://localhost:8000/api/accounts/{ACCOUNT_ID}/login/verify
```

返回账号信息（昵称、头像等），更新到本地。

---

## 退出登录（logout / 退出）

```bash
curl -s -X DELETE http://localhost:8000/api/accounts/{ACCOUNT_ID}/login
```

退出后需要重新扫码登录才能发布内容。

---

## 重新登录（账号掉线 / 换账号 / 重新扫码）

识别到"账号掉线了"、"换个小红书账号"、"重新扫码"等意图时执行完整重连流程：

### 1. 确认当前状态

```bash
curl -s http://localhost:8000/api/accounts/{ACCOUNT_ID}/login/verify
```

如果已登录且正常，告知用户无需操作；如果掉线或需要换号，继续以下步骤。

### 2. 退出当前登录

```bash
curl -s -X DELETE http://localhost:8000/api/accounts/{ACCOUNT_ID}/login
```

### 3. 重新扫码登录

直接执行「登录小红书」流程（步骤 1-4），无需用户再次确认。

---

## 查看 MCP 日志（logs / 日志）

```bash
curl -s http://localhost:8000/api/accounts/{ACCOUNT_ID}/mcp/logs
```

展示最近的 MCP 进程日志，用于排查问题。

常见错误：
- `address already in use` → 有残留进程占用端口，先 stop 再 start
- `binary not found` → MCP 二进制文件路径配置有误，检查 `MCP_BINARY` 环境变量
- `login expired` → 登录已过期，需要重新扫码

---

## 完整重置（reset / 重置）

如果 MCP 状态异常，执行完整重置：

```bash
# 1. 停止
curl -s -X POST http://localhost:8000/api/accounts/{ACCOUNT_ID}/mcp/stop

# 2. 等待 2 秒（在对话中告知用户等待）

# 3. 重新启动
curl -s -X POST http://localhost:8000/api/accounts/{ACCOUNT_ID}/mcp/start

# 4. 检查状态
curl -s http://localhost:8000/api/accounts/{ACCOUNT_ID}/mcp/status
```

如果重置后仍然有问题，建议查看系统日志：运行 `/logs` 检查后端日志。
