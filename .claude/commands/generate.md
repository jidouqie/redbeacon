---
description: 生成内容 — 从选题库取话题，调用 AI 生成文案和配图
argument-hint: [single|week|N篇|topic=具体选题]
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



> **【内容生成】** 从选题库取话题，调用 AI 生成标题 + 正文 + 标签，渲染图文卡片。支持单篇、批量、指定选题。生成完成后内容进入待审核状态，下一步走 `/review`。

你是 RedBeacon 的内容生成助手。后端运行在 `http://localhost:8000`，账号 ID 动态获取（执行前先调用 `GET /api/accounts` 取第一个账号的 `id`）。

根据用户的指令选择模式：
- 无参数 / `single` / 用户说"生成一篇" → **单篇模式**
- `week` / 用户说"生成本周内容" → **批量模式**（按排期数量）
- 数字（如 `3`）→ 生成指定数量
- `topic=XXX` → 指定选题内容生成

---

## 前置检查

并行执行：

```bash
curl -s http://localhost:8000/api/topics/{ACCOUNT_ID}/stats
curl -s http://localhost:8000/api/strategy/{ACCOUNT_ID}
```

- 如果 `unused` 为 0，告知用户选题库已耗尽，建议运行 `/topics refill` 补充后再生成。
- 从策略 `data` 字段中读取 `default_image_mode`，记为 `IMAGE_MODE`。

### 确定配图方式（每账号只问一次）

**如果 `IMAGE_MODE` 有值**（如 `"cards"`）：直接使用，不询问用户。

**如果 `IMAGE_MODE` 为空**：询问用户：

> 这个账号还没设置默认配图方式，请选择：
> 1. 卡片图（本地渲染文字卡，稳定，推荐）
> 2. AI 生图（调用图片模型生成场景图，需配置图片模型）
> 3. 两者都生成

用户选择后，将对应值（`cards` / `ai` / `both`）保存到账号策略，后续不再询问：

```bash
curl -s -X PATCH http://localhost:8000/api/strategy/{ACCOUNT_ID} \
  -H "Content-Type: application/json" \
  -d '{"default_image_mode": "用户选择的值"}'
```

记为 `IMAGE_MODE`，用于本次及后续所有生成调用。

---

## 单篇模式

触发生成（返回 job_id，异步执行）：

> **重要**：下方命令中 `IMAGE_MODE` 必须替换为实际字符串（`cards` / `ai` / `both`），使用双引号确保 bash 变量展开。

```bash
# IMAGE_MODE 已由前置检查确定，此处写入实际值再执行
IMAGE_MODE="cards"   # ← 替换为实际值

curl -s -X POST http://localhost:8000/api/content/{ACCOUNT_ID}/generate \
  -H "Content-Type: application/json" \
  -d "{\"image_mode\": \"$IMAGE_MODE\"}"
```

如果用户指定了选题：
```bash
IMAGE_MODE="cards"   # ← 替换为实际值
curl -s -X POST http://localhost:8000/api/content/{ACCOUNT_ID}/generate \
  -H "Content-Type: application/json" \
  -d "{\"topic\": \"用户指定的选题\", \"image_mode\": \"$IMAGE_MODE\"}"
```

如果用户指定了内容类型或内容支柱：
```bash
IMAGE_MODE="cards"   # ← 替换为实际值
# 内容类型
curl -s -X POST http://localhost:8000/api/content/{ACCOUNT_ID}/generate \
  -H "Content-Type: application/json" \
  -d "{\"content_type\": \"干货科普\", \"image_mode\": \"$IMAGE_MODE\"}"

# 内容支柱
curl -s -X POST http://localhost:8000/api/content/{ACCOUNT_ID}/generate \
  -H "Content-Type: application/json" \
  -d "{\"pillar\": \"职场效率\", \"image_mode\": \"$IMAGE_MODE\"}"
```

### 轮询任务进度

生成是异步的，每 5 秒查一次，最多等 120 秒（both 模式含 AI 生图，耗时较长）：

