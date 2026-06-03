---
description: 生成内容 — 从选题库取题 → AI 写文案 + 出图 → 入库并自动推飞书审核表；手动触发，无后台排期
argument-hint: 无参数=给当前账号生成一篇；可指定选题/内容类型/配图方式（如「用『新手避坑』这个题生成」「生成一篇纯卡片的」）
---

> **【生成 skill】** 跑一次内容生产：从账号选题库取一个未用选题 → 按定位用 AI 写文案 → 出图（AI 封面 / 文字卡片 / 两者）→ 入库 → **自动推到飞书审核表**等你审。
>
> 上一步是飞书绑表（`/redbeacon-feishu`），下一步是去飞书审核、然后 `/redbeacon-publish` 发布。**生成是手动命令触发的，没有任何后台自动排期/常驻服务**，别向用户承诺"定时自动生成"。

---

## 前置：确认就绪（少一环都生成不了）

```bash
redbeacon readiness
```

生成至少需要：AI 已配（stage1）、有账号（stage2）、账号有定位（stage3）。没到位就按 readiness 的 `stage` 把用户带去对应 skill，本 skill 暂停。

选账号（同其它 skill）：

```bash
redbeacon accounts list
```

- 0 个 → `/redbeacon-accounts`；1 个 → 自动用，记 `{ID}`；多个 → 让用户指明（`$ARGUMENTS` 已说明就直接用）。

> 选题库为空会直接生成失败（见下）。定位流程（`/redbeacon-定位`）会灌一批选题；想确认存量可 `redbeacon topics stats --account-id {ID}` 看 `unused`。

---

## 生成一篇

最简单：用账号默认配图方式、从选题库自动取题：

```bash
redbeacon generate --account-id {ID}
```

可选参数（按用户意图加，不需要就都不传）：

| 用户说 | 加参数 |
|---|---|
| 指定这一篇写什么题 | `--topic "选题原文"`（绕过选题库，不消耗库存） |
| 指定走哪类内容 | `--content-type "干货科普"`（取该类未用选题） |
| 围绕某个内容支柱 | `--pillar "支柱名"` |
| 这篇要纯文字卡片 / 纯 AI 封面 / 两者都要 | `--image-mode cards` / `ai` / `both` |

> **配图方式怎么定**：不传 `--image-mode` 时，CLI 用账号策略里的 `default_image_mode`。若账号也没设过，会报错并提示带上 `--image-mode`——这时问用户要哪种（纯卡片 `cards` / AI 封面 `ai` / 两者 `both`），或引导去 `/redbeacon-面板` 把默认配图方式定下来。**对用户说"配图方式"，别甩 `cards/ai/both` 这种字段词**。

---

## 跟进生成过程

`generate` 是**前台阻塞**命令，过程进度以 JSON 打到 **stderr**（形如 `{"progress":N,...}`：取选题 → 写文案 → 出图 → 渲染卡片 → 入库）。可以把阶段转成人话让用户知道在跑（"正在写文案…"/"正在出图…"），不用逐条念。

结果在 stdout：

- `{"ok":true,"content_id":N}` → 成功。内容已入库**并自动推送到飞书审核表**。告知用户：

  > ✓ 已生成一篇并送进飞书审核表。去飞书表里审核 / 改标题正文标签 / 标「通过」，然后回来用 **`/redbeacon-publish`** 发布。

- stderr `{"error":"选题库已耗尽…"}` → 选题用光了。带用户去 `/redbeacon-定位`（重新补一批选题）或直接 `--topic "..."` 临时指定一个题再生成。
- 其它 `{"error":...}` → 把原因给用户（常见：AI key 失效/模型不可用 → `/redbeacon-config` 改；图片模型不可用 → `/redbeacon-面板` 或 `/redbeacon-策略` 换图片模型）。

> 想一次生成多篇就重复跑 `generate`（每次取下一个未用选题）。别假装有"批量/定时"能力。

---

## 选题余量守护（未用选题 < 5 主动补，**强制**）

**每次生成成功后**（以及进入生成流程前）都查一次余量：

```bash
redbeacon topics stats --account-id {ID}
```

**只要 `unused < 5`，就主动在聊天里跟用户讲，并当场给 10 个候选选题让他挑**——不要等用户问、不要默默让它见底（CLI 虽然也会发飞书低余量提醒，但 skill 必须在对话里主动补题）：

> 📌 选题快用完了，只剩 {unused} 条。我按你的账号定位拟了 10 个新选题，挑你想要的（也可以删改或让我重拟）：

**怎么拟这 10 个（关键，必须贴合账号）**：先读定位作为依据——

```bash
redbeacon strategy get --account-id {ID}
redbeacon topics list --account-id {ID} --used 0   # 看现有未用题，避免重复
```

- 紧扣 `niche`（赛道）+ `target_audience`（受众）+ `pain_points`（**真实痛点**）+ `content_pillars`（内容支柱）+ 差异化角度来出题；每条一句话、≤25 字、可直接当创作起点。
- 分到三类内容类型（`干货科普` / `痛点解析` / `经验分享`，按 `topics types` 实际为准），分组展示、标好序号。
- **不与现有未用选题重复**。
- **定位不全时**（如 `pain_points`/`content_pillars` 为空，只有 niche）：仍基于 niche 和差异化尽力出题，但顺带提醒用户「定位只填了赛道，补全定位（`/redbeacon-定位`）后选题会更准」。

用户挑选 / 改完后，按类型批量入库（stdin 喂多行最稳）：

```bash
redbeacon topics batch --account-id {ID} --type "痛点解析" <<'EOF'
选中的选题1
选中的选题2
EOF
```

入库后再 `topics stats` 确认 `unused` 已补上来，告知用户。

---

## 想看生成了什么 / 查队列

```bash
redbeacon content list --account-id {ID} --limit 20
redbeacon content get --account-id {ID} --id {内容ID}
```

`status` 字段：`pending_review`=已推飞书待审、`published`=已发布等。**本地只读，改稿全在飞书**，没有本地审核/编辑命令。

若某篇生成成功但没进飞书（飞书当时抽风），用兜底批量补推：

```bash
redbeacon content feishu-push
```

---

## 场景对照（别越界）

| 用户想干的 | 去哪个 skill |
|---|---|
| 生成内容 | **本 skill** |
| 改文案风格/配图风格的"预设"（影响以后每次生成） | `/redbeacon-策略` 或 `/redbeacon-面板` |
| 「这篇文案/图不对劲」找原因调参 | `/redbeacon-诊断` |
| 补选题 / 重定位 | `/redbeacon-定位` |
| 发布已通过内容 | `/redbeacon-publish` |
| 审稿改稿标通过 | 在飞书表里做 |

---

## 注意

- 生成后内容**自动进飞书审核表**，不需要、也没有本地审核步骤。别在 skill 里做"先给用户看要不要通过"这种本地审核。
- 全程手动触发、前台阻塞，**无后台排期 / 无常驻服务**。
- 文案与图文卡片是**两套文本**：发布用纯文字+emoji 排版，卡片用 markdown 渲染——这是底层自动分的，对用户无感，不用解释，更不要把 markdown 符号塞进给用户看的文案里。
- 配图、emoji 用量、卡片配色等"长期偏好"在 `/redbeacon-面板` 或 `/redbeacon-策略` 设；本 skill 的 `--image-mode` 只是**这一篇**的临时覆盖。
- 命令成功走 stdout JSON、失败走 stderr `{"error","next"}`；把 error 给用户看，按 next 自愈。
