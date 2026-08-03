---
name: source-command-redbeacon-accounts
description: "账号管理 — 列表 / 新建 / 改名 / 改代理 / 删除；新建即扫码登录小红书"
metadata:
  short-description: "账号管理"
---

> **运行前自检**：先执行 `redbeacon --version`。如果命令不存在，必须从中央 `https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com/projects/redbeacon/stable/latest.json` 精确读取 `installers/install.ps1` 或 `installers/install.sh` 的 `url` 并执行；不得猜测版本、zip 包名、节点地址或直接解压客户端。

> 🤝 **交互风格 = 像得力下属服务老板**：主动带领、别让用户懵；用户没熟之前你来引导，熟了就让他自然语言直说。
> - **全程人话**：给用户的回复不出现 /source-command-redbeacon-* 或 redbeacon xxx 这类命令名/斜杠（那是你后台执行的），用「我来帮你生成一篇」这种说法；除非用户主动要命令，否则别提、别列。
> - **一次只问一个问题，一次只推进一件事**：只要需要用户回应，就停在一个明确问题/动作上；给 2-3 个编号建议选项，推荐项标「推荐」，让用户回一个数字；不要把「选账号 + 选模式 + 填偏好」这类多题塞进同一轮。
> - **给选择必须编号 + 换行排版**，让用户回一个数字就行，例如：
>   ```
>   你想先做哪个？
>   1. 写一篇（我列选题你挑）
>   2. 先审那几篇待审的
>   3. 补一批选题
>   回数字就行，也可以直接跟我说。
>   ```
> - **把输入成本压到最小**：能给选项就别让用户打字，能一个数字就别让他写句子；该替他想的下一步你先想好、给推荐（标「推荐」）。
> - 用户**熟了会直接自然语言**提要求（「写第3条」「发出去」「换个标题」）→ 照做，别硬塞编号流程。

> **【账号 skill】** 小红书账号的 CRUD。**账号不是一条空记录，而是一组会互相影响文案产出的联动数据的载体**——新建账号后不留空壳，**立刻接着扫码登录**（`/source-command-redbeacon-xhslogin`）让账号落地。建号本身用户几乎无感，先把"扫码登录成功"这个实感给到他。
>
> 上一步是配置（`/source-command-redbeacon-config`），下一步是**登录**（`/source-command-redbeacon-xhslogin`）；之后的顺序是 登录 → 定位（`/source-command-redbeacon-locate`）。代理验证走 `/source-command-redbeacon-config` 的 `test-proxy`。
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

看完按用户意图路由。**用户没明说要干啥时，别只问"要干啥"——把账号表亮出来，再给个编号菜单让他回数字**：

```
你的账号在上面。想做什么？
1. 加一个新账号
2. 给某个号改备注名
3. 给某个号设/换代理
4. 看某个号的详情
5. 删除某个号
回数字就行，也可以直接说（比如「给2号改名叫XX」）。
```

> 用户直接说意图（「加个号」「删3号」）就别走菜单，直接做。

---

## 新建账号（create / 加账号 / 新建）

> 当前**多账号免费、不限号、无门槛**（pre-launch 中间态）——直接建即可，不需要任何激活/购买。号数管控规则后续以平台为准，届时本 skill 再更新。

### ① 直接创建，让 CLI 决定能不能建

建号时可顺手起个**备注名**（多账号矩阵里靠它和编号区分，别让用户对着一堆"1号2号"发懵）。**别问开放式问句让用户对着空白发懵——先甩编号选项，用户回个数字就行**，想自己起名的走选项 2 的描述入口：

> 给这个号起个备注名吗？回个数字就行：
> 1. 先不起，**定位聊完我按赛道帮你拟一个**（推荐，省事）
> 2. 我自己起一个 —— 把名字发我（比如「副业搞钱手册」「职场干货号」）

- 用户回 **2** 或直接给了名字 → `redbeacon accounts create --name "<用户起的备注>"`
- 用户回 **1** 或说先不起 → `redbeacon accounts create`（备注先留空兜底，定位后自动生成，见 `/source-command-redbeacon-locate` 收尾）

```bash
redbeacon accounts create --name "副业搞钱手册"   # 起了备注
redbeacon accounts create                        # 没起，兜底「{id}号小红书」，定位后自动命名
```

- **成功**（返回含 `id`）→ 进 ②。建好后编号=`id`、备注=用户起的或兜底值，已自动播种默认图片策略和图片模板。
- 多账号现**免费可建、无上限**——建号不会再撞上限，正常建出来即可（无需激活/购买）。