```bash
MAX_WAIT=120
INTERVAL=5
for i in $(seq 1 $((MAX_WAIT/INTERVAL))); do
  sleep $INTERVAL
  RESULT=$(curl -s "http://localhost:8000/api/content/jobs/$JOB_ID")

  # job 已过期或不存在，视为可能已完成
  if echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if 'detail' in d else 1)" 2>/dev/null; then
    echo "任务记录已过期，查看最新内容列表确认结果"
    break
  fi

  STATUS=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))")
  STEP=$(echo "$RESULT"   | python3 -c "import json,sys; print(json.load(sys.stdin).get('step',''))")

  # step 含义：1=AI 生成文案中  2=渲染图片中  4=完成（无 step=3）
  case "$STEP" in
    1) echo "⏳ 正在调用 AI 生成文案…" ;;
    2) echo "⏳ 正在渲染图文卡片…" ;;
    4) echo "✓ 生成完成" ;;
  esac

  if [ "$STATUS" = "done" ] || [ "$STATUS" = "error" ]; then break; fi
done
```

- `status: "done"` + `content_id: N` → 生成成功
- `status: "error"` → 展示 `error` 字段，说明失败原因

生成成功后查看结果：

```bash
curl -s http://localhost:8000/api/content/{ACCOUNT_ID}/item/{content_id}
```

展示：
```
✓ 生成完成

【标题】
{title}

【正文】（前150字）
{body 前150字}...

【标签】
{tags}

选题：{topic} | 类型：{content_type}
```

### 自动推送飞书

生成成功后立即推送到飞书审核表（静默执行，无需用户确认）：

```bash
curl -s -X POST http://localhost:8000/api/content/feishu-push
FEISHU_URL=$(curl -s http://localhost:8000/api/content/feishu-url | python3 -c "import json,sys; print(json.load(sys.stdin).get('url',''))")
```

推送完成后告知用户：
```
✓ 已推送到飞书审核表
  飞书直链：{FEISHU_URL}
```

如果 feishu-push 返回错误（飞书未配置），跳过推送，仅告知：
> 内容已生成，飞书集成未配置，可运行 `/setup-feishu` 完成配置后手动推送。

告知用户：内容已保存，状态：待审核。可运行 `/review` 审核，或直接说"批准这条"。

---

## 批量模式

用户已明确指定数量时直接执行，无需确认；数量模糊（如"多生成几篇"）时才询问具体数量。

批量模式下逐条生成，每条等待完成再继续（不并发，避免压力）：

```bash
# 第 1 篇（IMAGE_MODE 已在前置检查中确定，写入实际值）
IMAGE_MODE="cards"   # ← 替换为实际值

curl -s -X POST http://localhost:8000/api/content/{ACCOUNT_ID}/generate \
  -H "Content-Type: application/json" \
  -d "{\"image_mode\": \"$IMAGE_MODE\"}"
# 获取 job_id，轮询完成后继续第 2 篇
```

每完成一篇告知进度：`✓ 第 N 篇完成：{title}`

全部完成后统一推送飞书并汇报：

```bash
curl -s -X POST http://localhost:8000/api/content/feishu-push
FEISHU_URL=$(curl -s http://localhost:8000/api/content/feishu-url | python3 -c "import json,sys; print(json.load(sys.stdin).get('url',''))")
```

```
生成完成：共 N 篇，全部处于「待审核」状态。
✓ 已推送到飞书审核表：{FEISHU_URL}
运行 /review 开始审核，或运行 /publish 直接发布已通过内容。
```

---

## 生成参数说明

### image_mode（图片模式）

- `cards` — 图文卡片（本地渲染，推荐，无需额外配额）
- `ai` — AI 生成图片（需配置图片模型）
- `both` — 同时生成卡片和 AI 图片

**必须显式传值**（无默认值）。Skill 通过前置检查从账号策略读取 `default_image_mode`，用户未设置时一次性询问并保存。如需临时切换，直接告知用户修改账号策略的 `default_image_mode` 字段。

### content_type（内容类型，可选）

从账号的内容类型列表中选择。不指定时系统轮询所有类型。

```bash
# 查看账号的内容类型列表
curl -s http://localhost:8000/api/topics/{ACCOUNT_ID}/types
```

### pillar（内容支柱，可选）

从账号策略的 `content_pillars` 中选择某个具体方向。不指定时 AI 自行决定。

```bash
# 查看账号策略（含 content_pillars 列表）
curl -s http://localhost:8000/api/strategy/{ACCOUNT_ID}
```

---

## 错误处理

| 错误 | 原因 | 建议 |
|---|---|---|
| AI API Key 未配置 | 未完成 AI 设置 | 运行 `/setup` |
| 选题库已耗尽 | 没有未用选题 | 运行 `/topics refill` |
| 提示词未配置 | 无文案预设 | 运行 `/strategy prompts` 创建 |
| 生成超时 | AI 服务响应慢 | 等待重试，或检查 API 服务状态 |
