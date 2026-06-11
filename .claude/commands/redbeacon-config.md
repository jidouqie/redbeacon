---
description: 配置检测与设置 — AI（必需）+ 飞书（必需）+ 代理（可选），支持单项独立修改
argument-hint: 无参数=自动检测缺什么补什么；也可直接说要改哪一项（如「换文案模型」「重配飞书」）
---

> 🤝 **交互风格 = 像得力下属服务老板**：主动带领、别让用户懵；用户没熟之前你来引导，熟了就让他自然语言直说。
> - **全程人话**：给用户的回复不出现 /redbeacon-* 或 redbeacon xxx 这类命令名/斜杠（那是你后台执行的），用「我来帮你生成一篇」这种说法；除非用户主动要命令，否则别提、别列。
> - **给选择必须编号 + 换行排版**，让用户回一个数字就行，例如：
>   ```
>   你想先做哪个？
>   1. 写一篇（我列选题你挑）
>   2. 先审飞书里那几篇
>   3. 补一批选题
>   回数字就行，也可以直接跟我说。
>   ```
> - **把输入成本压到最小**：能给选项就别让用户打字，能一个数字就别让他写句子；该替他想的下一步你先想好、给推荐（标「推荐」）。
> - 用户**熟了会直接自然语言**提要求（「写第3条」「发出去」「换个标题」）→ 照做，别硬塞编号流程。

> **【配置 skill】** 入口触发时自动检测配置完整度。**AI（含图片模型）和飞书都是必需项**，代理可选、可跳过。全部配好后才能进入下一步（建账号 / 定位）。
>
> 审核与改稿全在飞书多维表格，本地不存在任何审核。

> 🚦 **硬规则（全量配置）**：进入全量配置后，**第一句话必须是问用户「网页向导 还是 对话配」**（见「第〇步」），**在用户选定之前，一条 `config set` 都不许跑、A/B/C 段一段都不许进**。不要默认走对话、不要替用户决定。单项修改（只改某一项）除外。

---

## 两种模式（先判断用户要哪种）

**① 全量配置**（入口自动检测触发，或用户说「帮我配置」「配一下」）→ **先让用户选配置方式**（见下方「第〇步：选配置方式」），再按所选方式补全。

**② 单项修改**（用户明确只想改某一项，如「换个文案模型」「API key 换了」「重配飞书」「改通知人」「加代理」）→ **直接跳到对应单项，只做那一件，不重跑其他段**，不进网页向导。CLI 每个配置项都是独立的 `config set`，不会牵连别的。

---

## 第〇步：选配置方式（仅全量配置，先问这一句）

全量配置入口触发后，**第一件事是问用户想怎么配**，不要默认闷头走对话、不要替他选。

**做法（两步，缺一不可）：**

**第 1 步 · 先用正文把区别讲清楚**（让用户带着信息选）：

> 「配置有两种方式，先说下区别：
>
> **① 网页向导（推荐）** — 我打开一个本地网页，AI / 飞书 / 代理一次性填完。密钥直接在浏览器里填、**不经过聊天框**，每项填完当场点按钮测连通，还有「复制飞书权限」「打开注册页」这些按钮帮你。**坐在电脑前就用它，最省事、隐私也好。**
>
> **② 对话配** — 我一步步问、你一条条发给我，边配边给你解释每一项是干嘛的。适合想边了解边配、或不方便开网页的时候。」

**第 2 步 · 结尾给一个编号菜单，让用户回一个数字**（按全局交互风格——编号 + 换行，最少输入）：

```
你想怎么配？
1. 网页配置 —— 打开本地网页一次性填完，密钥不经过聊天（推荐，坐在电脑前就用它）
2. 对话配置 —— 我一步步问、你一条条发，边配边解释
回 1 或 2 就行，也可以直接说。
```

> Claude Code 上可顺手用 `AskUserQuestion` 做成可点选卡片（体验更好）；Codex 等没有该工具的环境就用上面这个编号文本——**两端都得是"回个数字/一句话就行"**。

**分流：**
- 选 1（网页）→ 跳「网页向导分支」。
- 选 2（对话）→ 走下面的 A / B / C 三段对话流。
- 用户答得含糊 → 别擅自开配，再用同一个编号菜单问一次。

### 网页向导分支

```bash
redbeacon ui setup
```

会在浏览器打开本地配置页（一次性本地服务，仅 localhost）。告诉用户：

> 页面已打开。在里面分三块填：
> - **AI**：Base URL + API Key + 选文案模型/图片模型，每项填完点「测试」当场验连通；没有中转站可以点页面里的「推荐中转站」按钮去注册。
> - **飞书**：App ID + App Secret，右上角有「打开创建应用页」和「复制权限到剪贴板」两个按钮；填完点测试。
> - **代理**（可选）：巨量 getips 链接，右上角有注册入口；不需要可留空。
>
> **密钥只在浏览器里填，不用发给我**。全部填完点页面的「完成」，再回来告诉我一声。

