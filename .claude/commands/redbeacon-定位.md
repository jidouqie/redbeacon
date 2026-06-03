---
description: 账号定位 — 对话梳理赛道/受众/差异化/变现 → 写策略 → 初始化内容类型 → 生成选题入库
argument-hint: 无参数=从零给账号定位；多账号时说清是哪个（如「给账号2定位」）
---

> **【定位 skill】** 账号建好后给它"定性"。通过对话把账号方向定下来，写进策略，并生成一批选题灌进选题库——这是账号能产出内容的前提。
>
> 上一步是建号（`/redbeacon-accounts`），下一步是扫码登录（`/redbeacon-login`）。后续想单独改某一项（定位/文案预设/图片预设）走 `/redbeacon-策略`；觉得产出的文案/图不对劲走 `/redbeacon-诊断`。

---

## 前置：选账号 + 看是不是已有定位

```bash
redbeacon accounts list
```

- **0 个账号** → 还没建号，先去 `/redbeacon-accounts`，本 skill 到此为止。
- **1 个账号** → 自动用它，记为 `{ID}`，不用问。
- **多个账号** → 把列表给用户，让其指明给哪个账号定位（`$ARGUMENTS` 里已说明就直接用）。

确定 `{ID}` 后读现有策略：

```bash
redbeacon strategy get --account-id {ID}
```

- 返回 `{}` 或 `data.niche` 为空 → 全新账号，进「第一步」。
- 已有 `niche` → 告诉用户「检测到已有定位」，展示核心信息（niche / target_audience），问是**重新定位**还是**只改某部分**（只改某部分建议走 `/redbeacon-策略`，不用重跑全程）。

---

## 第一步：发现对话（核心，别一次抛所有问题）

**用自然对话逐步引导，每次只问一到两件事**，根据回答追问或转下一个话题。要摸清这五件事（顺序灵活）：

1. **赛道**：想做什么领域？（美食 / 健身 / 穿搭 / 职场 / 亲子 / 知识 / 本地生活 …）
2. **目标受众**：内容给谁看？他们的共同痛点或欲望是什么？
3. **差异化**：同赛道账号很多，你的独特角度 / 优势是什么？
4. **目标 / 变现**：做这个账号想达成什么？（涨粉 / 卖货 / 私域引流 / 个人品牌 / 纯记录）
5. **参考账号**（可选）：有没有想参考风格的账号？（只作文字风格参考，不调任何接口）

> 这是"联动数据"的源头——赛道、受众、差异化、痛点任何一处变动，最终文案都会跟着变。聊透一点，后面少返工。

### 顺带：引导用户发"喜欢的样子"（多模态抽取，强烈建议）

你（运行此 skill 的客户端）能读图、能读长文案。趁定位对话，主动邀请用户把**喜欢的封面图**和**喜欢的笔记文案**直接发到聊天窗——这是把抽象偏好变具体的最快方式：

- **用户发参考封面图** → 你看图，反推出**视觉风格的一句大白话描述**：主体 / 构图 / 色调 / 留白 / 质感（如「明亮清新、ins 简约、主体居中、上方留白」）。第二步连同定位一起，用 `redbeacon strategy image-set` 落库（`prompt_template` 只写这句人话，**别写 `{niche}`/`{title}` 占位符或"竖版3:4"等格式词，程序会自动补**；要 AI 生图再配 `mode=ai` + `ai_model`）。
- **用户发参考文案**（喜欢的博主笔记）→ 你抽象出风格：语气、句式长短、开场套路、分段方式、emoji 习惯、有无人设口头禅。把能映射到定位字段的填进去（`tone`/`opening_style`/`format_style`/`emoji_usage`）；更具体的"某类内容怎么写"用一句人话留到第三步 `strategy prompt-set` 写进对应内容类型（写人话，不写 JSON/占位符）。

> 图片只在对话里被你读懂，不会进 CLI；CLI 里存的永远是你抽象出来的**文本提示词**。用户没有参考样例也没关系，跳过即可，靠问答把风格说清楚也行。

---

## 第二步：生成定位草稿 → 确认 → 写入

根据对话整理成一份定位方案，清晰展示给用户：

