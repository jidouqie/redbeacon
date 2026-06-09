---
description: 账号管理 — 列表 / 新建 / 改名 / 改代理 / 删除；新建即扫码登录小红书
argument-hint: 无参数=列出账号并问要干啥；也可直接说「加个账号」「改名」「删除账号」「看详情」
---

> 🗣️ **对用户全程自然语言**：路由 / 调用别的能力是你**内部**的事，**给用户看的回复里不要出现 `/redbeacon-*`、`redbeacon xxx` 这类命令名 / 斜杠命令**——用人话说你要做什么（如「我来帮你生成一篇」而不是「运行 /redbeacon-generate」；「觉得不对劲随时跟我说」而不是「去 /redbeacon-diagnose」）。**除非用户主动说想用命令 / 想看命令，否则别提、别列命令。** CLI 命令是你在后台执行的，用户无感。

> **【账号 skill】** 小红书账号的 CRUD。**账号不是一条空记录，而是一组会互相影响文案产出的联动数据的载体**——新建账号后不留空壳，**立刻接着扫码登录**（`/redbeacon-login`）让账号落地。建号本身用户几乎无感，先把"扫码登录成功"这个实感给到他。
>
> 上一步是配置（`/redbeacon-config`），下一步是**登录**（`/redbeacon-login`）；之后的顺序是 登录 → 飞书绑表（`/redbeacon-feishu`）→ 定位（`/redbeacon-locate`）。代理验证走 `/redbeacon-config` 的 `test-proxy`。
>
> **遵循主入口的「自动推进原则」**：这些都是必需步骤，建完号直接进登录，别问"要不要登录"。

---

## 第零步：照镜子（每次入口先跑）

```bash
redbeacon accounts list
```

渲染成表格——**每个账号有两个身份：编号（id，固定连续）+ 备注名（display_name，有意义的名字）**：

```
| 编号 | 备注名 | 小红书登录 | 会话 |
|------|--------|-----------|------|
| 1号  | 副业搞钱手册 | ✓ 已登录 | 运行中 |
| 2号  | （未命名）   | ✗ 未登录 | 已停止 |
```

字段映射：
- **编号** = `id` → 一律念成「{id}号小红书」（"1号""2号"，多账号矩阵里用户靠编号快速定位）
- **备注名** = `display_name`（建号时用户可起，或定位后按赛道自动生成）。若是兜底值「{id}号小红书」或 `redbeacon-{id}` 这类抽象默认 → 显示「（未命名）」并提示用户起一个。
- **小红书登录** = `login_status == "logged_in"` ? `✓ 已登录` : `✗ 未登录`
- **会话** = `session_running` ? `运行中` : `已停止`（进程内 CloakBrowser 会话，命令结束即停，不用管）

> **指代账号**：用户说「1号 / 一号」按编号定位；说「副业号 / 搞钱那个」按备注名模糊匹配到对应 id。两种都支持，别只认 id。

看完按用户意图路由：新建 / 改名（改备注）/ 改代理 / 删除 / 查看详情。无明确意图时把上表给用户，问要干啥。

---

## 新建账号（create / 加账号 / 新建）

> 付费门槛由 **CLI 强制**（不是这个 skill 在拦）：免费版只允许单账号，多账号是付费能力。skill 只负责把 CLI 的拦截结果翻译给用户，**不要试图绕过**。

### ① 直接创建，让 CLI 决定能不能建

建号时可顺手起个**备注名**（多账号矩阵里靠它和编号区分，别让用户对着一堆"1号2号"发懵）。问一句、不强求：

> 给这个号起个备注吗？（比如「副业搞钱手册」「职场干货号」）—— 现在不想起也行，**定位聊完我按它的赛道帮你拟一个**。

- 用户给了名字 → `redbeacon accounts create --name "<用户起的备注>"`
- 用户说先不起 → `redbeacon accounts create`（备注先留空兜底，定位后自动生成，见 `/redbeacon-locate` 收尾）

