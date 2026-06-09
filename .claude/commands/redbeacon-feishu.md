---
description: 绑定账号的飞书多维表格 — 自动复制审核模板表并关联账号 / 测连通；审核改稿全在飞书
argument-hint: 无参数=给当前账号绑飞书表；多账号时说清是哪个（如「给账号2绑飞书」）
---

> **【飞书 skill】** 把账号关联到一张飞书多维表格。**这张表是整个产品唯一的审核与改稿场所**——生成的内容自动进表，你在飞书里审、改标题/正文/标签、标「通过」，再回来发布。本地不存在任何审核环节。
>
> 上一步是登录（`/redbeacon-login`），下一步是**定位**（`/redbeacon-locate`）——链路顺序 登录 → 飞书绑表 → 定位。飞书的**全局凭证**（App ID / Secret / 接收通知的 User ID）在 `/redbeacon-config` 里配，本 skill 只负责给**单个账号绑表**。
>
> **遵循主入口「自动推进原则」**：onboarding 中绑表成功后直接进定位，别问"要不要定位"；用户单独来绑表/重绑的，做完即止。

---

## 前置一：飞书全局凭证必须先配好

绑表会用到全局飞书应用凭证。先确认配过：

```bash
redbeacon config get feishu_app_id
```

- **已配（非空）** → 进前置二。
- **空 / 未配（含"之前配过现在没了"）** → **别默默跳走**。明确告诉用户凭证缺失，并**立即弹出飞书开发者页面让用户重新录入**：

  ```bash
  open "https://open.feishu.cn/app"
  ```

  > ⚠️ 没检测到飞书应用凭证（App ID / App Secret）。已为你打开飞书开放平台。
  > 如果你**已经建过** RedBeacon 自建应用：进该应用 →「凭证与基础信息」→ 复制 **App ID（`cli_` 开头）** 和 **App Secret** 发我，我帮你重新录入（不用重建应用）。
  > 如果**还没建过**：走 `/redbeacon-config` 的飞书段，我带你创建应用+配权限+发版。

  收到用户发来的凭证后录入并验证：

  ```bash
  redbeacon config set feishu_app_id "<APP_ID>"
  redbeacon config set feishu_app_secret "<APP_SECRET>"
  redbeacon config test-feishu
  ```

  `test-feishu` 通过再进前置二；失败则多为 App ID/Secret 不全或应用版本没发布，引导回 `/redbeacon-config` 检查。

> 凭证错了 `setup` 会直接报错（CLI 会验 `verify_credentials`）。报错同样按上面：提示用户 + `open https://open.feishu.cn/app` 让其核对/重录，别静默吞。

---

## 前置二：选账号

```bash
redbeacon accounts list
```

- **0 个账号** → 先 `/redbeacon-accounts`，本 skill 结束。
- **1 个账号** → 自动用它，记为 `{ID}`。
- **多个账号** → 让用户指明给哪个账号绑表（`$ARGUMENTS` 已说明就直接用）。

---

## 绑表（setup）

> ⚠️ **绑表前先确保 `feishu_user_id` 已配好**（`config get feishu_user_id` 非空）。原因：模板表是用应用身份复制的，**默认归应用所有、用户根本进不去**；`setup` 复制后会自动把表**授权给用户并转移所有权**，这一步必须有 user ID。没配就先 `config feishu-users` 选自己 → `config set feishu_user_id <ou_xxx>`，再绑表。

直接跑，CLI 会自动：复制审核模板表 → 取表 ID → **把表授权给你 + 转移所有权** → 回写账号。已绑过的账号会**复用原表、只补刷授权**（幂等，可放心重跑）：

```bash
redbeacon feishu setup --account-id {ID}
```

按返回分支：

- `{"ok":true,"app_token":"...","table_id":"...","reused":bool,"shared":{"member":{"ok":..},"owner":{"ok":..}}}`：
  - `shared.member.ok` 和 `owner.ok` 都为 `true` → 表已归你、可编辑。把链接给用户：

    ```
    https://www.feishu.cn/base/{app_token}?table={table_id}
    ```

    > ✓ 已为账号「{账号名}」{`reused`=true 说"复用并刷新授权"，否则"创建并绑定"}审核表，已授权给你。以后生成的内容自动进这张表，你在表里审核 / 改稿 / 标「通过」。

  - `member.ok` 或 `owner.ok` 为 `false`（`msg` 多为权限不足）→ 表建好了但**没授权成功，用户可能打不开**。通常是应用缺「管理云文档权限」相关 scope：引导用户去飞书开放平台给应用补该权限 + 重新发版，再重跑 `feishu setup`（幂等会重试授权）。
  - 响应带 `warning`（没配 user ID）→ 按 warning：先配 `feishu_user_id` 再重跑 setup 补授权。
- stderr `{"error":...}` → 多半是飞书凭证问题，按本 skill「前置一」处理（提示 + `open https://open.feishu.cn/app` 重录）。

> 一般不用手动指定表。确有需要（绑到自己已有的某张表）才传 `--app-token <token> --table-id <id>`。

---

## 测连通（test，建议绑完跑一次）

验证应用对这张表能读写、能给你发消息：

```bash
redbeacon feishu test --account-id {ID}
```

返回是一组检查项，逐条转达：

```
表格写入：✓ 写入成功
表格删除：✓ 删除成功
消息推送：✓ 消息发送成功   （未配 User ID 则为「— 跳过」）
```

- 全 ✓ → 飞书链路通了。
- 有 ✗ → 把失败原因给用户：写入失败多为权限/表结构问题，消息失败多为 User ID 没配或没把应用拉进对话。引导回 `/redbeacon-config`（User ID）或检查飞书应用权限。

---

## 完成后给下一步（onboarding 中：绑表成功 → 直接进定位）

**用 per-账号 readiness 看这个号还缺什么**（多账号必须带 id）：

```bash
redbeacon readiness --account-id {ID}
```

判断是"onboarding 路上"还是"用户专门来绑表的"：

- **onboarding 路上**（账号还没定位，readiness 会是 stage5）→ 别停别问，**直接交棒 `/redbeacon-locate`**：
  > ✓ 审核表已绑好。接下来给账号定位——聊清楚做什么赛道、给谁看，再铺一批选题，账号就能开始产内容了。这就进定位。
- **账号早已配好**（readiness=ready）→ 给真正的下一步：
  - **`/redbeacon-generate`** 生成内容（生成后自动进这张飞书表等你审核）
  - 审核完、标了「通过」→ **`/redbeacon-publish`** 发布

---

## 场景对照（别越界）

| 用户想干的 | 去哪个 skill |
|---|---|
| 给账号绑飞书表 / 测连通 | **本 skill** |
| 配飞书 App ID / Secret / User ID（全局凭证） | `/redbeacon-config` |
| 扫码登录小红书 | `/redbeacon-login` |
| 生成内容 / 发布 | `/redbeacon-generate`、`/redbeacon-publish` |
| 在表里怎么审稿改稿 | 在飞书里做，不在任何 skill |

---

## 注意

- **审核与改稿 100% 在飞书多维表格里完成**，本地无审核、无内容编辑入口。别在 skill 里实现或承诺本地审稿。
- 飞书凭证是**全局一份**（所有账号共用），但**表是按账号各绑一张**——多账号每个都要单独 setup。
- 发布（`/redbeacon-publish`）只发飞书表里标了「通过」的记录，且唯一数据源就是飞书；没绑表无法发布。
- 命令成功走 stdout JSON、失败走 stderr `{"error","next"}`；把 error 给用户看，按 next 自愈。
