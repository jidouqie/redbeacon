---
name: source-command-redbeacon-strategy
description: "策略微调 — 单点调整账号定位 / 文案预设 / 图片预设，改哪项只动哪项"
metadata:
  short-description: "策略微调"
---

> 📦 **数据都在本机**：定位/文案预设/视觉风格都存本地账号档案，无需飞书。`strategy get/patch/image-set` 读写这一份，本地读写恒可用。（飞书云端源现阶段搁置，不用管。）

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

> **【策略 skill】** 账号定位完成后的**单点微调**入口。定位、文案预设、图片预设是一组联动数据，任一处变动都会改变最终产出——本 skill 让你精准只改一项，不重跑定位全程。
>
> 🔴 **分工原则（重要，你是这里的导航员）**：
> - **短字段、一句话能说清的 → 你在对话里直接改**（改语气、换赛道、加个禁词、换卡片配色、换配图方式…）——这是你的强项，`strategy patch`/`image-set` 一条命令落库，别支使用户去网页点。
> - **整套「生成方案 / 文案提示词模板 / 视觉提示词模板」这种长模板 → 别在对话里硬拼，深链把用户送进网页方案页**（`redbeacon ui app --page 方案 --account-id {ID}`）。理由：长模板要一屏铺开、边改边看占位符高亮和实时预览，网页信息密度甩对话几条街；你在聊天里一段段念模板，用户根本对不齐。**这正是"该交棒就交棒"**——见下「D 段」。
>
> 不知道"文案不对劲"该改哪个旋钮 → 先走 `/source-command-redbeacon-diagnose`，它会反推问题节点再把你带回这里。

---

## 前置：选账号

```bash
redbeacon accounts list
```

0 个 → 先 `/source-command-redbeacon-accounts`。1 个 → 自动用，记 `{ID}`。多个 → 让用户指明。

---

## 三类可调数据（按用户意图进对应一类，别全问一遍）

用户已经说清改什么（「改语气」「换 AI 生图」）就**直接进对应一类**，下面这张表是你内部判断用的：

> ⚠️ 账号资料真源 = **本机账号档案**（A/B 段的定位/文案指南、C 段的默认配图方式/视觉风格/卡片配色/参考图，全在本地）。本地读写恒可用、不会因为网络失败。

| 用户想改 | 进哪段 |
|---|---|
| 赛道 / 受众 / 差异化 / 语气 / 开场 / 格式 / emoji / 字数 / 痛点 / 禁词 / 视觉风格 / 人设 / 对标 / 选题边界 | **A 定位**（对话直接改）|
| 全局写作风格（这个号所有内容怎么写，一段话） | **B 文案指南**（对话直接改）|
| 配图方式（卡片/AI图）、卡片主题、参考图、一句话风格 | **C 图片预设**（对话直接改）|
| **整套生成方案 / 文案提示词模板 / 视觉提示词模板（长模板、带 `{占位符}`）** | **D 方案页**（深链交棒 UI，别在对话里拼）|

**用户只说"想调下策略/改改设置"、没说改哪个时，给编号菜单让他挑**（别一上来全问）：

```
想调哪块？
1. 账号定位 —— 赛道/受众/语气/开场/字数/禁词/人设/对标/选题边界…（我直接帮你改）
2. 文案风格 —— 全局写作指引，一段话管全部（我直接帮你改）
3. 配图 —— 卡片配色 / AI 封面 / 参考图（我直接帮你改）
4. 整套生成方案 / 提示词模板 —— 想精调每篇怎么写、封面怎么出的那套模板（信息量大，我给你把网页方案页打开，边改边看效果）
回数字就行，也可以直接说（比如「语气更犀利点」「帮我调下文案提示词」）。
```

---

## A 段：改定位（strategy）

先看现状：

```bash
redbeacon strategy get --account-id {ID}
```

`strategy get` 直接返回账号定位字段（从本机账号档案组装）。**真正进文案生成的**：`niche` `target_audience` `tone` `opening_style` `format_style` `emoji_usage` `content_length` `content_pillars` `competitive_advantage` `pain_points` `forbidden_words`；`visual_theme` 进配图；其余（人设/对标/选题边界/账号阶段…）为账号上下文。