```bash
redbeacon accounts create --name "副业搞钱手册"   # 起了备注
redbeacon accounts create                        # 没起，兜底「{id}号小红书」，定位后自动命名
```

- **成功**（返回含 `id`）→ 进 ②。建好后编号=`id`、备注=用户起的或兜底值，已自动播种默认图片策略和图片模板。
- **失败且 `code` == `ACCOUNT_LIMIT`** → 已达账号上限（免费版=1）。这是付费解锁点，**别重试创建**，转去下面的「解锁多账号」流程引导用户激活；激活成功后再回来重跑 `accounts create`。

---

## 解锁多账号（激活 / 我要买 / 加不了号了）

> 触发：建号撞 `ACCOUNT_LIMIT`，或用户直说"解锁/激活/买多账号"。多账号矩阵是付费能力（**¥199 一次性买断，解锁码绑定本机，换机失效**）。门槛由 CLI 强制，skill 只负责把用户顺畅带过激活，**绝不自己编解锁码、绝不绕过校验**。

先看当前状态，已解锁就别再走流程：

```bash
redbeacon license info
```

返回 `{"machine_code","tier","unlocked","max_accounts"}`。`unlocked=true` → 已是付费版，直接去建号。否则按 4 步引导：

**① 给用户看机器码**——`machine_code` 字段就是这台机器的身份码，购买页要粘它。用人话告诉用户：

> 解锁多账号 ¥199 一次性买断，绑定你**当前这台电脑**（换电脑要重新买）。
> 你的机器码是 **`{machine_code}`** —— 待会儿粘到购买页。

**② 弹出官网购买页**（像配飞书那样直接弹浏览器，别只甩链接）。把机器码拼进 URL，购买页会自动填好，用户连粘都不用粘：

```bash
open "https://redbeacon.jiomig.com/buy.html?mc={machine_code}"          # macOS
# Linux: xdg-open  "https://redbeacon.jiomig.com/buy.html?mc={machine_code}"
```

> 已帮你打开购买页（机器码已自动填好）。直接用支付宝付款 → 付款成功页会显示一串**激活码**，复制它发给我。

**③ 接激活码并激活**——用户把激活码贴回对话后：

```bash
redbeacon license activate "<用户给的激活码>"
```

- 成功 `{"ok":true,"tier":"pro","max_accounts":99}` → 告诉用户已解锁，**立刻自动重跑** `accounts create` 把刚才想建的号建出来，接着进登录（②）。
- 失败 `code=LICENSE_INVALID`（解锁码无效或与本机不匹配）→ 最常见两个原因，逐一帮用户排查，别让他干等：
  1. **机器码贴错**：再跑一次 `license info`，确认购买页填的机器码和这里的 `machine_code` 一字不差。
  2. **在别的机器上买的**：解锁码绑机器，必须在**要用的这台**上购买和激活，换机失效。
  让用户核对后把激活码重发，再试一次。

**铁律**：解锁码就是用户的凭证，提醒他存好（换机/重装系统要重新买）；激活只认本机现算的机器码，你无法代签、也别假装能解锁。

### ② 强制交棒登录（关键，别省，也别问"要不要登录"）

建完**不要停在这里**、**也不要回头去定位**。建号本身用户几乎无感，紧接着就把"扫码登录成功"这个实感给到他——**直接交棒 `/redbeacon-login`**，并**带上这个新账号的 id**：

> ✓ {新id}号小红书已创建（备注：{用户起的或「未命名」}）。
> 先把小红书号扫码登录上，让账号真正落地——**这就给你弹二维码**，打开小红书 App 扫一下。

然后**直接进 `/redbeacon-login` 给这个新 id 登录**（按主入口「自动推进原则」，这是必需步骤，别征求同意）。登录成功后，由登录 skill 继续交棒到绑飞书表 → 定位 → 面板。

