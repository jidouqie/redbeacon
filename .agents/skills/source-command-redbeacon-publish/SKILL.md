---
name: source-command-redbeacon-publish
description: "发布已通过内容 — 从本机审核表读「通过」记录，浏览器自动化发到小红书；手动触发，无后台"
metadata:
  short-description: "发布已通过内容"
---

> **运行前自检**：先执行 `redbeacon --version`。如果命令不存在，必须从中央 `https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com/projects/redbeacon/stable/latest.json` 精确读取 `installers/install.ps1` 或 `installers/install.sh` 的 `url` 并执行；不得猜测版本、zip 包名、节点地址或直接解压客户端。

> 📦 **数据都在本机**：从**本机审核表**读标「通过」的记录发布，发布成功移入本机归档。无需飞书。（飞书云端源现阶段搁置，不用管。）

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

> **【发布 skill】** 把审核表里**标了「通过」**的内容真正发到小红书：下载图片 → 浏览器自动化填标题/正文/标签 → 发布（或按记录里的定时设置定时发）。
>
> 上一步是审核改稿、标「通过」（`/source-command-redbeacon-review`；内容由 `/source-command-redbeacon-generate` 生成后自动进审核表）。全程手动命令触发，无后台常驻/自动定时。

---

## 前置：选账号 + 两件事缺一不可

发布要同时满足：**① 账号小红书登录态在线、② 审核表里有标「通过」的记录**。

选账号：

```bash
redbeacon accounts list
```

0 个 → `/source-command-redbeacon-accounts`；1 个 → 自动用，记 `{ID}`；多个 → 让用户指明（`$ARGUMENTS` 已说明就直接用）。

**发布前必须先实测登录态——这是每次发布的固定第一步，不可跳过**（掉线会被静默跳过、白跑一趟，用户还以为发成功了）：

```bash
redbeacon xhs-login verify --account-id {ID}
```

- `{"logged_in":false}` → **账号掉线了**。明确告诉用户「账号已掉线，先去 `/source-command-redbeacon-xhslogin` 重新扫码登录」，**就此停下，不要继续发布**，等重登成功再回来发。
- `{"logged_in":true}` → 在线，继续。

> 标「通过」走 `/source-command-redbeacon-review`（我直接帮你标）或操作台审稿页；没有标「通过」的记录就没东西可发，先去审。

---

## 发布前确认（必做，先预览再发）

登录态 OK 后，**先用 dry-run 拉一份"即将发布什么 + 用什么设置发"给用户过目**，不要直接 `publish`：

> 💡 用户想**可视化地一条条看待发的、勾选着发**，可深链发布页交棒：`redbeacon ui app --detach --page 发布 --account-id {ID}`（网页支持勾选批量发、看图预览）。**要"就发吧"走命令更快，要挑挑拣拣走网页更直观**——按用户语气选。

```bash
redbeacon publish --account-id {ID} --dry-run
```

返回 `{"count","items":[{title,body_preview,image_count,schedule}],"config":{...}}`，**纯预览不发布**。把它**用人话**摆给用户，请他确认后再发：

> 准备发布 {count} 篇，发布设置如下，确认没问题我就发：
> - 《{title}》：{image_count} 张图，{schedule}（"立即发布"或具体时间）
> - 浏览器：{browser_visible? "会弹出窗口让你看到自动化过程" : "后台运行、不显示窗口"}
> - 会自动勾选「笔记含 AI 合成内容」声明：{mark_ai_generated? "是" : "否"}
> - 原创声明：{mark_original?"勾选":"不勾选"}　可见范围：{visibility}
> - 发布 IP：{proxy_rotate? "每篇自动换 IP（防多号关联）" : "本机直连不换 IP"}

**首次发布时一定要主动点明这两条**（哪怕用户没问）：
1. **默认会弹出浏览器窗口**显示整个自动化过程（方便你看着它操作、有异常能发现）。不想看、想让它后台静默跑，跟我说一声"发布别显示浏览器"即可。
2. **默认会勾选「含 AI 合成内容」声明**（小红书合规要求）。如不需要可让我关掉。

用户想改任何一项发布设置，用自然语言说，我帮你落库（**改一次长期生效**，下次不用再说）：

| 用户说 | 我执行 |
|---|---|
| 「发布别显示浏览器 / 后台跑」 | `config set browser_visible false` |
| 「发布要显示浏览器」（默认就是） | `config set browser_visible true` |
| 「别标 AI 内容了」 | `config set publish_is_ai_generated false` |
| 「勾上原创声明」 | `config set publish_is_original true` |
| 「设成仅自己可见 / 粉丝可见」 | `config set publish_visibility <可见范围>` |
| 发布时间（定时） | 在这条稿的「发布时间」字段填（操作台审稿页里改那一条），不在这里设 |

> 改完设置可以再跑一次 `--dry-run` 让用户看新设置生效了，再正式发。

---

## 确认后发布

预览摆给用户后，给个编号菜单让他拍板（发布是对外动作，必须用户点头）：

```
确认一下，{count} 篇就这么发？
1. 就这么发（推荐）
2. 改下设置再发 —— 比如别显示浏览器 / 改可见范围 / 别标 AI 内容
3. 先不发，我再想想
回数字就行，也可以直接说。
```

