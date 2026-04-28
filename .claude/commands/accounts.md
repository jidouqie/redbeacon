---
description: 账号管理 — 列表、新建、改名、删除
argument-hint: [list|create|rename|delete]
---

> **【账号管理】** 小红书账号的完整 CRUD：查看/新建/改名/删除。**扫码登录走 `/mcp`，代理配置走 `/proxy`。**

你是 RedBeacon 的账号管理助手。后端运行在 `http://localhost:8000`。

MAX_ACCOUNTS 编译进二进制（免费版=1，专业版更多），新建受此限制。

---

## 查看账号列表（list / 查看 / 无参数默认）

```bash
curl -s http://localhost:8000/api/accounts
```

展示表格：

```
| # | ID | 账号名 | 小红书登录 | 端口 |
|---|---|---|---|---|
| 1 | 1  | 账号A | ✓ 已登录 | 18060 |
| 2 | 2  | 账号B | ✗ 未登录 | 18061 |
```

字段映射：
- 账号名：`display_name` → `nickname` → `"账号 {id}"`
- 小红书登录：`login_status == "logged_in"` ? "✓ 已登录" : "✗ 未登录"

> 注：MCP 进程是按需启动的，发布/验证时自动启停，不需要关注 MCP 运行状态。

---

## 新建账号（create / 新建 / 加一个）

```bash
# 不带参数（系统自动选端口）
curl -s -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{}'

# 指定端口 + 代理（都可选）
curl -s -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{"mcp_port": 18066, "proxy": "http://user:pass@host:port"}'
```

成功返回：新账号的 id、mcp_port。

达到 MAX_ACCOUNTS 上限时返回 403：
```json
{"detail": {"code": "ACCOUNT_LIMIT", "max": 1}}
```
告知用户：
> 当前版本最多支持 1 个账号。如需多账号矩阵功能，请扫码联系作者升级 RedBeacon 专业版（企业微信 / 关注公众号吉豆茄）。

创建后提示用户：
> 账号已创建。下一步登录：
> - 运行 `/mcp login` 引导扫码
> - 或打开 http://localhost:8000/login 扫码

---

## 改备注名（rename / 改名）

展示账号列表确认要改哪个，然后：

```bash
curl -s -X PATCH http://localhost:8000/api/accounts/{ACCOUNT_ID} \
  -H "Content-Type: application/json" \
  -d '{"display_name": "用户填写的名称"}'
```

清空备注名用空字符串 `""`。

---

---

## 删除账号（delete / 删除 / 移除）

**删除不可恢复**，会同时清掉该账号的：
- 所有内容（content_queue、publish_log）
- 所有提示词预设（prompt）
- 所有策略（strategy）
- MCP 进程会自动停止

操作前二次确认：

```bash
curl -s http://localhost:8000/api/accounts
```

展示列表，用户明确指定账号后：

> 确认要删除「[账号名]」（ID={ACCOUNT_ID}）吗？
> 该账号所有内容、选题、策略将一并清除，**不可恢复**。

用户确认后：

```bash
curl -s -X DELETE http://localhost:8000/api/accounts/{ACCOUNT_ID}
```

删除成功后展示剩余账号列表。

---

## 查看单个账号详情

```bash
curl -s http://localhost:8000/api/accounts/{ACCOUNT_ID}
```

返回字段：
- `id` / `display_name` / `nickname` / `xhs_user_id`
- `login_status` / `mcp_port` / `mcp_running` / `mcp_headless` / `proxy`
- `feishu_app_token` / `feishu_table_id` / `feishu_user_id`
- `auto_generate_enabled` / `generate_schedule_json`
- `last_login_check`

---

## 常见场景对照

| 场景 | 走哪个 skill |
|---|---|
| 账号创建/改名/删除 | 本 skill |
| 扫码登录 / 退出 / 重新登录 | `/mcp` |
| 配置代理 API、换 IP | `/proxy` |
| 飞书表格绑定该账号 | `/setup-feishu` |
| 修改该账号定位 | `/strategy` |
| 改该账号生成排期 | `/schedule` |
| 是否显示浏览器窗口（调试） | 设置页 → 系统配置 → "执行任务时显示浏览器窗口" |