```
【核心定位】一句话：专注 [X] 的账号，帮 [目标受众] 实现 [核心价值]
【目标受众】年龄/身份 · 核心痛点 · 使用场景
【差异化】和同类账号的本质区别
【内容调性】文字风格关键词 · 视觉风格关键词
【内容支柱】3-4 个方向
【痛点切入】最容易戳中受众的 3-5 个话题方向
```

问一句：**「这个方向准吗？要调哪里？」** 改到用户确认，再写入策略：

```bash
redbeacon strategy patch --account-id {ID} --data '{
  "niche": "赛道",
  "target_audience": "受众画像",
  "competitive_advantage": "差异化优势",
  "monetization": "变现路径",
  "content_pillars": [{"name":"方向1","description":"说明"},{"name":"方向2","description":"说明"},{"name":"方向3","description":"说明"}],
  "pain_points": ["痛点1","痛点2","痛点3"],
  "tone": "亲切自然，像朋友分享而非说教",
  "opening_style": "痛点戳入",
  "format_style": "分点列举",
  "emoji_usage": "适量",
  "content_length": "300-500字",
  "visual_theme": "简洁高级感",
  "forbidden_words": []
}'
```

> 写入成功后告知：✓ 账号定位已保存。
>
> **真正进文案生成的字段**：niche / target_audience / tone / opening_style / format_style / emoji_usage / content_pillars / pain_points / forbidden_words（visual_theme 影响配图）。其余（competitive_advantage / monetization / content_length）作为上下文留存。改这些将来走 `/redbeacon-策略`。

---

## 第三步：初始化内容类型

```bash
redbeacon topics types-init --account-id {ID}
```

播种三类内容类型（已存在则跳过）：**干货科普 / 痛点解析 / 经验分享**。

---

## 第四步：生成选题矩阵 → 确认 → 批量入库

基于已确认的定位，生成 **15-18 个选题**，分到三类，每条一句话、25 字内、可直接作为创作起点：

- **干货科普（6个）**：解决具体问题 / 步骤指南 / 对比 / 避坑清单
- **痛点解析（6个）**：戳痛点 / 踩坑经历 / 反共识 / 真实困境
- **经验分享（5-6个）**：亲身经历 / 成长故事 / before-after / 阶段总结

展示给用户，问：**「这些方向合适吗？要删要补尽管说。」** 用户删减后**至少保留 10 条**，不足就主动补到 10。

确认后按类型批量写入（用 stdin 喂多行，中文最稳）：

```bash
redbeacon topics batch --account-id {ID} --type "干货科普" <<'EOF'
选题1
选题2
EOF

redbeacon topics batch --account-id {ID} --type "痛点解析" <<'EOF'
选题1
选题2
EOF

redbeacon topics batch --account-id {ID} --type "经验分享" <<'EOF'
选题1
选题2
EOF
```

写完核对数量：

```bash
redbeacon topics stats --account-id {ID}
```

- `unused >= 10` → ✓ 告知已入库 N 条选题。
- `unused < 10` → 再生成补到 ≥ 10，追加 `topics batch`。

---

## 第五步：输出账号策略卡

全部完成后给一张可截图的策略卡：

```
━━━━━━━━━━━━━━━━━━━━
📋 账号策略卡（{账号名}）
━━━━━━━━━━━━━━━━━━━━
【定位】一句话定位
【目标受众】画像
【差异化】角度
【内容支柱】• 支柱1  • 支柱2  • 支柱3
【选题库】已入库 N 条 / 三类
━━━━━━━━━━━━━━━━━━━━
```

然后给下一步（按 readiness 顺序，定位之后是登录）：

```bash
redbeacon readiness
```

> 定位完成！下一步：
> - **`/redbeacon-login`** 扫码登录这个账号（readiness 的 stage4）
> - 登录后配飞书多维表格 `/redbeacon-feishu`
> - 全部就绪后 `/redbeacon-generate` 生成内容（生成是手动命令触发，本工具无后台自动排期）

---

## 注意

- 没有任何自动排期 / 常驻服务，内容生成一律手动 `/redbeacon-generate` 触发，别向用户承诺"定时自动发"。
- 审核与改稿全在飞书多维表格，本地不存在审核环节，定位 skill 也不涉及审核。
- 命令失败走 stderr `{"error","next"}`，把 error 给用户看，按 next 自愈，别静默吞。
- `strategy patch` 是增量合并（只覆盖传入字段），所以单项调整可以只传那一个字段——这正是 `/redbeacon-策略` 的工作方式。