选 1（或用户直接说「发吧/发出去」）才执行：

```bash
redbeacon publish --account-id {ID}
```

这是**前台阻塞**命令：它会从审核表拉所有「通过」记录，逐条下载图片、用浏览器自动化发布，并把成功的记录移入归档。记录里若带了定时字段，会提交为定时发布。

按返回讲给用户：

- `{"ok":true,"published":N}`：
  - **N > 0** → ✓ 成功发布/提交了 N 篇。立即执行 `redbeacon ui app --detach --page 归档 --account-id {ID}`，把客户端置前到归档页，让用户看到结果；也可去小红书核对。
  - **N == 0** → 没东西可发。最可能两种原因，帮用户判断：
    1. **还没有标「通过」**的记录 → 先去 `/source-command-redbeacon-review` 审核标通过。
    2. 账号**掉线被跳过** → 回 `/source-command-redbeacon-xhslogin` 重登。
- 其它 `{"error":...}` → 把原因给用户（图片下载失败、小红书页面变动、风控等；部分会自动重试 3 次后才报）。

### 多账号一起发

```bash
redbeacon publish --all-accounts          # 依次发布所有账号
redbeacon publish --all-accounts --dry-run  # 先逐账号预览
```

> 多账号模式下账号**之间自动错峰**（间隔随机，基准 `publish_account_stagger` 秒）防关联；掉线的账号自动跳过。返回 `{"ok":true,"published":总数,"results":[{account_id,published/error}]}`。仍**无后台定时**。

> **发布节奏可调**（`/source-command-redbeacon-config set` 或面板）：`publish_min_interval`/`publish_max_interval`（同账号连发间隔秒，默认 30–90）、`publish_account_stagger`（账号间错峰秒，默认 120）。号多、怕限流就调大。

> **审稿改稿后卡片会自动跟上**：若你在审核里改了正文，且这篇是纯图文卡片，发布前 CLI 会按新正文**重渲卡片**（`publish_rerender_cards`，默认开）——不用手动重生成。AI 封面图不受影响、保持原样。

---

## 关于代理与定时（自动处理，简单说明即可）

- **代理（多账号防关联）**：若在 `/source-command-redbeacon-config` 配了代理**且开了 `proxy_auto_rotate`**，每次发布 CLI 会自动取新 IP →（开了测速则验一下）→ 用新 IP 重启会话再发，用完即废，让多个号不共用同一出口 IP。**没配代理或没开 auto_rotate 就直连发**，不报错。代理的获取/验证/开关都在 `/source-command-redbeacon-config`，本 skill 不管。多账号矩阵（尤其 10–20 个号以上）建议务必配上并开轮换。
- **定时**：是否定时由**那条稿的「发布时间」字段**决定（在操作台审稿页里填）；发布命令照此执行，不在 skill 里另设定时。**本工具没有后台调度**——定时是提交给小红书侧的定时发布，不是我们常驻在发。

---

## 场景对照（别越界）

| 用户想干的 | 去哪个 skill |
|---|---|
| 发布已通过内容 | **本 skill** |
| 查看/改/删已发布归档 | **本 skill**（见下「已发布归档」） |
| 审稿 / 改标题正文标签 / 标「通过」 | `/source-command-redbeacon-review` |
| 生成内容 | `/source-command-redbeacon-generate` |
| 扫码登录 / 重登 | `/source-command-redbeacon-xhslogin` |
| 配代理 / 验证代理 | `/source-command-redbeacon-config` |

---

## 已发布归档（查看 / 改 / 删）

发布成功的稿会移入**归档**（已发布内容的资产库、交底「最近发了哪些」用）：

```bash
redbeacon content archive --account-id {ID}                                          # 列已发布归档
redbeacon content archive-edit   --account-id {ID} --record-id {rid} --note-url "https://xhs/…"  # 补/改笔记链接、标题、正文、标签
redbeacon content archive-delete --account-id {ID} --record-id {rid}                  # 删一条归档记录
```

- **补笔记链接最常用**：发布后拿到小红书笔记链接，`archive-edit --note-url` 回填，方便日后复盘找回。也能改 `--title/--body/--tags`。
- **`archive-edit/archive-delete` 只动归档表**，**不影响已经发到小红书的那篇**（小红书上的内容删不掉、要用户自己去 App 删）。跟用户说清这点，别让他以为删归档=撤回笔记。
- **🗑️ `archive-delete` 删前跟用户确认**（不可恢复，但只是删本地归档记录）。

---

## 注意

- **只发审核表里标了「通过」的记录**。注意区分两件事：**内容要不要发**＝标「通过」就是确认，别再做一遍内容审核；**发布前确认**＝过一遍发布设置（浏览器/AI标记/定时/IP 等属性），这一步要做，但它确认的是"怎么发"，不是"要不要发这篇"。
- 登录态是硬前提：掉线的账号会被**跳过**（不报错、published 不计它），所以发布前 `verify` 一下最稳。
- 全程手动触发、前台阻塞，**无常驻服务、无后台自动发**；别向用户承诺"放着它自己定时发"。
- 命令成功走 stdout JSON、失败走 stderr `{"error","next"}`；把 error 给用户看，按 next 自愈，别静默吞。