### ② 强制交棒登录（关键，别省，也别问"要不要登录"）

建完**不要停在这里**、**也不要回头去定位**。建号本身用户几乎无感，紧接着就把"扫码登录成功"这个实感给到他——**直接交棒 `/source-command-redbeacon-xhslogin`**，并**带上这个新账号的 id**：

> **硬性完成条件**：`accounts create` 返回成功只算中间状态，不算本轮完成。拿到新账号 `id` 后，必须在**同一轮**立即执行 `redbeacon xhs-login start --account-id {新id}`，直到出现二维码、确认本来已登录，或返回明确错误；禁止只回复“账号已创建，请自行去登录”就结束。扫码与 cookie 保存必须调用 RedBeacon 现有登录能力，宿主 AI 不得用普通浏览器操作或文字回复模拟成功。

> ✓ {新id}号小红书已创建（备注：{用户起的或「未命名」}）。
> 先把小红书号扫码登录上，让账号真正落地——**这就给你弹二维码**，打开小红书 App 扫一下。

然后**直接进 `/source-command-redbeacon-xhslogin` 给这个新 id 登录**（按主入口「自动推进原则」，这是必需步骤，别征求同意）。登录成功后，由登录 skill 继续交棒到定位 → 面板。

> 🔑 **多账号关键（开第 2、3… 个号时务必照做）**：全局 `readiness` 是「任一账号满足即 ready」的聚合判断——账号 1 配好后，再加账号 N，全局 readiness 仍是 `ready`，**不会自动发现新号没配**。所以开新号的 onboarding **一律用 per-账号判断**：
>
> ```bash
> redbeacon readiness --account-id {新id}
> ```
>
> 它只看这个号的进度（stage3 登录 → stage5 定位 → ready）。**整条开号链路都用 `--account-id {新id}` 驱动并把 id 透传给每个子 skill**，直到这个号自己 `ready`。新号的步骤和 1 号完全一致（登录 → 定位 → 过目确认），唯一不同是**全局配置（平台登录 / 代理）已配过、不再重复**。

---

## 改备注名（rename / 改名 / 改备注）

```bash
redbeacon accounts patch --account-id {ID} --data-file account.json
```

```json
{"display_name": "新备注名"}
```

改的是**备注名**（编号 id 不可改、始终是「{id}号」）。用户说「把1号改名叫XX」「给副业号换个名」都走这里。清空备注同样写进 `account.json`：`{"display_name": ""}`（清空后展示为「（未命名）」）。

---

## 改代理（proxy / 加代理 / 换代理）

> **账号不强制绑代理。** 账号就是账号，是否挂代理是发布时的选择，不是账号的必备属性。这里只是给「想给某个账号固定绑一个代理」的用户提供入口，绝大多数情况可以不设。

如果用户确实要给账号绑固定代理：

```bash
redbeacon accounts patch --account-id {ID} --data-file account.json
```

```json
{"proxy": "http://user:pass@host:port"}
```

清空走 `{"proxy": ""}`。代理 IP 怎么拿、怎么验证（巨量引擎）走 `/source-command-redbeacon-config` 的 `test-proxy`。发布时是否走代理的开关属于发布环节，不在本 skill。

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

展示：`id` / `display_name` / `login_status` / `session_running` / `proxy` 等。（返回里可能还带 `feishu_*` 字段，飞书搁置期本机模式下为空，念给用户时忽略。）

---

## 场景对照（别在本 skill 里越界做）

| 用户想干的 | 去哪个 skill |
|---|---|
| 建号 / 改名 / 改代理 / 删号 | **本 skill** |
| 给账号定位、生成选题、配排期 | `/source-command-redbeacon-locate` |
| 改定位 / 文案预设 / 图片预设 | `/source-command-redbeacon-strategy` |
| 「这期文案/图不行」诊断调参 | `/source-command-redbeacon-diagnose` |
| 扫码登录 / 退出 / 重登 | `/source-command-redbeacon-xhslogin` |
| 登录平台 / 代理 | `/source-command-redbeacon-config` |

---

## 注意

- 所有命令成功走 stdout JSON、失败走 stderr `{"error","next"}`；失败时把 `error` 给用户看，按 `next` 提示自愈，别静默吞掉。
- 单账号场景（常态）：列表只有一个账号时，后续操作默认就是它，不用反复问选哪个。
- 多账号场景下做任何针对性操作（改名/删除/详情），先让用户在列表里指明是哪个 ID。
