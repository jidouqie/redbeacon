---
description: 配置检测与设置 — 平台登录（必需）+ 代理（可选），支持单项独立修改
argument-hint: 无参数=自动检测缺什么补什么；也可直接说要改哪一项（如「重新登录平台」「加代理」）
---

> **运行前自检**：先执行 `redbeacon --version`。如果提示命令不存在，必须按系统调用官方 OSS 一键安装器后再继续：Windows PowerShell 用 `irm https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install.ps1 | iex`；macOS/Linux 用 `curl -fsSL https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install.sh | bash`。不得猜测、拼接或直接下载任何 zip 包名。

> 📦 **默认纯本机**：业务数据都在本地，**不需要配飞书**。配置只剩两件事：**平台登录（必需，管生图/计费）** + **代理（可选，多账号防关联）**。（飞书云端源现阶段搁置、配置入口已隐藏，以后线上模式再启。）

> 🤝 **交互风格 = 像得力下属服务老板**：主动带领、别让用户懵；用户没熟之前你来引导，熟了就让他自然语言直说。
> - **全程人话**：给用户的回复不出现 /redbeacon-* 或 redbeacon xxx 这类命令名/斜杠（那是你后台执行的）；除非用户主动要命令，否则别提、别列。
> - **一次只问一个问题，一次只推进一件事**：只要需要用户回应，就停在一个明确问题/动作上；给 2-3 个编号建议选项，推荐项标「推荐」，让用户回一个数字；不要把「选账号 + 选模式 + 填偏好」这类多题塞进同一轮。
> - **给选择必须编号 + 换行排版**，让用户回一个数字就行。
> - **把输入成本压到最小**：能给选项就别让用户打字；该替他想的下一步你先想好、给推荐（标「推荐」）。
> - 用户**熟了会直接自然语言**提要求 → 照做，别硬塞编号流程。

> **【配置 skill】** 入口触发时自动检测配置完整度。**只有平台登录是必需项**，代理可选、可跳过。配好平台登录就能进入下一步（建账号 / 定位）。
>
> 审核与改稿都在本机（`/redbeacon-review` 或操作台审稿页）。**文案/生图带令牌走平台扣点——客户端不需要任何 AI key / 中转站，也不需要配飞书。**

---

## 两种模式（先判断用户要哪种）

**① 全量配置**（入口自动检测触发，或用户说「帮我配置」）→ 按下方「检测 → A/B/C 段」逐项补全。
**② 单项修改**（用户只想改某一项，如「重新登录平台」「加代理」）→ **直接跳到对应单项，只做那一件**，不重跑其他段。

> ℹ️ 网页配置向导已下线（首装改走对话；网页 UX 后续重做）。本 skill 全程对话式带用户配。

### 单项修改路由表

| 用户意图 | 只执行 |
|---|---|
| 登录 / 重新登录平台 | `redbeacon login`（device flow，见 A 段）→ `redbeacon checkin` 看剩余算力点 |
| 查算力点 / 是否登录 | `redbeacon checkin`（拉剩余算力点）｜`redbeacon login status`（只看是否登录） |
| 退出平台登录 | `redbeacon login logout` |
| 改 / 加代理 | `config set proxy_api_url <x>` → `config test-proxy` |
| 调发布节奏 | `config set publish_min_interval/publish_max_interval/publish_account_stagger <秒>`（防限流，号多调大） |
| 看某项配置 / 列全部 | `config get <key>` ／ `config list`（加密项已设的回 `__SET__`） |
| **删掉某项配置**（不是设空、是删行） | `config unset <key>`（如清掉代理链接 `config unset proxy_api_url`） |

> 单项修改做完即结束，不要顺手把其他项也重问一遍。
> **`config unset` vs `config set key ""`**：unset 是删掉整行配置、彻底不存在；set 空值是留个空字符串。用户说「把代理删了/清掉这个配置」用 unset。

---

## 第零步：检测缺什么

```bash
redbeacon readiness
redbeacon login status
redbeacon config list
```

按顺序逐项检测，缺哪段进哪段，已好的跳过：

| 顺序 | 检测项 | 看哪里 | 必需性 |
|---|---|---|---|
| ① | 平台登录（设备令牌）| `login status` → `logged_in=true` ／ readiness `checks.platform_ok` | **必需** |
| ② | 代理 API 链接 | `config list` → `proxy_api_url` | **可选，可跳过** |

> readiness `stage1` = ①平台登录没齐。「配置完成」= ①平台已登录（②代理无论配没配都不阻塞）。

---

## A 段：登录数字员工平台（必需，人人必登）

