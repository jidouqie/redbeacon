---
description: 策略管理 — 查看和修改账号定位、文案预设（提示词模板）、图片预设
argument-hint: [positioning|prompts|image|view]
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



> **【策略管理】** 账号初始化完成后，随时调整账号定位字段、管理文案提示词模板、配置图片生成策略。**修改定位后内容风格自动跟着变。**

你是 RedBeacon 的策略管理助手。后端运行在 `http://localhost:8000`，账号 ID 动态获取（执行前先调用 `GET /api/accounts` 取第一个账号的 `id`）。

根据参数或用户意图选择操作。

---

## 查看完整策略（view / 查看）

```bash
curl -s http://localhost:8000/api/strategy/{ACCOUNT_ID}
```

清晰展示 `data` 字段中的所有内容：

```
【账号定位】
赛道（niche）：...
目标用户（target_audience）：...
竞争优势（competitive_advantage）：...
变现方式（monetization）：...
发布频率（posting_frequency）：...

内容方向（content_pillars）：
  • 方向1（描述）
  • 方向2
  若未设置显示"未配置"

目标受众痛点（pain_points）：
  • 痛点1
  • 痛点2
  若未设置显示"未配置"

【内容风格】
调性（tone）：... 若未设置显示"亲切自然，专业但不刻板，像朋友分享而非说教（默认）"
开篇风格（opening_style）：... 若未设置显示"提问式或数字列举，前两行必须抓住读者注意力（默认）"
内容形式（format_style）：... 若未设置显示"分段清晰，多用短句，每段2-3行，重点内容单独成行（默认）"
Emoji 用量（emoji_usage）：... 若未设置显示"适量，每段1-2个，增加亲切感，不堆砌（默认）"
字数区间（content_length）：... 若未设置显示"300-500字（默认）"

【视觉风格】
{visual_theme}
```

---

## 修改账号定位（positioning / 定位）

读取当前值后，询问要修改哪个字段，或让用户直接描述要改什么。

根据用户输入构建 PATCH 请求（只传要更新的字段）：

```bash
curl -s -X PATCH http://localhost:8000/api/strategy/{ACCOUNT_ID} \
  -H "Content-Type: application/json" \
  -d '{
    "niche": "...",
    "target_audience": "...",
    "competitive_advantage": "...",
    "monetization": "...",
    "posting_frequency": "每周N篇",
    "content_pillars": [{"name": "方向名", "description": "说明"}, ...],
    "pain_points": ["...", "..."],
    "tone": "...",
    "opening_style": "痛点戳入|数字吸引|故事开场|提问引发",
    "format_style": "分点列举|叙述型|干货罗列|对话体",
    "emoji_usage": "不用|适量|丰富",
    "content_length": "200-400字|300-500字|500-800字",
    "visual_theme": "...",
    "forbidden_words": ["...", "..."]
  }'
```

修改后告知用户已保存，并说明这些设置会影响下次内容生成时的提示词。

---

## 管理文案预设（prompts / 预设 / 提示词）

文案预设是生成内容时注入 AI 的提示词模板，支持多套。

### 查看现有预设

```bash
curl -s http://localhost:8000/api/strategy/{ACCOUNT_ID}/prompts
```

展示所有预设列表（id、name、type、is_active）。

### 查看某个预设的完整内容

询问用户选择哪个 ID，然后在展示列表时直接包含 `prompt_text` 字段的完整内容。

### 新建预设

收集：
- 预设名称（如："知识分享版"、"故事化版"）
- 类型（`copy` = 文案，`image` = 图片）
- 提示词内容（可以帮用户基于当前账号定位起草一个）

```bash
curl -s -X POST http://localhost:8000/api/strategy/{ACCOUNT_ID}/prompts \
  -H "Content-Type: application/json" \
  -d '{
    "type": "copy",
    "name": "用户填写的名称",
    "prompt_text": "提示词内容",
    "notes": "用途说明（可选）"
  }'
```

### 修改预设

```bash
curl -s -X PUT http://localhost:8000/api/strategy/{ACCOUNT_ID}/prompts/{prompt_id} \
  -H "Content-Type: application/json" \
  -d '{"prompt_text": "新内容", "notes": "新说明"}'
```

### 帮用户起草提示词

如果用户说"帮我写一个提示词"，根据当前策略数据生成一份合适的提示词，包含：

- 角色设定（你是一个专注[niche]领域的小红书博主）
- 目标用户描述
- 内容风格要求（tone、format_style、emoji_usage、content_length）
- 禁止事项
- 输出格式要求（JSON 格式：title、body、tags）

---

## 管理图片预设（image / 图片）

### 查看图片预设

```bash
curl -s http://localhost:8000/api/strategy/{ACCOUNT_ID}/image
```

展示：`mode`（cards/ai/both）、`template_mode`、`card_theme`、`ai_model`、`prompt_template`。

### 修改图片预设

询问用户要改哪些：

```bash
curl -s -X PUT http://localhost:8000/api/strategy/{ACCOUNT_ID}/image \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "cards|ai|both",
    "template_mode": "specific|random",
    "card_theme": "default|dark|warm|cool|minimal|vibrant|elegant",
    "ai_model": "模型名（如用 AI 配图）",
    "prompt_template": "AI 配图提示词模板"
  }'
```

**mode 说明：**
- `cards` — 只用图文卡片（本地渲染，无需 AI 图片配额）
- `ai` — 只用 AI 生成图片
- `both` — 同时生成卡片和 AI 图片

**template_mode 说明：**
- `specific` — 使用当前激活的图片模板（固定参考图风格）
- `random` — 每次随机选择一个图片模板（风格多样）

---

## 管理图片模板（image-templates / 图片模板）

图片模板是 AI 配图时的参考图+提示词组合，支持多套轮换使用。

### 查看所有模板

```bash
curl -s http://localhost:8000/api/strategy/{ACCOUNT_ID}/image-templates
```

展示：id、名称、是否激活（`is_active`）、参考图数量。

### 新建模板

```bash
curl -s -X POST http://localhost:8000/api/strategy/{ACCOUNT_ID}/image-templates \
  -H "Content-Type: application/json" \
  -d '{
    "name": "模板名称",
    "items": [
      {"image_path": "/绝对路径/或空", "prompt": "这张图的提示词"}
    ]
  }'
```

每个 `item` 是一对（参考图路径 + 对应提示词）。`image_path` 可为空字符串（仅用提示词）。

### 修改模板

```bash
curl -s -X PUT http://localhost:8000/api/strategy/{ACCOUNT_ID}/image-templates/{template_id} \
  -H "Content-Type: application/json" \
  -d '{"name": "新名称", "items": [...]}'
```

### 激活模板（`specific` 模式下使用激活的那一个）

```bash
curl -s -X POST http://localhost:8000/api/strategy/{ACCOUNT_ID}/image-templates/{template_id}/activate
```

### 取消激活所有模板

```bash
curl -s -X POST http://localhost:8000/api/strategy/{ACCOUNT_ID}/image-templates/deactivate
```

### 删除模板

```bash
curl -s -X DELETE http://localhost:8000/api/strategy/{ACCOUNT_ID}/image-templates/{template_id}
```
