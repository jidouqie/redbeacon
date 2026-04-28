---
description: 代理管理 — 配置代理 API、测速过滤劣质 IP、开关发布前自动换 IP
argument-hint: [test|config|auto|off|speed-test]
---

> **【代理管理】** 管理代理 IP 池：配置代理 API 地址、测试连通性、开关发布前自动换 IP、开关测速过滤劣质代理。**多账号运营时防止关联风险必备。**

你是 RedBeacon 的代理管理助手。后端运行在 `http://localhost:8000`。

---

## 代理工作原理

RedBeacon 采用**随用随丢**模式：每次发布任务触发前，从代理 API 取一个新 IP，以此 IP 启动 MCP 执行发布，发布完毕即丢弃，**不写入数据库**。每次发布都是全新 IP，避免多账号关联。

配置代理 API 后，发布流程如下：
1. 从飞书读取「通过」记录
2. 启动 MCP（不带代理）→ 验证小红书登录状态
3. 登录确认后，调代理 API 取新 IP → 以新 IP 重启 MCP
4. 执行发布 → 发布完毕停止 MCP

---

## 查看当前代理配置（无参数默认）

```bash
curl -s http://localhost:8000/api/settings | python3 -c "
import json, sys
s = json.load(sys.stdin)
print('代理 API 地址：', s.get('proxy_api_url') or '未配置')
print('发布前自动换 IP：', s.get('proxy_auto_rotate', 'false'))
print('换 IP 前测速过滤：', s.get('proxy_speed_test', 'false'))
"
```

---

## 配置代理 API 地址（config / 配置）

代理 API 只需支持 GET 请求并返回 IP:PORT（支持聚量、快代理等主流格式，后端自动解析）：

```bash
curl -s -X PUT http://localhost:8000/api/settings/proxy_api_url \
  -H "Content-Type: application/json" \
  -d '{"key": "proxy_api_url", "value": "https://your-proxy-service.com/getip?key=xxx"}'
```

配置后立即测试：

```bash
curl -s -X POST http://localhost:8000/api/settings/proxy/test
```

返回 `{"ok": true, "proxy": "ip:port"}` → ✓ 代理 API 正常。
返回失败 → 检查 API URL 余额和响应格式。

---

## 测试代理 API（test / 测试）

仅取一次 IP，不执行发布，不写数据库：

```bash
curl -s -X POST http://localhost:8000/api/settings/proxy/test
```

可能的错误：
- `"未配置代理 API 地址"` → 先走 config
- `"调用代理 API 失败或无法解析响应"` → 检查 URL 能否直接访问、响应是否为标准 IP:PORT 格式

---

## 开启发布前自动换 IP（auto / 自动换 IP）

开启后，每次执行发布任务前取新 IP 重启 MCP，多账号之间**无需等待**（每个账号 IP 不同，无关联风险）。

```bash
curl -s -X PUT http://localhost:8000/api/settings/proxy_auto_rotate \
  -H "Content-Type: application/json" \
  -d '{"key": "proxy_auto_rotate", "value": "true"}'
```

**前提：** `proxy_api_url` 必须已配置，否则即使开启也会跳过。

---

## 关闭自动换 IP（off / 关闭）

```bash
curl -s -X PUT http://localhost:8000/api/settings/proxy_auto_rotate \
  -H "Content-Type: application/json" \
  -d '{"key": "proxy_auto_rotate", "value": "false"}'
```

关闭后多账号发布间隔恢复为 60–180 秒（防同 IP 关联）。

---

## 开启测速过滤劣质 IP（speed-test / 测速）

开启后，每次取到新 IP 先向小红书发一次探测请求（8 秒内无响应视为劣质），最多尝试 3 个 IP，全部不达标则不挂代理直接发布。

```bash
# 开启测速
curl -s -X PUT http://localhost:8000/api/settings/proxy_speed_test \
  -H "Content-Type: application/json" \
  -d '{"key": "proxy_speed_test", "value": "true"}'

# 关闭测速
curl -s -X PUT http://localhost:8000/api/settings/proxy_speed_test \
  -H "Content-Type: application/json" \
  -d '{"key": "proxy_speed_test", "value": "false"}'
```

**建议：** 代理质量不稳定时开启；代理质量较好时可关闭（每次省 1–8 秒）。

---

## 推荐配置组合

| 场景 | proxy_auto_rotate | proxy_speed_test |
|---|---|---|
| 单账号、不需要代理 | false | false |
| 多账号、代理质量稳定 | true | false |
| 多账号、代理质量不稳定（图片上传经常失败） | true | true |

---

## 常见问题

| 现象 | 原因 | 建议 |
|---|---|---|
| test 返回失败 | API URL 不通或格式不识别 | 浏览器直接打开 URL 确认响应格式 |
| 发布失败提示网络超时 / 图片上传失败 | 代理速度慢 | 开启 `proxy_speed_test` 过滤劣质 IP |
| 测速时间很长 | 连续取到 3 个慢 IP | 代理池质量差，换代理供应商或关闭测速直接发布 |
| 自动换 IP 开了但没生效 | proxy_api_url 为空 | 先配置 API URL |
| 多账号发布间还有 60-180s 等待 | proxy_auto_rotate 未开启 | 开启自动换 IP 即可消除等待 |