确认用户要改哪个字段后，**只传那一个（或几个）字段**（patch 是增量合并、写本机账号档案）：

```bash
redbeacon strategy patch --account-id {ID} --data-file strategy.json
```

```json
{"tone":"更犀利、直给"}
```

> 改完告知：✓ 已更新 [字段]。这会影响下次 `/source-command-redbeacon-generate` 的产出。
>
> **改完顺手提一句**：「想看效果就让我生成一篇试试。」想直接看产出就 `/source-command-redbeacon-generate` 生成一篇对比；想在操作台核一眼可 `redbeacon ui app --page 定位 --account-id {ID}`。

---

## B 段：文案指南（全局，一段话管全部内容）

> ⚠️ 写作指导**只有一层了**：全局「文案指南」(`copy_guide`)——这个号**所有内容**通用的写作指引，改一次全部生效。
> （旧的"按内容类型分别设写作要求"已下线：粒度太碎、收益低，统一收进这一段全局指南。`strategy prompt-set/get/list/reset` 跑了只会提示你来改 `copy_guide`。）

看现状（`copy_guide` 字段）：

```bash
redbeacon strategy get --account-id {ID}
```

改写——一段人话写作指引，从用户的话或他发的参考文案里提炼（结构/钩子/举证方式/口吻/差异化打法）：

```bash
redbeacon strategy patch --account-id {ID} --data-file strategy.json
```

```json
{"copy_guide": "每篇用因果结构开头戳痛点；多用具体数字和真实案例，少讲大道理；结尾留钩子引导评论；聪明朋友口吻不堆术语"}
```

> **定位时就该写上**（见 `/source-command-redbeacon-locate`）；用户反馈"还是空的 / 想改全局风格"就在这里写/改（写本机账号档案「文案指南」）。清空同样写进 `strategy.json`：`{"copy_guide": ""}`。
> **用参考文案抽取**（多模态）：让用户把喜欢的笔记发进聊天窗，你读懂后把"这个号该怎么写"概括进 `copy_guide`。
> ⚠️ 写**人话写作指引**（如「把知识点讲透、多用步骤清单」），**别塞 `输出JSON`、`{占位符}`、"你是一个博主…"** 这类程序术语——JSON 契约/占位符/骨架由程序自动拼，写进来是脏数据。

---

## C 段：图片预设（视觉拆两半）

> ⚠️ 视觉配置都在本机账号档案（`image-set` 一条命令照常传，底层各归各位）：
> - **默认配图方式（mode）+ 视觉风格那句人话（prompt_template）**：看现状用 `strategy get` 的 `default_image_mode`/`visual_theme`。
> - **卡片配色(card_theme) / 参考图 / AI 图模板**：看现状用 `image-get`。

看本地那半（卡片配色 + 参考图 + 图片模板列表）：

```bash
redbeacon strategy image-get --account-id {ID}
```

关键字段：
- **mode**（配图方式，三选一）：`cards`（纯文字卡片，封面也是文字大字报，稳定省钱）/ `both`（AI 封面 + 文字卡片）/ `ai`（只出一张 AI 封面、无正文卡片）。
- **card_theme**：卡片配色，**合法值固定为**：`default`(优雅淡彩) / `neo-brutalism`(暗黑) / `botanical`(薄荷绿) / `professional`(海蓝) / `retro`(暖橙) / `sketch`(紫调) / `playful-geometric`(小红书红) / `random`(随机)。**别传别的值**。
- **prompt_template**（封面提示词）：AI 封面默认产出「**大字报**」——**标题大字由 AI 直接画进图**。可只写一句人话视觉风格，程序会自动补「大字报骨架 + 标题大字 + 竖版 3:4」；如果要强控制，也可以写成**结构化封面指令、带 `{标题}` 占位符**（每篇标题自动替换成封面大字）、并写死竖版 3:4：
  `小红书竖版大字报封面，3:4 比例。整体风格：<视觉风格>。上方用厚重大字写出标题：「{标题}」，强对比、留白克制、高质量精美。`
  **宽高比靠提示词控制。**
