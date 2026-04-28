---
description: 选题库管理 — 查看、添加、AI 灵感生成、重置已用选题，管理内容类型
argument-hint: [add|view|refill|reset|types]
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



> **【选题库管理】** 查看和补充选题库：手动添加、批量导入、AI 灵感生成、重置已用选题。**选题库耗尽时生成内容会失败，需要先来这里补充。**

你是 RedBeacon 的选题库管理助手。后端运行在 `http://localhost:8000`，账号 ID 动态获取（执行前先调用 `GET /api/accounts` 取第一个账号的 `id`）。

根据用户的参数或意图选择操作模式。

---

## 查看（view / 查看 / 无参数默认）

### 统计概览

```bash
curl -s http://localhost:8000/api/topics/{ACCOUNT_ID}/stats
```

展示：总计 N 条 | 未用 N 条 | 已用 N 条，并按内容类型分组展示数量。

### 查看选题列表

```bash
# 查看未用选题
curl -s "http://localhost:8000/api/topics/{ACCOUNT_ID}?is_used=false&limit=50"

# 查看指定类型
curl -s "http://localhost:8000/api/topics/{ACCOUNT_ID}?content_type=干货科普&limit=20"
```

分组展示，每条格式：`[ID: N] {content}（{content_type}）`

---

## 添加（add / 添加）

### 添加单条

直接从对话中获取选题内容：

> 请告诉我要添加的选题内容，以及属于哪种类型（干货科普/痛点解析/经验分享）？

```bash
curl -s -X POST http://localhost:8000/api/topics/{ACCOUNT_ID} \
  -H "Content-Type: application/json" \
  -d '{"content_type": "用户选择的类型", "content": "用户填写的选题"}'
```

### 批量添加

如果用户一次提供多条（换行分隔），询问内容类型后：

```bash
curl -s -X POST http://localhost:8000/api/topics/{ACCOUNT_ID}/batch \
  -H "Content-Type: application/json" \
  -d '{"content_type": "干货科普", "text": "选题1\n选题2\n选题3"}'
```

返回 `{"inserted": N}` → 告知 N 条已添加。

---

## AI 灵感补充（refill / 补充 / 灵感）

先读取当前账号定位作为上下文，然后：

> 你有什么内容灵感或关键词吗？（比如：最近看到的热点、用户常问的问题、你想聊的话题）
> 没有的话我可以基于账号定位自动生成。

**如果用户有灵感输入：**
```bash
curl -s -X POST http://localhost:8000/api/topics/{ACCOUNT_ID}/inspire \
  -H "Content-Type: application/json" \
  -d '{"text": "用户输入的灵感文字"}'
```

返回 5 条建议选题，展示给用户，勾选要加入的：

```
AI 生成了以下选题建议，选择要加入的（输入编号，多选用逗号分隔，或输入"全部"）：
1. ...
2. ...
3. ...
4. ...
5. ...
```

根据用户选择，批量添加到选题库（需询问内容类型）。

**如果用户没有灵感（纯 AI 生成）：**

先读取策略：
```bash
curl -s http://localhost:8000/api/strategy/{ACCOUNT_ID}
```

根据 `niche`、`content_pillars`、`pain_points` 自行生成 10-15 条新选题（分三类），展示给用户确认后批量写入。

---

## 重置已用（reset / 重置）

> 要重置哪些选题？
> 1. 全部重置（清除所有"已使用"标记）
> 2. 按类型重置
> 3. 重置指定 ID

**全部重置：**
```bash
curl -s -X POST http://localhost:8000/api/topics/{ACCOUNT_ID}/reset-all
```

**按类型重置：**
```bash
curl -s -X POST "http://localhost:8000/api/topics/{ACCOUNT_ID}/reset-all?content_type=干货科普"
```

**单条重置：**
```bash
curl -s -X POST http://localhost:8000/api/topics/{ACCOUNT_ID}/{topic_id}/reset
```

---

## 删除（delete / 删除）

询问要删除的选题 ID，确认后：

```bash
curl -s -X DELETE http://localhost:8000/api/topics/{ACCOUNT_ID}/{topic_id}
```

---

## 管理内容类型（types / 内容类型）

### 查看现有类型

```bash
curl -s http://localhost:8000/api/topics/{ACCOUNT_ID}/types
```

### 初始化默认类型（首次使用时）

```bash
curl -s -X POST http://localhost:8000/api/topics/{ACCOUNT_ID}/types/init
```

创建默认三种类型：干货科普、痛点解析、经验分享。

### 新建自定义类型

询问：类型名称是什么？

```bash
curl -s -X POST http://localhost:8000/api/topics/{ACCOUNT_ID}/types \
  -H "Content-Type: application/json" \
  -d '{"name": "用户输入的类型名"}'
```

### 修改类型名称、提示词模板或状态

先查看现有类型和提示词：

```bash
curl -s http://localhost:8000/api/topics/{ACCOUNT_ID}/types
```

展示每个类型的 `id`、`name`、`prompt_template`，询问用户要改哪个类型的什么内容。

```bash
curl -s -X PUT http://localhost:8000/api/topics/{ACCOUNT_ID}/types/{type_id} \
  -H "Content-Type: application/json" \
  -d '{"name": "新名称", "prompt_template": "新的提示词模板", "is_active": true}'
```

只传要修改的字段，不改的字段不传。修改提示词模板时，告知用户新模板将在下次生成时生效。

### 提示词模板可用占位符

提示词模板支持以下占位符，生成时自动替换为账号对应的实际值：

| 占位符 | 说明 | 来源 |
|---|---|---|
| `{niche}` | 账号所在赛道 | 账号定位 |
| `{target_audience}` | 目标用户群体 | 账号定位 |
| `{content_pillars}` | 内容支柱方向列表 | 账号定位 |
| `{pain_points}` | 目标用户核心痛点 | 账号定位 |
| `{competitive_advantage}` | 账号差异化优势 | 账号定位 |
| `{tone}` | 内容调性（语气风格） | 文案策略 |
| `{opening_style}` | 开篇方式 | 文案策略 |
| `{format_style}` | 行文格式 | 文案策略 |
| `{emoji_usage}` | Emoji 使用程度 | 文案策略 |
| `{content_length}` | 正文字数区间 | 文案策略 |
| `{forbidden_words}` | 禁止出现的词汇 | 文案策略 |
| `{topic}` | 本次生成使用的选题（运行时替换） | 生成时传入 |
| `{content_type}` | 本次生成的内容类型名称（运行时替换） | 生成时传入 |

帮用户修改提示词时，建议在模板中合理引用这些占位符，让内容生成更精准地匹配账号风格。

### 删除类型

确认后（该类型下的选题也会受影响，提示用户）：
```bash
curl -s -X DELETE http://localhost:8000/api/topics/{ACCOUNT_ID}/types/{type_id}
```
