---
description: RedBeacon 主入口 — 自动判断你在哪一步，路由到对应能力；也可直说要干什么
argument-hint: 无参数=检测当前进度并给下一步；或直说意图（如「配置」「加账号」「定位」「文案不对劲」「发布」）
---

> **【主入口】** 不确定该用哪个能力时，从这里进。它会先看你的账号运作链路到哪一步了，再把你带到该去的子能力。
>
> 整条链路：**配置 → 建账号 → 定位 → 登录 → 飞书 → 生成 →（飞书审核改稿）→ 发布**。审核与改稿全在飞书多维表格，本地无审核。生成与发布都是手动命令触发，无后台常驻服务。

---

## 优先：用户已经明说要干什么 → 直接路由

| 用户意图 | 去 |
|---|---|
| 配 AI / 飞书 / 代理，或「配置」 | `/redbeacon-config` |
| 建号 / 改名 / 删号 / 多账号解锁 | `/redbeacon-accounts` |
| 给账号定位、生成选题（首次定性） | `/redbeacon-定位` |
| 改定位 / 文案预设 / 图片预设（单点微调） | `/redbeacon-策略` |
| 想直观地看/改账号配置（弹网页面板） | `/redbeacon-面板` |
| 「看下整体情况 / 各账号怎么样了 / 全局概览」 | 弹**运营看板**（见下） |
| 「文案不行 / 图不对 / 跑题」找原因 | `/redbeacon-诊断` |
| 扫码登录小红书 | `/redbeacon-login` |
| 绑定账号的飞书多维表格 | `/redbeacon-feishu` |
| 生成内容 | `/redbeacon-generate` |
| 发布已通过内容 | `/redbeacon-publish` |

意图明确就别跑检测，直接进对应 skill。

---

## 否则：检测当前进度，给下一步

```bash
redbeacon readiness
```

按返回的 `stage` 路由（每个 stage 代表"卡在这一步"）：

| stage | 含义 | 带用户去 |
|---|---|---|
| `stage1` | AI 没配 | `/redbeacon-config` |
| `stage2` | 没有账号 | `/redbeacon-accounts` |
| `stage3` | 账号没定位 | `/redbeacon-定位` |
| `stage4` | 账号没登录小红书 | `/redbeacon-login` |
| `stage5` | 飞书没配 | `/redbeacon-config`（飞书凭证）→ `/redbeacon-feishu`（绑表） |
| `ready` | 全就绪 | 见下 |

把 `readiness` 的 `reasons`（缺什么）和 `next`（建议命令）一并讲给用户，让他知道为什么去那一步。

**顺带看一眼 `update` 字段（升级提示）**：`readiness` 返回里带 `update`。若 `update.update_available == true`，**在带用户去 stage 之前，先用一句话告诉他有新版**，把 `update.notes` 转成人话，并主动提议帮他升级：

> 🔔 RedBeacon 有新版（{latest}）：{notes}。要我现在帮你升级吗？升级很快，不影响你已配置的账号和数据。

用户答应就执行升级（见下「升级」一节）。`update` 为 `null` 或 `update_available=false` 就别提，正常往下走。

**ready 状态**，给用户后续选择：

> 全部就绪 ✅ 你可以：
> - **`/redbeacon-generate`** 生成内容（生成后自动进飞书审核表）
> - 在飞书多维表格里审核 / 改标题文案标签 / 标「通过」
> - **`/redbeacon-publish`** 发布飞书里标了「通过」的内容
> - 觉得产出不对劲 → **`/redbeacon-诊断`**

---

## 运营看板（一眼看全部账号）

```bash
redbeacon ui dashboard
```

弹一个**只读**网页看板：所有账号的在线状态、定位、飞书绑定、内容数（待审/已发/失败）、可用选题余量，一屏看全。是本地一次性服务，用户点「关闭看板」或超时即退，**不是常驻服务**。

**前提：看板是给多账号用户的**。`redbeacon license info` 若 `unlocked=false` 或账号数 ≤1，**不要弹看板**——单账号一句话就说清了，弹个总览反而累赘。只有「已解锁 且 账号 ≥2」才考虑弹。

**什么时候弹**（满足上面前提后）——两种情形主动弹，不用等用户点 skill：
1. **用户要求**："看下情况 / 各账号怎么样了 / 整体概览 / 哪个号该补题了"等。
2. **你认为有必要**：做完一批跨账号操作后想让用户总览；发现多个账号选题告急/掉线时；用户问"现在到哪了"且涉及多个账号时。先弹看板再用人话点一句重点（如"3 号掉线了、5 号选题只剩 2 条"）。

---

## 升级（CLI + skill 一起更新）

用户说「升级 RedBeacon / 更新一下 / 有新版帮我升」，或 `readiness` 报了 `update_available`，就执行：

```bash
redbeacon update
```

这一条会**同时**升级两层：闭源 CLI（走私有源 `uv tool upgrade`）+ 开源 skill（从 GitHub 拉最新 markdown 覆盖到本命令目录）。用完按返回讲人话：

- `{"ok":true,...}`：升级跑完了。看两块结果——
  - `was_outdated:false` → 本来就是最新版，没什么可升的，告诉用户「已经是最新版」。
  - `skill.updated`（刷新了哪些命令）+ `cli.ok`：都成功就说「CLI 和 skill 都更新好了（{current}→{latest}）」。
  - `cli.skipped:true` 或 `cli.ok:false`：CLI 那层没升成（多半是非标准安装），**skill 仍可能已更新**；把 `cli` 里的 `reason`/`hint` 转人话告诉用户，建议「重跑一次官网的安装命令」兜底，别假装全成了。
  - `skill.failed` 非空：有命令没拉下来（网络问题），让用户稍后再 `redbeacon update` 一次。
- `{"ok":false,"error":...}`：多半是拉不到版本清单（网络/官网问题）。如实告诉用户「暂时查不到更新，当前版本能正常用」，别卡着。

> 只想查有没有新版、先不升：`redbeacon update --check`（只比对版本，不动任何文件）。
> **skill 刷新会覆盖本地命令目录的 redbeacon*.md**——这些是开源文件，正常不该被用户改；若用户手改过会被覆盖，升级前可提醒一句。

---

## 注意

- 这是路由器，本身不直接改数据，只判断方向、把用户交给对应 skill。
- `readiness` 的阶段顺序是固定的：定位（stage3）排在登录（stage4）**之前**——先想清楚账号做什么，再扫码。
- 全流程无本地审核、无常驻服务，别向用户承诺"自动定时发布"。