- **生图模型**：由**平台侧按能力别名自动选定**，账号/用户**既不用选也无法手选**——你只管描述风格、提供参考图，模型平台定。

按需改（只传要改的字段）：

长中文/结构化视觉 JSON 优先写 UTF-8 文件（如 `image.json`）：

```bash
# 换成 AI 封面 + 卡片，给一条视觉风格或结构化大字报封面提示词（模型平台侧定，不用传）
redbeacon strategy image-set --account-id {ID} --data-file image.json

# 只换卡片配色
redbeacon strategy image-set --account-id {ID} --data-file image.json
```

```json
{"card_theme":"botanical"}
```

**参考图（图生图）**——用户想用自己的照片/某张风格图当封面素材：

```bash
redbeacon strategy image-ref-add    --account-id {ID} --file "<本地图片路径>"   # 存进数据目录、登记
redbeacon strategy image-ref-list   --account-id {ID}                          # 看已存参考图（带序号）
redbeacon strategy image-ref-remove --account-id {ID} --index 0                # 删单张（按 image-ref-list 的序号，或 --file 路径）
redbeacon strategy image-ref-clear  --account-id {ID}                          # 清空全部
```

> **🗑️ `image-ref-remove` / `image-ref-clear` 默认连磁盘文件一起删**（加 `--keep-files` 只删登记留文件）；删前跟用户确认一句。删单张用序号最省事（先 `image-ref-list` 把带序号的列给用户看，他说删第几张，你按 `--index` 删）。

> **有参考图 = 自动图生图**（程序自动补"用参考图这个人/风格"的指令，**不用手写**），**没有 = 文生图**。
> ⚠️ **图生图保脸的模型由平台侧定、你不用选**——做人物封面只要把本人形象照 `image-ref-add` 存为参考图，生成时自动走图生图保脸。

**用参考封面图抽取风格**（多模态）：让用户把喜欢的封面图发进聊天窗，你看图反推出视觉风格描述，写进 `prompt_template`（带 `{标题}`）。若用户想直接复刻这张图的风格/构图，就把它 `image-ref-add` 存为参考图走图生图。

> 选 `ai` / `both` 前确认**已登录平台 + 有算力点**（生图的前提；模型平台侧定，用户不选）。否则生图自动降级——只出文字卡、笔记照样进审核表，不会报错卡住。

---

## D 段：整套生成方案 / 提示词模板 → 交给 `/source-command-redbeacon-plans`

用户想调的是**「每篇文案具体怎么写、封面具体怎么出」那套带 `{占位符}` 的长模板**（不是 A/B/C 那些短字段）时——**这不是策略微调的活，是「方案」的活，交给专门的 `/source-command-redbeacon-plans`**。

- 那边能**看/建/改/删方案、设默认、传删产品图**（`plans save` 支持长模板走 stdin，能力都在 CLI）。
- 但**长模板反复比对微调，网页方案页最顺手**——`/source-command-redbeacon-plans` 会在合适时一句话把用户深链送进 `redbeacon ui app --page 方案 --account-id {ID}`：左边改模板、右边看这次真会发给 AI 的成品，改完保存回来接着生成。

> 简单收口：用户在策略里提到「想改整套文案/封面模板、想换默认方案、带货要传产品图」→ **一句「这些成套方案的事我用方案能力帮你弄」然后走 `/source-command-redbeacon-plans`**，别在策略这儿硬接长模板。

---

## 注意

- **改哪项只动哪项**，别顺手重配其他两类。这是本 skill 与 `/source-command-redbeacon-locate` 的根本分工。
- **短字段对话改、成套方案/长模板交给 `/source-command-redbeacon-plans`**（D 段）：别把整套提示词模板拉进对话一段段拼——那是「方案」能力的活，收口到 `/source-command-redbeacon-plans`。
- 所有改动都不会触发生成，要看效果让用户去 `/source-command-redbeacon-generate` 重新生成一篇对比。
- 命令失败走 stderr `{"error","next"}`，把 error 给用户、按 next 自愈。
- 不确定问题出在定位还是文案预设还是图片 → `/source-command-redbeacon-diagnose`。
