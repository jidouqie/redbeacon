---
description: 配置 AI 服务 — 设置 API Base URL、API Key、文案模型、图片模型，并验证连通性
---

> **【AI 服务配置】** 配置 AI 接口的 Base URL、API Key、文案模型、图片模型，并验证连通性。**生成内容前必须先完成这个配置。**

你是 RedBeacon 的配置助手。后端运行在 `http://localhost:8000`，账号 ID 动态获取（执行前先调用 `GET /api/accounts` 取第一个账号的 `id`）。

---

## 第一步：读取当前配置

```bash
curl -s http://localhost:8000/api/settings
```

展示当前状态：
- `ai_base_url`：已设置 / 未设置
- `ai_api_key`：已设置（显示"__SET__"）/ 未设置
- `ai_model`：当前值
- `image_model`：当前值

---

## 第二步：询问配置信息

用自然对话逐步收集，已设置的字段询问"是否要更新"。

**必填项：**

1. **AI Base URL**
   > 你使用的是哪个 AI 服务？（OpenAI 官方填 `https://api.openai.com/v1`，中转服务填对应地址）

2. **API Key**
   > 填入你的 API Key（输入后我不会回显，直接保存）

3. **文案生成模型**
   > 先拉取可用模型列表再让用户选：
   ```bash
   curl -s http://localhost:8000/api/settings/models
   ```
   展示 `models` 数组，让用户从中选择，或直接输入模型名。

4. **图片生成模型**（必填，用于 AI 配图）
   > 从上面的模型列表中选择支持图片生成的模型（通常和文案模型相同，或使用专门的图片模型如 flux、dall-e-3）。

---

## 第三步：保存配置

批量保存（文案模型和图片模型都必须保存）：

```bash
curl -s -X POST http://localhost:8000/api/settings/batch \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"key": "ai_base_url",   "value": "用户输入的URL"},
      {"key": "ai_api_key",    "value": "用户输入的Key"},
      {"key": "ai_model",      "value": "用户选择的文案模型"},
      {"key": "image_model",   "value": "用户选择的图片模型"}
    ]
  }'
```

---

## 第四步：验证连通性

**验证文案 AI：**
```bash
curl -s -X POST http://localhost:8000/api/settings/test-ai
```

- 返回 `{"ok": true, "reply": "..."}` → ✓ AI 连接正常
- 返回错误 → 展示错误信息，提示检查 Base URL 和 Key 是否正确

**验证图片模型：**
```bash
curl -s -X POST http://localhost:8000/api/settings/test-image
```

- 返回 `found_in_list: true` → ✓ 图片模型已确认
- `found_in_list: false` → 提示用户该模型名可能有误，展示可用模型列表重新选择

---

---

## 代理设置（可选，多账号发布需要）

用于为不同账号分配独立 IP，防止关联风险。

### 配置代理 API 地址

```bash
curl -s -X PUT http://localhost:8000/api/settings/proxy_api_url \
  -H "Content-Type: application/json" \
  -d '{"key": "proxy_api_url", "value": "https://your-proxy-api.com/getip?..."}'
```

### 测试代理 API 是否可用

```bash
curl -s -X POST http://localhost:8000/api/settings/proxy/test
```

返回 `{"ok": true, "proxy": "ip:port"}` 表示代理 API 正常。

### 为账号分配代理 IP

```bash
# 刷新所有账号的代理 IP
curl -s -X POST http://localhost:8000/api/settings/proxy/refresh \
  -H "Content-Type: application/json" \
  -d '{}'

# 只刷新指定账号
curl -s -X POST http://localhost:8000/api/settings/proxy/refresh \
  -H "Content-Type: application/json" \
  -d '{"account_id": 1}'
```

---

## 完成后自动继续引导

AI 配置验证通过后，**立即继续检查下一项必要配置，不要停在这里**：

```bash
curl -s http://localhost:8000/api/settings
```

按以下顺序检测并引导：

1. **飞书未配置**（`feishu_app_id` 为空）→ 告知用户飞书是审核和发布的必要环节，直接进入飞书配置流程（相当于运行 `/setup-feishu`）
2. **MCP 程序未就绪** → 检测（见下方），未就绪则引导
3. **无账号** → 提示创建账号
4. **账号未登录** → 引导扫码
5. **账号未定位** → 引导运行 `/onboard`
6. **全部就绪** → 告知系统已完全配置，可以开始生成内容

### MCP 程序检测

```bash
CWD="$(pwd)"
if [ "$(uname)" = "Darwin" ]; then
  MCP_PATH="$CWD/mac/tools/xiaohongshu-mcp"
elif [ "$(uname)" = "Linux" ]; then
  MCP_PATH="$CWD/linux/tools/xiaohongshu-mcp"
else
  MCP_PATH="$CWD/win/tools/xiaohongshu-mcp.exe"
fi

if [ -f "$MCP_PATH" ] && [ -x "$MCP_PATH" ]; then
  echo "mcp_ok"
else
  echo "mcp_missing:$MCP_PATH"
fi
```

- `mcp_ok` → 继续
- `mcp_missing` → 告知用户：
  > RedBeacon 发布功能需要 xiaohongshu-mcp 程序，未在 `tools/` 目录下找到。
  > 请确认安装包完整性，或联系管理员重新获取。
  > 路径应为：`{MCP_PATH}`
