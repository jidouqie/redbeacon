---
description: 策略微调 — 单点调整账号定位 / 文案预设 / 图片预设，改哪项只动哪项
argument-hint: 说要改什么（如「改一下语气」「重写干货科普的文案提示词」「图片换成AI生图」）；不确定哪出问题用 /redbeacon-diagnose
---

> **【策略 skill】** 账号定位完成后的**单点微调**入口。定位、文案预设、图片预设是一组联动数据，任一处变动都会改变最终产出——本 skill 让你精准只改一项，不重跑定位全程。
>
> 不知道"文案不对劲"该改哪个旋钮 → 先走 `/redbeacon-diagnose`，它会反推问题节点再把你带回这里。

---

## 前置：选账号

```bash
redbeacon accounts list
```

0 个 → 先 `/redbeacon-accounts`。1 个 → 自动用，记 `{ID}`。多个 → 让用户指明。

---

## 三类可调数据（按用户意图进对应一类，别全问一遍）

| 用户想改 | 进哪段 |
|---|---|
| 赛道 / 受众 / 差异化 / 语气 / 开场 / 格式 / emoji / 字数 / 痛点 / 禁词 / 视觉风格 | **A 定位** |
| 某个内容类型产出的文案"骨架/风格"（提示词模板本身） | **B 文案预设** |
| 配图方式（卡片/AI图）、卡片主题、AI 图提示词、图片模型 | **C 图片预设** |

---

## A 段：改定位（strategy）

先看现状：

```bash
redbeacon strategy get --account-id {ID}
```

`data` 里是定位全字段。**真正进文案生成的**：`niche` `target_audience` `tone` `opening_style` `format_style` `emoji_usage` `content_length` `content_pillars` `competitive_advantage` `pain_points` `forbidden_words`；`visual_theme` 进配图；其余为上下文。

确认用户要改哪个字段后，**只传那一个（或几个）字段**（patch 是增量合并）：

```bash
redbeacon strategy patch --account-id {ID} --data '{"tone":"更犀利、直给"}'
```

> 改完告知：✓ 已更新 [字段]。这会影响下次 `/redbeacon-generate` 的产出。
>
> **改完顺手递一句面板**（用户多半想"看着确认 + 立刻试一篇"）：「想边看边调、改完直接生成一篇看效果，我给你开个面板？」点头就 `/redbeacon-panel`。别等用户主动问——他不知道有这东西。

---

## B 段：各类内容的写法（人话指引，不是程序模板）

每个内容类型（干货科普 / 痛点解析 / 经验分享）挂着一句**"这类内容怎么写"的人话指引**，空 = 用内置默认。

> ⚠️ **重要**：这里存的是给人看的一句话写作指引（如「把一个知识点讲透，多用步骤和清单」），**不是**完整提示词模板。JSON 输出契约、`{niche}` 等占位符、格式骨架，全部由程序在生成时自动拼上，你和用户都不用写、也写不进去。**绝不要往这里塞 `输出JSON`、`{占位符}`、"你是一个博主…"这类程序术语**——那是脏数据。

看哪些类型用了自定义、哪些还是默认：

```bash
redbeacon strategy prompt-list --account-id {ID}
```

（`using_default: true` = 还在用默认指引）

看某个类型当前的写法指引：

```bash
redbeacon strategy prompt-get --account-id {ID} --type "干货科普"
```

**用参考文案抽取**（多模态）：让用户把喜欢的笔记发进聊天窗，你读懂后**用一两句人话**概括出这类内容该怎么写（什么角度、什么结构、什么调性），写进去。

改写某个类型的写法指引（用 stdin 喂，避开转义坑），就写一句给人看的话：

```bash
redbeacon strategy prompt-set --account-id {ID} --type "干货科普" <<'EOF'
把一个知识点讲清楚讲透，多用具体步骤和清单，让读者看完能直接照做。
EOF
```

恢复成默认指引：

```bash
redbeacon strategy prompt-reset --account-id {ID} --type "干货科普"
```

---

## C 段：图片预设（image_strategy）

看现状（含已有图片模板列表）：

```bash
redbeacon strategy image-get --account-id {ID}
```

`strategy` 里关键字段：
- **mode**（配图方式，三选一）：`cards`（纯文字卡片，封面也是文字大字报，稳定省钱）/ `both`（AI 封面 + 文字卡片）/ `ai`（只出一张 AI 封面、无正文卡片）。
- **card_theme**：卡片配色，**合法值固定为**：`default`(优雅淡彩) / `neo-brutalism`(暗黑) / `botanical`(薄荷绿) / `professional`(海蓝) / `retro`(暖橙) / `sketch`(紫调) / `playful-geometric`(小红书红) / `random`(随机)。**别传别的值**。
- **prompt_template**（封面提示词）：AI 封面默认产出「**大字报**」——**标题大字由 AI 直接画进图**。推荐写成**结构化封面指令、带 `{标题}` 占位符**（每篇标题自动替换成封面大字）、并在提示词里**写死竖版 3:4**：
  `小红书竖版大字报封面，3:4 比例。整体风格：<视觉风格>。上方用厚重大字写出标题：「{标题}」，强对比、留白克制、高质量精美。`
  也可只写一句纯风格描述（不带占位符），程序会自动补「大字报骨架 + 标题大字 + 竖版3:4」。**宽高比靠提示词控制。**
- **ai_model**：这个账号 AI 生图用的模型名（留空则用全局 image_model）。

按需改（只传要改的字段）：

```bash
# 换成 AI 封面 + 卡片，给一条结构化大字报封面提示词
redbeacon strategy image-set --account-id {ID} --data '{"mode":"both","ai_model":"<图片模型>","prompt_template":"小红书竖版大字报封面，3:4 比例。整体风格：深色背景配亮色块、厚重大字、强对比、极简高级。上方用大字写出标题：「{标题}」，留白克制、精美。"}'

# 只换卡片配色
redbeacon strategy image-set --account-id {ID} --data '{"card_theme":"botanical"}'
```

**参考图（图生图）**——用户想用自己的照片/某张风格图当封面素材：

```bash
redbeacon strategy image-ref-add   --account-id {ID} --file "<本地图片路径>"   # 存进数据目录、登记
redbeacon strategy image-ref-list  --account-id {ID}                          # 看已存参考图
redbeacon strategy image-ref-clear --account-id {ID}                          # 清空
```

> **有参考图 = 自动图生图**（程序自动补"用参考图这个人/风格"的指令，**不用手写**），**没有 = 文生图**。
> ⚠️ **图生图保脸要用 flash 系模型**：`gemini-3.1-flash-image-preview`（nano-banana）实测完美还原本人；`gemini-3-pro-image-preview` 保脸偏弱。做人物封面就 `image-set` 把 `ai_model` 设成 flash 系。

**用参考封面图抽取风格**（多模态）：让用户把喜欢的封面图发进聊天窗，你看图反推出视觉风格描述，写进 `prompt_template`（带 `{标题}`）。若用户想直接复刻这张图的风格/构图，就把它 `image-ref-add` 存为参考图走图生图。

> 选 `ai` / `both` 前确认已配图片模型（`/redbeacon-config` 的 image_model）。否则 AI 生图会失败。

---

## 注意

- **改哪项只动哪项**，别顺手重配其他两类。这是本 skill 与 `/redbeacon-locate` 的根本分工。
- 所有改动都不会触发生成，要看效果让用户去 `/redbeacon-generate` 重新生成一篇对比。
- 命令失败走 stderr `{"error","next"}`，把 error 给用户、按 next 自愈。
- 不确定问题出在定位还是文案预设还是图片 → `/redbeacon-diagnose`。
