---
description: 扫码登录小红书 — 弹二维码用 App 扫 / 查登录态 / 退出重登；登录态是发布的前提
argument-hint: 无参数=给当前账号扫码登录；多账号时说清是哪个（如「登录账号2」「账号2掉线了重登」）
---

> **【登录 skill】** 给账号挂上小红书登录态。发布（`/redbeacon-publish`）必须先有有效登录态，掉线会被跳过。本 skill 负责扫码登录、查状态、退出重登。
>
> 上一步是建号（`/redbeacon-accounts`）。链路顺序是 登录（stage3）→ 飞书绑表（stage4）→ 定位（stage5）——建号后先扫码落地，登录成功后**下一步是绑飞书表**（`/redbeacon-feishu`）。登录用的浏览器会话**命令结束即停**，不是常驻服务。
>
> **遵循主入口「自动推进原则」**：onboarding 阶段登录成功后直接进飞书绑表，别问"要不要绑飞书"；用户主动来重登/查登录态的，做完即止。

---

## 前置：选账号 + 先看现在登没登

```bash
redbeacon accounts list
```

- **0 个账号** → 还没建号，先去 `/redbeacon-accounts`，本 skill 到此为止。
- **1 个账号** → 自动用它，记为 `{ID}`，不用问。
- **多个账号** → 把列表给用户，让其指明给哪个账号登录（`$ARGUMENTS` 里已说明就直接用）。

确定 `{ID}` 后，先查库里记录的登录态（快，不起浏览器）：

```bash
redbeacon login status --account-id {ID}
```

- `login_status == "logged_in"` → 看着已登录。但库里的状态可能过期（cookie 掉线库里仍写着登录），用户若说"要发布 / 怀疑掉线"，进「确认是否真的还在线」用 `verify` 实测；否则可直接告知已登录、给下一步。
- 其它（`logged_out` / 空）→ 进「扫码登录」。

---

## 确认是否真的还在线（verify，实测）

`status` 只读库，`verify` 会**真起一个无头浏览器拿当前 cookie 去小红书验**，最准，用于"发布前确认 / 怀疑掉线"：

```bash
redbeacon login verify --account-id {ID}
```

- `{"logged_in": true, "nickname": "..."}` → 在线，把昵称报给用户，给下一步。
- `{"logged_in": false}` → 已掉线，进「扫码登录」重登。

> verify 起的浏览器查完即停，不残留。

---

## 扫码登录（start / 登录 / 重登）

这是**阻塞命令**，会打开一个**有界面的浏览器**并自动弹出二维码图片，等你用手机扫，最多等 180 秒：

```bash
redbeacon login start --account-id {ID}
```

它会按进度往 stdout 依次打多行 JSON，**逐条转达给用户**，别等全部结束才说话：

| 收到 | 跟用户说 |
|---|---|
| `{"status":"browser_started"}` | 正在加载二维码… |
| `{"status":"qr_shown","qr_file":"..."}` | **二维码已弹出（一张图片）。请打开小红书 App → 我 → 扫一扫，扫描这张二维码，180 秒内完成。** |
| `{"logged_in":true,"nickname":"..."}`（最终成功） | ✓ 登录成功，账号「{nickname}」。 |
| `{"already_logged_in":true}` 或直接 `{"logged_in":true}` | 该账号本来就在线，无需重扫。 |
| stderr `{"error":"扫码超时或登录失败"}` | 超时/失败了。问用户要不要再来一次（重跑 `login start`）。 |

> 扫码成功后会自动保存 cookie、回写昵称和登录态，登录用的浏览器随即关闭。

---

## 退出登录 / 换号重登（delete）

退出登录 = 清掉本机保存的 cookie：

```bash
redbeacon login delete --account-id {ID}
```

**换一个小红书号登录同一个账号槽**：先 `delete` 清掉旧 cookie，再 `login start` 扫新号的码。直接重扫不 delete 通常也行，但怀疑串号/异常时先 delete 更干净。

---

## 完成后给下一步（onboarding 中：登录成功 → 直接进飞书绑表）

**用 per-账号 readiness 看这个号还缺什么**（多账号必须带 id，否则全局 readiness 会被别的号"带成 ready"、漏掉本号）：

```bash
redbeacon readiness --account-id {ID}
```

判断这次登录是"onboarding 路上"还是"用户专门来重登的"：

- **onboarding 路上**（这账号还没绑飞书表，readiness 会是 stage4）→ 别停别问，**直接交棒 `/redbeacon-feishu`** 给账号绑审核表：
  > ✓ 登录成功，账号「{nickname}」已落地。接下来把它绑到飞书审核表——以后生成的内容都进这张表给你审核。这就绑表。
- **用户专门来重登 / 查登录态的**（账号早已配好）→ 按 readiness 给真正缺的下一步：
  - 还没绑飞书表 → **`/redbeacon-feishu`**
  - 还没定位 → **`/redbeacon-定位`**
  - 全就绪（readiness=ready）→ **`/redbeacon-generate`** 生成内容

---

## 场景对照（别在本 skill 里越界）

| 用户想干的 | 去哪个 skill |
|---|---|
| 扫码登录 / 查登录态 / 退出 / 重登 | **本 skill** |
| 建号 / 改名 / 删号 | `/redbeacon-accounts` |
| 给账号定位、生成选题 | `/redbeacon-定位` |
| 绑该账号的飞书多维表格 | `/redbeacon-feishu` |
| 生成内容 / 发布 | `/redbeacon-generate`、`/redbeacon-publish` |

---

## 注意

- 登录态是**发布的硬前提**：发布时若账号掉线，该账号会被直接跳过（并通过飞书提醒重登），不会报错也不会发出去。所以发布前不确定就先 `verify`。
- 登录浏览器是有界面窗口（要扫码），但**命令一结束就关**，无任何常驻/后台进程，别向用户承诺"保持登录在线服务"。
- `login start` 是前台阻塞、最长 180s；让用户尽快扫，超时就重跑。
- 命令成功走 stdout JSON、失败走 stderr `{"error","next"}`；把 error 给用户看，按 next 自愈，别静默吞。