用户填完回来后，**不要假设全配好了**，复查一遍：

```bash
redbeacon readiness
redbeacon config list
```

- 都齐 → 直接「配置就绪」，进下一步（建账号 / 定位）。
- 还缺哪项（向导里漏填或测试没过）→ 只针对缺的那项，用对话补（跳到对应的 A/B/C 段落里的那一小步），不整段重来。

> 向导只配 AI / 飞书 / 代理这三块全局配置。多维表格绑账号（`feishu setup --account-id N`）是建账号之后的事，不在向导里。

### 单项修改路由表

| 用户意图 | 只执行 |
|---|---|
| 改 Base URL | `config set ai_base_url <x>` → `config test-ai` |
| 改 API Key | `config set ai_api_key <x>` → `config test-ai` |
| 换文案模型 | `config models`（列给用户选）→ `config set ai_model <x>` → `config test-ai` |
| 换图片模型 | `config models` → `config set image_model <x>` → `config test-image` |
| 调发布节奏 | `config set publish_min_interval/publish_max_interval/publish_account_stagger <秒>`（防限流，号多调大） |
| 重配飞书机器人 | `config set feishu_app_id <x>` + `config set feishu_app_secret <x>` → `config test-feishu` |
| 改通知接收人 | `config feishu-users` → `config set feishu_user_id <ou_xxx>` |
| 改 / 加代理 | `config set proxy_api_url <x>` → `config test-proxy`（代理全部在本 skill 配，无独立代理命令） |

> 单项修改做完即结束，不要顺手把其他项也重问一遍。

---

## 对话分支 · 第零步：自动检测缺什么（选了「对话配」才走这里）

```bash
redbeacon readiness
redbeacon config list
```

按顺序逐项检测，缺哪段进哪段，已配好的跳过：

| 顺序 | 检测项 | 看哪里 | 必需性 |
|---|---|---|---|
| ① | AI Base URL | `config list` → `ai_base_url` | **必需** |
| ② | AI API Key | `config list` → `ai_api_key`=`__SET__` | **必需** |
| ③ | 文案模型 | `config list` → `ai_model` | **必需** |
| ④ | 图片生成模型 | `config list` → `image_model` | **必需（硬门槛，不可跳过）** |
| ⑤ | 飞书机器人 | `config list` → `feishu_app_id` + `feishu_app_secret`=`__SET__` | **必需** |
| ⑥ | 通知接收人 user ID | `config list` → `feishu_user_id` | **必需** |
| ⑦ | 代理 API 链接 | `config list` → `proxy_api_url` | **可选，可跳过** |

> readiness 的 `checks.ai_ok` = ①②③ 齐；`checks.feishu_ok` = ⑤ 齐。④⑥⑦ 不在 readiness 里，靠 `config list` 自己看。
> **「配置完成」判定 = AI ok + ④图片模型已设 + ⑤飞书 ok + ⑥user ID 已设**（⑦代理无论配没配都不阻塞）。

---

## A 段：AI 服务配置（必需）

> 🟢 **强烈推荐官方中转站 `aihub.jidouqie.com`**：本工具**只对它深度适配**（文案 + 三个生图模型实测全通）。**其他站点不保证工具正常运行**——这一点要在配 AI 时主动讲清，别等出问题。

### 1. 先问：有没有自己的 AI 中转站 / API key？

**主动询问，给编号选项让用户回数字**（别只抛开放问句）：

> AI 服务怎么配？回个数字就行：
> 1. 用官方推荐站 `aihub.jidouqie.com`（**推荐**，只对它深度适配、文案+生图实测全通，我弹注册页带你拿 Key）
> 2. 我有自己的中转站 —— 把 Base URL + API Key 发我（非官方站不保证生图正常，我会提醒）

- **没有 / 不确定 / 想要稳的** → 用官方站 `aihub.jidouqie.com`，Base URL 固定 `https://aihub.jidouqie.com/v1`，弹注册页引导拿 Key（见下）。**首选推这个。**
- **有自己的站，且坚持用** → 让用户提供 **Base URL + API Key**（可分两次发或一起发）。但**一旦 Base URL 不是 jidouqie，必须主动提醒一句**：
  > ⚠️ 你这个不是官方中转站。本工具只对 `aihub.jidouqie.com` 深度适配，其他站点不保证写文案/生图正常。先按你的试，**万一连不通或生图有问题，强烈建议换成官方站**。
  - Base URL：中转站填对应地址（一般 `/v1` 结尾）；API Key 不回显。
