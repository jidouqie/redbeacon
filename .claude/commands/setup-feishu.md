---
description: 配置飞书集成 — 引导创建自建应用、配置权限、初始化多维表格、设置审核通知
---

> **【飞书集成配置】** 飞书是 RedBeacon 内容审核和发布的核心环节：内容生成后自动推送飞书多维表格，审核通过后自动发布小红书。**配置一次，后续无需重复。**

你是 RedBeacon 的飞书集成配置助手。后端运行在 `http://localhost:8000`。

先获取账号列表确定 `ACCOUNT_ID`（多账号时询问用户选哪个），然后检测当前配置状态：

```bash
SETTINGS=$(curl -s http://localhost:8000/api/settings)
ACCOUNTS=$(curl -s http://localhost:8000/api/accounts)
```

用 python3 解析，输出 `GOTO=stepN`：

```python
import json, sys, subprocess

settings = json.loads("""SETTINGS_JSON""")
accounts = json.loads("""ACCOUNTS_JSON""")
account  = accounts[0] if accounts else {}

def ok(d, k): return bool((d or {}).get(k, '').strip())

cred_ok    = ok(settings, 'feishu_app_id')
userid_ok  = ok(settings, 'feishu_user_id') and any(
    bool((a.get('feishu_user_id') or '').strip()) for a in accounts
)
token_ok   = any(bool((a.get('feishu_app_token') or '').strip()) for a in accounts)

if   not cred_ok:    print('GOTO=step1')
elif not userid_ok:  print('GOTO=step3')
elif not token_ok:   print('GOTO=step4')
else:                print('GOTO=done')
```

- `GOTO=step1` → 凭证未配，从第一步开始
- `GOTO=step3` → 凭证已配，直接跳第三步获取 user_id
- `GOTO=step4` → user_id 已配，直接跳第四步建表
- `GOTO=done`  → 全部完成，告知用户退出

---

## 第一步：在飞书开放平台完成准备工作

用 Bash 打开浏览器：

```bash
open "https://open.feishu.cn/app"
```

然后**一次性**告知用户所有需要手动完成的操作：

---

> 请在浏览器里完成以下操作，完成后把 **App ID** 和 **App Secret** 告诉我，我来帮你完成剩余配置。
>
> **① 创建自建应用**
> - 点击「创建企业自建应用」
> - 名称：RedBeacon（随意），描述随意，确认创建
>
> **② 配置权限**
> - 左侧「权限管理」→「批量导入权限」
> - 粘贴以下 JSON，点确认：
>
> ```json
> {"tenant":["bitable:app","bitable:app:readonly","base:app:copy","base:app:create","base:app:read","base:app:update","base:collaborator:create","base:collaborator:read","base:field:create","base:field:read","base:record:create","base:record:delete","base:record:read","base:record:retrieve","base:record:update","base:table:create","base:table:read","base:view:read","docs:permission.member:create","docs:permission.member:readonly","docs:permission.member:retrieve","docs:permission.member:transfer","drive:file","drive:file:download","drive:file:readonly","drive:file:upload","contact:user.base:readonly","contact:user.id:readonly","contact:user.employee_id:readonly","im:message","im:message:send_as_bot","im:message:send_multi_users","im:message:readonly","im:resource"],"user":["contact:user.employee_id:readonly"]}
> ```
>
> **③ 发布应用版本**（权限必须发布后才生效）
> - 左侧「版本管理与发布」→「创建版本」→ 填版本号 `1.0.0` → 「提交审核」
> - 审核人就是自己，直接进审核页面点「通过」
>
> **④ 复制凭证**
> - 左侧「凭证与基础信息」
> - 复制 **App ID**（格式 `cli_xxxxxxxx`）
> - 点击查看并复制 **App Secret**
>
> 完成后直接告诉我：**App ID 是 xxx，App Secret 是 xxx**

---

等用户回复 App ID 和 App Secret。

---

## 第二步：保存凭证并验证

收到用户输入后，保存并立即验证：

```bash
curl -s -X POST http://localhost:8000/api/settings/batch \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"key": "feishu_app_id",     "value": "用户输入的AppID"},
      {"key": "feishu_app_secret", "value": "用户输入的AppSecret"}
    ]
  }'

curl -s -X POST http://localhost:8000/api/settings/test-feishu-auth
```

- 返回 `{"ok": true}` → 继续第三步
- 返回错误 → 告知用户：
  > 凭证验证失败，请确认：① App ID / Secret 复制完整无多余空格；② 应用版本已发布（未发布则权限不生效）

---

## 第三步：识别通知接收人

```bash
curl -s http://localhost:8000/api/settings/feishu-users
```

**只有一个成员** → 自动选定，无需询问，告知：
> ✓ 通知接收人已自动识别为：{姓名}

**多个成员** → 展示列表，让用户选择：
```
请选择你的飞书账号（用于接收内容通知）：
1. 张三（zhangsan@company.com）
2. 李四（lisi@company.com）
```

选定后同时写入两处（缺一不可）：

```bash
# 全局 settings
curl -s -X POST http://localhost:8000/api/settings/batch \
  -H "Content-Type: application/json" \
  -d '{"items": [{"key": "feishu_user_id", "value": "OPEN_ID"}]}'

# 账号表
curl -s -X PATCH http://localhost:8000/api/accounts/{ACCOUNT_ID} \
  -H "Content-Type: application/json" \
  -d '{"feishu_user_id": "OPEN_ID"}'
```

接口报错或返回空 → 提示检查 `contact:user.base:readonly` 权限是否已发布生效，修复后再继续。

---

## 第四步：初始化飞书多维表格

```bash
curl -s -X POST http://localhost:8000/api/accounts/{ACCOUNT_ID}/feishu/setup \
  -H "Content-Type: application/json" \
  -d '{}'
```

- 成功（含 `"skipped": true`）→ 继续第五步
- **报错 / 500**：**先查账号状态，确认是否已建表**，再决定是否重试：

  ```bash
  curl -s http://localhost:8000/api/accounts/{ACCOUNT_ID} | python3 -c \
    "import json,sys; a=json.load(sys.stdin); print('已建表' if a.get('feishu_app_token') else '未建表')"
  ```

  - 返回「已建表」→ **不要重试**，直接继续第五步（建表已成功，只是后端返回时报错）
  - 返回「未建表」→ 检查权限是否已发布生效，修复后再重试一次

---

## 第五步：连通性测试 + 完成

```bash
curl -s -X POST http://localhost:8000/api/accounts/{ACCOUNT_ID}/feishu/test
FEISHU_URL=$(curl -s http://localhost:8000/api/content/feishu-url | python3 -c "import json,sys; print(json.load(sys.stdin).get('url',''))")
```

测试通过后输出：

```
✓ 飞书集成配置完成
  凭证：已验证
  通知接收人：{姓名}
  多维表格：{url}

内容生成后会自动推送到飞书表格，在表格里把状态改为「通过」后 RedBeacon 会自动发布。
```

**完成后自动继续系统引导，检测下一项配置。**
