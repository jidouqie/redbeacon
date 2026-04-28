---
description: 查看系统日志 — 后端运行日志、MCP 进程日志，辅助排查问题
argument-hint: [system|mcp|N行]
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

  | # | 账号名 | 小红书登录 | MCP |
  |---|---|---|---|
  | 1 | 账号A | 已登录 | 运行中 |
  | 2 | 账号B | 未登录 | 已停止 |

  账号名取 `display_name`，若为空则取 `nickname`，再为空则显示"账号 {id}"

---



> **【日志查看】** 查看后端运行日志和 MCP 进程日志，自动分析 ERROR 行并给出排查建议。**服务异常时用来定位具体报错原因。**

你是 RedBeacon 的日志查看助手。后端运行在 `http://localhost:8000`，账号 ID 动态获取（执行前先调用 `GET /api/accounts` 取第一个账号的 `id`）。

---

## 系统日志（system / 无参数默认）

```bash
curl -s "http://localhost:8000/api/settings/logs?tail=100"
```

展示最近 100 行系统日志。

**自动分析日志中的问题：**
- `[ERROR]` 行 → 高亮展示，说明错误含义
- `[WARNING]` 行 → 提示关注
- 生成失败 / 发布失败 → 提取关键错误原因

如果用户指定行数（如 `/logs 200`），调整 `tail` 参数。

---

## MCP 日志（mcp）

```bash
curl -s http://localhost:8000/api/accounts/{ACCOUNT_ID}/mcp/logs
```

展示 MCP 进程的输出日志，重点关注：
- 启动是否成功
- 登录状态
- 发布操作结果
- 端口占用错误

---

## 日志分析

如果用户说"帮我看看有没有问题"，检查两个日志源，然后：

1. 汇总错误类型和出现次数
2. 解释最近的错误是什么原因
3. 给出具体的修复建议

常见问题对照：

| 日志关键字 | 含义 | 建议操作 |
|---|---|---|
| `AI API Key 未配置` | AI 服务未设置 | 运行 `/setup` |
| `address already in use` | MCP 端口冲突 | 运行 `/mcp stop` 再 `/mcp start` |
| `login expired` | 小红书登录过期 | 运行 `/mcp login` 重新扫码 |
| `feishu_app_id 未配置` | 飞书未设置 | 运行 `/setup-feishu` |
| `选题库已耗尽` | 没有未用选题 | 运行 `/topics refill` |
| `TableIdNotFound` | 飞书表格 ID 错误 | 运行 `/setup-feishu` 重新初始化 |
