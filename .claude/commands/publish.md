---
description: 发布内容 — 从飞书拉取审核通过的笔记，触发发布到小红书
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
  | 1 | 账号A | ✓ 已登录 |
  | 2 | 账号B | ✗ 未登录 |

  账号名取 `display_name`，若为空则取 `nickname`，再为空则显示"账号 {id}"

---

> **本 skill 的职责**：从飞书多维表格同步审核结果，将状态为「通过」的笔记发布到小红书。MCP 进程会在发布时自动启动/停止，无需手动管理。

---

## 第一步：预检登录状态

发布前检查账号是否已登录（MCP 会自动启动，但登录 Cookie 必须有效）：

```bash
curl -s http://localhost:8000/api/accounts/{ACCOUNT_ID}
```

- `login_status != "logged_in"` → 提示用户先运行 `/mcp login` 完成扫码登录
- `login_status == "logged_in"` → 继续

---

## 第二步：预览飞书待发布内容

先同步飞书最新审核状态，看看有多少内容待发布：

```bash
curl -s -X POST http://localhost:8000/api/content/feishu-sync
curl -s "http://localhost:8000/api/content/{ACCOUNT_ID}?status=approved&limit=20"
```

- 如果列表为空 → 告知用户：

  > 飞书中暂无审核通过的笔记，无内容可发布。
  > 如需发布，请先在飞书多维表格中将内容状态改为「通过」，再运行本 skill。

  **流程结束。**

- 如果有内容 → 展示列表：

  ```
  飞书已通过，待发布：N 篇
  1. [ID: xxx] {title} — 选题：{topic}
  2. [ID: xxx] {title} — 选题：{topic}
  ```

---

## 第三步：确认并发布

> 准备发布以上 N 篇内容到小红书，确认吗？

用户确认后触发发布：

```bash
PUB_RESP=$(curl -s -w "\n%{http_code}" -X POST http://localhost:8000/api/content/publish-now)
HTTP_CODE=$(echo "$PUB_RESP" | tail -1)
BODY=$(echo "$PUB_RESP" | head -1)
if [ "$HTTP_CODE" != "200" ]; then
  echo "发布请求失败（$HTTP_CODE）：$BODY"
else
  echo "发布结果：$BODY"
fi
```

**发布流程说明（publish-now 内部自动完成）：**
1. 对每个账号再次同步飞书审核状态
2. 有待发布内容 → 启动 MCP → 验证登录 → 取新 IP（若开启代理轮换）→ 逐条发布 → 停止 MCP
3. 多账号时：开启代理轮换则账号间无等待；未开启则上一账号有发布后等待 60–180s

> **`scheduled_at`（计划发布时间）字段说明：**
> - 这是发布时**透传给小红书平台**的定时展示参数，让小红书在指定时间对外展示笔记
> - **不是** RedBeacon 自身的发布时机判断——RedBeacon 检测到飞书「通过」状态就立即发布，与此字段无关
> - 有效范围：1小时~14天内；超出此范围或为空 → 忽略，小红书立即发布
> - 如果看到内容有 `scheduled_at` 值，不要理解为"RedBeacon 会等到那个时间再发"

返回 `{"synced": N, "published": N}`，展示结果：

```
发布完成：
✓ 同步 N 条，发布成功 N 篇
```

---

## 终止正在进行的发布任务

如果发布任务正在执行，需要中止（例如选错账号、发现内容有问题）：

```bash
# 查询是否有任务在运行
curl -s http://localhost:8000/api/content/publish-running

# 发送取消信号
curl -s -X POST http://localhost:8000/api/content/cancel-publish
```

取消信号发送后，任务会在当前条目发布完成后停止（不会强杀正在进行的上传操作）。
也可在 Web UI 首页（http://localhost:8000）点击「终止任务」按钮。

---

## 第四步：查看发布结果

```bash
curl -s "http://localhost:8000/api/content/{ACCOUNT_ID}?status=published&limit=5"
```

展示最新发布的内容（含 `xhs_note_id` 小红书笔记 ID）。

如果有失败（`status=failed`）：

```bash
curl -s "http://localhost:8000/api/content/{ACCOUNT_ID}?status=failed&limit=10"
```

展示 `error_msg`，常见原因：MCP 登录过期、图片上传失败（代理速度慢）、内容违规。

---

## 错误处理

| 错误 | 原因 | 建议 |
|---|---|---|
| 账号未登录 | Cookie 失效或从未登录 | 运行 `/mcp login` |
| 飞书同步失败 | 飞书未配置或 token 过期 | 运行 `/setup-feishu` |
| 无可发布内容 | 飞书里没有「通过」状态记录 | 在飞书表格中审核内容后再来 |
| 图片上传失败 / 网络超时 | 代理速度慢 | 在代理设置中开启测速过滤，或更换代理供应商 |
| 发布失败 | 登录过期 / 内容违规 | 重新扫码登录，或检查内容是否合规 |