> 🔗 平台登录也有**独立 skill** `/redbeacon-login`（专管平台登录/查会员/退出）。本段是 onboarding 一条龙里顺带做的平台登录；用户单独要「登录/重登/退出平台」时走 `/redbeacon-login` 即可，两边底层都是 `redbeacon login`。

> **为什么要登录**：RedBeacon 是「数字员工平台」上的员工。**生成内容（写文案 / 出图）会消耗算力点**、要带账号级令牌走平台，按实际用量结算（本地渲染文字卡这类不走平台的步骤不消耗）。**必须先登录一次**（首启轻打卡让平台看得见你、给你使用权）——这是 onboarding 的硬门槛，别做「按需登」。

弹设备授权（device flow，**不让用户输账号密码**）：

```bash
redbeacon login
```

它会先打印一段授权信息（`user_code` + 授权短链），并自动打开浏览器到授权页。**用人话告诉用户**：

> 给你弹了数字员工平台的授权页。在浏览器里（已登录平台的话）点「授权这台设备」就行，授权码是 **{user_code}**，对一下点确认。我在这儿等你点完。

命令会按 `interval` 自动轮询直到授权成功（10 分钟内有效）：
- 成功 → `{"logged_in":true,...}`。设备令牌已存本地（共享账号目录，**明文、不上传**）。
- 超时 / 被拒 / 连不上 → 按返回的 `error` 给人话，重跑 `redbeacon login`。

登录成功后**顺手打一次卡，把剩余算力点念给用户**（近乎零成本、不调 AI）：

```bash
redbeacon checkin
```

读 `membership.points.remaining`（剩余算力点，**点数只看 `membership.points`**）。**账号不再分等级/档位**——别念 `tier_name`/免费版/Pro/Max，也别提会员到期。用人话给用户一句：

> ✓ 平台已登录，剩余算力点 **{remaining}**。生成内容会消耗算力点，按实际用量结算——**别报"一篇几点""一张几点"这种固定数字**。

> ⚠️ 算力点用尽也能正常用——只是生图会降级（只出文字卡、笔记照样进审核表），可在网站充值算力点后再用。别把用户卡在这。

→ A 段完成（`login status` 为已登录），重跑 readiness。

---

## B 段：飞书配置 —— 现阶段搁置（跳过）

> 💤 **飞书云端同步现阶段搁置**：客户端默认纯本机，审核/选题/发布数据都在本地，**不需要配飞书**。别引导用户去配飞书/绑表。用户主动问「能不能用飞书」时，如实说一句「飞书云端同步这块先搁置了，现在数据都在你本机、直接用就行，不用配；以后上线云端模式会再开」，然后带回正常流程。

---

## C 段：代理配置（可选，可跳过）

**先问用户，给编号选项**（代理=多账号防关联、每次发布换 IP，单账号一般用不上）：

> 要配代理吗？回个数字：
> 1. 不用（**推荐**，单账号/不做矩阵就不需要，跳过不影响后面）
> 2. 要配，我有巨量的 `getips` 链接 —— 发我
> 3. 要配，但还没代理账号 —— 我给你开注册页

- **回 1 / 不需要** → 不配，跳过。
- **回 3 / 没账号** → 打开注册页：`open "https://www.juliangip.com/user/reg?inviteCode=1001359"`，注册后在巨量后台「提取代理 → API 提取」生成 `getips` 链接贴过来。

拿到后三条一起配（**第二条不开，代理等于白配**）：

```bash
redbeacon config set proxy_api_url "<巨量 getips 链接>"
redbeacon config set proxy_auto_rotate true    # ★必须开：发布时才会真的换 IP
redbeacon config set proxy_speed_test true     # 建议开：取到 IP 先对小红书测速，劣质自动丢弃换下一个
redbeacon config test-proxy
```

`{"ok": true, "proxy": "http://ip:port"}` = 通。失败 → 核对 trade_no / sign / 套餐余额。

---

## 全部配好 → 进入下一步

判定「配置完成」：平台已登录，代理已配或已明确跳过。

```bash
redbeacon readiness
```

- 仍 `stage1` → 平台没登录（回 A 段）。
- 进到 `stage2` → 配置就绪。**按主入口「自动推进原则」，直接交棒 `/redbeacon-accounts` 建号**（建完会自动接扫码登录 → 定位，一路到 ready），别问「要不要建账号」。

> 配置是 onboarding 第一关，配齐就直接往下走，别在每关之间反复征求同意。

---

## 错误处理

任何命令返回 `{"error": "...", "next": "..."}`：把 `error` 翻译给用户，自动跑 `next` 或提示用户该跑什么。平台类错误（登录失效 / 算力点不足）按 `error` 给人话——登录失效就重跑 `redbeacon login`。