- **没有 / 不确定** → 直接弹官方站主页引导注册：

  ```bash
  open "https://aihub.jidouqie.com/"
  ```

  引导用户在站内注册 / 充值 / 拿 API Key。用这个中转站时 **Base URL 固定为 `https://aihub.jidouqie.com/v1`**，用户只需回传 API Key。

已设置过的项问「是否更新」。拿到后保存：

```bash
redbeacon config set ai_base_url "<URL>"
redbeacon config set ai_api_key "<KEY>"
```

### 2. 拉清单 → 选文案模型 + 图片模型（两个都必须配）

```bash
redbeacon config models
```

返回 `{"models": [...]}`，skill 按名字分类并推荐，用户拍板：

- **文案模型（ai_model，必需）**：chat 类关键词 `gpt-4o / gpt-4.1 / o1 / o3 / claude / deepseek / qwen / glm / moonshot / yi / ernie / hunyuan / step`。优先 `gpt-4o` / `claude-3.5+` / `deepseek-v3`。
- **图片模型（image_model，必需）**：image 类关键词 `dall-e / gpt-image / flux / stable-diffusion / sd3 / cogview / kolors / seedream / wanx / 即梦 / jimeng`。

**图片模型是硬门槛，必须配上：**
- 名字识别不出哪个是图片模型 → **把候选模型编号列出来**让用户回数字（别开放式问"哪个是图片模型"）：
  > 没认出哪个是生图模型，你回个数字：
  > 1. {模型A}
  > 2. {模型B}
  > 3. {模型C}
  用户回的那个配成 `image_model`。
- 清单里**确实没有任何图片模型** → 如实告知：当前 AI 服务不支持图片生成，需要换一个支持文生图的服务（中转站）才能继续。**不放行**，直到 `image_model` 配上为止。

### 3. 保存 + 验证

```bash
redbeacon config set ai_model "<文案模型>"
redbeacon config set image_model "<图片模型>"
redbeacon config test-ai
redbeacon config test-image
```

`test-ai` 返回 `{"ok": true, "reply": "ok", ...}` = 文案模型连通。失败 → 翻译 error，核对 base_url / key / model。
`test-image` 返回 `{"ok": true, ...}` = 图片模型能真的出图（会实调一次，约一张图成本）。失败要么连不通、要么该模型不支持文生图 → 按 error/next 换个图片模型（`config models` 重选）。**别等到生成时才发现图片模型是坏的**。

→ A 段完成（含图片模型且 test-image 通过），重跑 readiness。

---

## B 段：飞书配置（必需）

> 飞书多维表格 = 唯一审核面板 + 唯一发布数据源。生成内容自动推到飞书，人在飞书 APP 里看图、改标题/正文/标签、把「状态」改「通过」，`/redbeacon-publish` 只读「通过」记录发布。
>
> **门槛**：飞书开放平台创建自建应用 + 配权限 + 发布版本，约 5–10 分钟。

### 1. 创建机器人（自建应用）+ 配权限 + 发版

先打开飞书开放平台：

```bash
open "https://open.feishu.cn/app"
```

**权限 JSON 绝不要让用户从聊天窗里复制**——聊天窗复制会带换行、空格和多余字符，破坏 JSON 格式导致导入失败。skill 改为把权限写到桌面文件 + 复制进剪贴板 + 打开文件，用户直接 Cmd+V：

```bash
cat > ~/Desktop/飞书机器人权限.txt <<'EOF'
{"tenant":["bitable:app","bitable:app:readonly","base:app:copy","base:app:create","base:app:read","base:app:update","base:collaborator:create","base:collaborator:read","base:field:create","base:field:read","base:record:create","base:record:delete","base:record:read","base:record:retrieve","base:record:update","base:table:create","base:table:read","base:view:read","docs:permission.member:create","docs:permission.member:readonly","docs:permission.member:retrieve","docs:permission.member:transfer","drive:file","drive:file:download","drive:file:readonly","drive:file:upload","contact:user.base:readonly","contact:user.id:readonly","contact:user.employee_id:readonly","im:message","im:message:send_as_bot","im:message:send_multi_users","im:message:readonly","im:resource"],"user":["contact:user.employee_id:readonly"]}
EOF
pbcopy < ~/Desktop/飞书机器人权限.txt
open ~/Desktop/飞书机器人权限.txt
```

然后告诉用户在浏览器里完成：