> 🔑 **多账号关键（开第 2、3… 个号时务必照做）**：全局 `readiness` 是「任一账号满足即 ready」的聚合判断——账号 1 配好后，再加账号 N，全局 readiness 仍是 `ready`，**不会自动发现新号没配**。所以开新号的 onboarding **一律用 per-账号判断**：
>
> ```bash
> redbeacon readiness --account-id {新id}
> ```
>
> 它只看这个号的进度（stage3 登录 → stage4 绑表 → stage5 定位 → ready）。**整条开号链路都用 `--account-id {新id}` 驱动并把 id 透传给每个子 skill**，直到这个号自己 `ready`。新号的步骤和 1 号完全一致（登录 → 绑表 → 定位 → 面板二次确认），唯一不同是**全局配置（AI / 飞书凭证 / 代理）已配过、不再重复**。

---

## 改备注名（rename / 改名 / 改备注）

```bash
redbeacon accounts patch --account-id {ID} --data '{"display_name": "新备注名"}'
```

改的是**备注名**（编号 id 不可改、始终是「{id}号」）。用户说「把1号改名叫XX」「给副业号换个名」都走这里。清空备注传空字符串 `{"display_name": ""}`（清空后展示为「（未命名）」）。

---

## 改代理（proxy / 加代理 / 换代理）

> **账号不强制绑代理。** 账号就是账号，是否挂代理是发布时的选择，不是账号的必备属性。这里只是给「想给某个账号固定绑一个代理」的用户提供入口，绝大多数情况可以不设。

如果用户确实要给账号绑固定代理：

```bash
redbeacon accounts patch --account-id {ID} --data '{"proxy": "http://user:pass@host:port"}'
```

清空走 `{"proxy": ""}`。代理 IP 怎么拿、怎么验证（巨量引擎）走 `/redbeacon-config` 的 `test-proxy`。发布时是否走代理的开关属于发布环节，不在本 skill。

---

## 删除账号（delete / 删除 / 移除）

**不可恢复**，会连带级联删掉该账号的：内容（content_queue）、发布记录（publish_log）、选题（topic）、内容类型、提示词、策略（strategy）、图片策略与图片模板。运行中的会话会先自动停止。

删前先把"会损失什么"摆给用户看：

```bash
redbeacon accounts get --account-id {ID}
redbeacon content list --account-id {ID} --limit 100
```

把账号名、登录状态、以及大致内容条数列出来，然后二次确认：

> 确认删除「{账号名}」（ID={ID}）？
> 将一并清除：约 {N} 条内容、全部选题/策略/图片模板/发布记录。**不可恢复**。

用户明确确认后才执行：

```bash
redbeacon accounts delete --account-id {ID}
```

删完重新 `accounts list` 展示剩余账号。

---

## 查看详情（get / 详情）

```bash
redbeacon accounts get --account-id {ID}
```

展示：`id` / `display_name` / `login_status` / `session_running` / `proxy` / `feishu_app_token` / `feishu_table_id` / `feishu_user_id` / `auto_generate_enabled` / `generate_schedule_json`。

---

## 场景对照（别在本 skill 里越界做）

| 用户想干的 | 去哪个 skill |
|---|---|
| 建号 / 改名 / 改代理 / 删号 | **本 skill** |
| 给账号定位、生成选题、配排期 | `/redbeacon-locate` |
| 改定位 / 文案预设 / 图片预设 | `/redbeacon-strategy` |
| 「这期文案/图不行」诊断调参 | `/redbeacon-diagnose` |
| 扫码登录 / 退出 / 重登 | `/redbeacon-login` |
| 绑定该账号的飞书多维表格 | `/redbeacon-feishu` |
| 配 AI / 飞书 / 代理 | `/redbeacon-config` |

---

## 注意

- 所有命令成功走 stdout JSON、失败走 stderr `{"error","next"}`；失败时把 `error` 给用户看，按 `next` 提示自愈，别静默吞掉。
- 单账号场景（免费版常态）：列表只有一个账号时，后续操作默认就是它，不用反复问选哪个。
- 多账号场景下做任何针对性操作（改名/删除/详情），先让用户在列表里指明是哪个 ID。