> **① 创建企业自建应用** — 名称 RedBeacon（随意），确认创建。
>
> **② 配置权限** — 左侧「权限管理」→「批量导入权限」→ 在输入框里 **Cmd+V 直接粘贴**（权限 JSON 已复制到你剪贴板，同时也存到了桌面「飞书机器人权限.txt」，桌面文件已打开可对照）。
>
> **③ 发布版本**（权限发布后才生效）— 「版本管理与发布」→「创建版本」→ 版本号 `1.0.0` →「提交审核」→ 审核页点「通过」。
>
> **④ 复制凭证** — 「凭证与基础信息」→ 复制 **App ID**（`cli_xxxxxxxx`）和 **App Secret**。
>
> 完成后把 **App ID** 和 **App Secret** 发给我——**可以分两次发，也可以用逗号或空格隔开一起发，都行。**

### 2. 保存凭证 + 验证

```bash
redbeacon config set feishu_app_id "<APP_ID>"
redbeacon config set feishu_app_secret "<APP_SECRET>"
redbeacon config test-feishu
```

`test-feishu` 验证机器人凭证能换出 token。失败 → App ID/Secret 不完整，或版本没发布，让用户回 ②③ 检查。

> **权限是否配全，配置阶段不主动检测**（多维表格读写权限这里测不到）。后续在飞书相关操作（绑表 / 推送 / 发布）中如果报权限错，再回到本段引导用户重新检查权限并发版即可。

### 3. 选定通知接收人 user ID（必需）

```bash
redbeacon config feishu-users
```

按返回人数分流：

- **1 个** → 自动选定。
- **几个** → 列出来让用户选。
- **拉不到 / 人太多** → 引导：「打开飞书后台 → 通讯录找到自己 → 复制 user_id（`ou_` 开头）发给我」。

```bash
redbeacon config set feishu_user_id "<ou_xxx>"
```

> 多维表格「绑给哪个账号」是账号级操作（`feishu setup --account-id N`），建账号后做，不在这一步。

→ B 段完成，重跑 readiness。

---

## C 段：代理配置（可选，可跳过）

**先问用户，给编号选项**（代理=多账号防关联、每次发布换 IP，单账号一般用不上）：

> 要配代理吗？回个数字：
> 1. 不用（**推荐**，单账号/不做矩阵就不需要，跳过不影响后面）
> 2. 要配，我有巨量的 `getips` 链接 —— 发我
> 3. 要配，但还没代理账号 —— 我给你开注册页

- **回 1 / 不需要** → 不配，直接跳过，不影响进入下一步。
- **回 2 / 已有巨量获取链接** → 用户贴 `getips` 链接过来。
- **回 3 / 没有代理账号** → 打开邀请链接注册：

  ```bash
  open "https://www.juliangip.com/user/reg?inviteCode=1001359"
  ```

  注册后在巨量后台「提取代理 → API 提取」生成 `getips` 链接（带 trade_no + sign），贴过来。

拿到后，三条一起配（**第二条不开，代理等于白配**）：

```bash
redbeacon config set proxy_api_url "<巨量 getips 链接>"
redbeacon config set proxy_auto_rotate true    # ★必须开：发布时才会真的换 IP
redbeacon config set proxy_speed_test true     # 建议开：取到 IP 先对小红书测速，劣质自动丢弃换下一个
redbeacon config test-proxy
```

`{"ok": true, "proxy": "http://ip:port"}` = 通（测=真实发布取 IP，约 0.05 元/次）。失败 → 核对 trade_no / sign / 套餐余额。

> ⚠️ **关键**：`proxy_api_url` 只是"从哪取 IP"，真正"每次发布换 IP"由 `proxy_auto_rotate=true` 开关控制——只配链接不开轮换，发布时会直连、不换 IP。配代理就把 `proxy_auto_rotate` 一起开了。
>
> 发布时 CLI 会：取新 IP →（开了测速则）对小红书测速、不达标最多换 3 次 → 用新 IP 重启浏览器会话再发；用完即废、不存库。这是多账号防关联的核心（同一批号别共用一个 IP），10–20 个号以上尤其要开。

---

## 全部配好 → 进入下一步

判定「配置完成」：AI（含图片模型）+ 飞书 + user ID 都齐，代理已配或已明确跳过。

```bash
redbeacon readiness
```

- 仍 `stage1` → AI 没齐，回 A 段（注意 image_model 不在 readiness 里，单独看 `config list`）。
- 仍 `stage5` → 飞书没齐，回 B 段。
- 进到 `stage2` → 配置就绪。**按主入口「自动推进原则」，别问"要不要建账号"，直接交棒 `/redbeacon-accounts` 建号**（建完会自动接扫码登录 → 定位 → 绑飞书，一路到 ready）。

> 配置是 onboarding 的第一关，配齐就直接往下走，让用户一口气把环境建起来，别在每关之间反复征求同意。

---

## 错误处理

任何命令返回 `{"error": "...", "next": "..."}`：把 `error` 翻译给用户，自动跑 `next` 或提示用户该跑什么。
