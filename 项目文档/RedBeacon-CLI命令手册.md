# RedBeacon · CLI 命令手册（全量）

> **skill 开发的实操参照**：每条命令的**用途 + 全部参数（用途/必填/可选值） + 调用示例**都在这。
> 参数与用法**由 argparse 解析器程序化生成**（不手抄、不臆造）；用途与示例为人工补注。
> 想快速看「某能力是读还是写、扣不扣点、随不随数据源、要不要交棒 UI」，看伴随文档
> [`RedBeacon-CLI命令能力总表.md`](./RedBeacon-CLI命令能力总表.md)。

## 全局约定（所有命令通用，下方各条不再重复）

- **输出**：一律 **JSON**。TTY 下 `indent=2`、中文不转义；**管道/重定向下紧凑单行**（机器友好）。
  进度信息走 **stderr**（`{"progress":n,"message":"…"}`），**别把 stderr 混进 stdout 再 `json.load`**——
  取结果只读 stdout（`2>/dev/null` 或分别重定向）。
- **失败**：非零退出 + stderr 打 `{"error":"…","next":"建议的下一步命令"}`。
- **账号**：几乎所有账号级命令要 `--account-id N`（`accounts list` 拿 id）。
- **长文本/多行参数**：支持 **stdin 管道**（值传 `-`，如 `--copy-template -`、`--text -`、`--draft-file -`），
  规避 shell 转义与命令行长度限。一条命令里**同时只有一个**参数能用 `-`（stdin 只能读一次）。
- **JSON 入参**：`--data '{"字段":"值"}'`（`strategy patch` / `image-set` / `accounts patch`）。
- **⚡ 扣算力点的命令**（执行前应先跟用户确认，别在自动流程里默默烧点）：
  `generate`（文案+出图）、`generate --preview`（≈文案 1 点）、`generate --commit`（出图）、
  `topics suggest` / `topics inspire`（≈1 点）、`review rewrite`（重写扣点）。**其余全部不扣点。**
- **🔀 数据源**：选题/审稿/发布/内容/归档/定位/生成入库 的落点随数据源（本机/飞书）切换，core 无感；
  **方案(plans)与平台登录/配置/备份始终本机**。⚠️ 飞书现阶段**搁置**，一律按本机（第「飞书绑表」组少用）。
- **破坏性命令**（`*delete`、`accounts delete`、`review delete`、`content archive-delete`、`plans/*/--clear`、
  `config unset`）：CLI 直接执行不二次确认——**删前确认由 skill 层负责**。

---

## 登录 · 打卡 · 自检

### `redbeacon login start`
平台设备授权登录（device flow，不输账号密码；浏览器里授权本机）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--force` |  | 忽略本地已有令牌，强制重新授权（换平台账号 / 重测登录用）（开关） |

```bash
redbeacon login start
```

### `redbeacon login status`
看平台登录态、会员、剩余算力点。

```bash
redbeacon login status
```

### `redbeacon login logout`
退出平台（选题/账号/内容数据不受影响，只是再生图要重登）。

```bash
redbeacon login logout
```

### `redbeacon checkin`
打卡：会员状态 + 剩余算力点的唯一来源。

```bash
redbeacon checkin
```

### `redbeacon doctor`
平台连通性自检（排障用）。

```bash
redbeacon doctor
```


## 账号管理

### `redbeacon accounts list`
列出所有小红书账号（含 session 在线标记）。

```bash
redbeacon accounts list
```

### `redbeacon accounts get`
看单个账号详情。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon accounts get --account-id 8
```

### `redbeacon accounts create`
新建一个账号（随后一般接扫码登录小红书）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--name` |  | 账号备注名（如「副业搞钱手册」；不传则留空=未命名，可后续起或按定位自动生成） |

```bash
redbeacon accounts create --name "美妆小号"
```

### `redbeacon accounts delete`
删账号（连根拔：DB 行 + 本机业务数据 + cookie/profile + 配图）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon accounts delete --account-id 8
```

### `redbeacon accounts patch`
改账号字段（改名、改代理等）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--data` | ✅ | JSON: {"field": "value"} |

```bash
redbeacon accounts patch --account-id 8 --data '{"display_name":"新名字"}'
```


## 小红书登录

### `redbeacon xhs-login start`
弹二维码，用小红书 App 扫码登录该账号。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon xhs-login start --account-id 8
```

### `redbeacon xhs-login verify`
实时校验该账号小红书在线态（发布前用）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon xhs-login verify --account-id 8
```

### `redbeacon xhs-login status`
查该账号小红书登录态。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon xhs-login status --account-id 8
```

### `redbeacon xhs-login delete`
退出该账号小红书登录态。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon xhs-login delete --account-id 8
```


## 定位 / 策略 / 视觉素材

### `redbeacon strategy get`
读账号定位全档（赛道/受众/内容支柱/文案·视觉预设…）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon strategy get --account-id 8
```

### `redbeacon strategy patch`
改定位任意字段——与 UI 定位页同一写口，26 项都能写。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--data` | ✅ | JSON: {"field": "value"} |

```bash
redbeacon strategy patch --account-id 8 --data '{"niche":"AI效率工具","target_audience":"职场新人"}'
```

### `redbeacon strategy prompt-list`
〔已退役短路〕内容类型提示词，改走定位「内容支柱」。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon strategy prompt-list --account-id 8
```

### `redbeacon strategy prompt-get`
〔已退役短路〕同上。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--type` | ✅ | 内容类型名 |

```bash
redbeacon strategy prompt-get --account-id 8 --type <值>
```

### `redbeacon strategy prompt-set`
〔已退役短路〕同上。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--type` | ✅ | 内容类型名 |
| `--text` |  | 提示词模板，不传则从 stdin 读取 |

```bash
redbeacon strategy prompt-set --account-id 8 --type <值>
```

### `redbeacon strategy prompt-reset`
〔已退役短路〕同上。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--type` | ✅ | 内容类型名 |

```bash
redbeacon strategy prompt-reset --account-id 8 --type <值>
```

### `redbeacon strategy image-get`
看账号本地视觉素材（卡片主题/参考图/模板/模型）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon strategy image-get --account-id 8
```

### `redbeacon strategy image-set`
设卡片主题 / 配图方式等视觉字段。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--data` | ✅ | JSON: {"mode":"cards|ai|both","card_theme":"...","prompt_template":"...","ai_model":"..."} |

```bash
redbeacon strategy image-set --account-id 8 --data '{"card_theme":"macaron"}'
```

### `redbeacon strategy image-ref-add`
给账号加一张图生图参考图（人像/风格；拷贝入库）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--file` | ✅ | 本地图片路径（人物写真 / 风格参考图） |
| `--replace` |  | 先清空已有参考图再加这一张（开关） |

```bash
redbeacon strategy image-ref-add --account-id 8 --file ~/Desktop/portrait.jpg
```

### `redbeacon strategy image-ref-list`
列账号已登记的参考图。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon strategy image-ref-list --account-id 8
```

### `redbeacon strategy image-ref-clear`
清空账号所有参考图（默认连磁盘文件删）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--keep-files` |  | 只清登记、保留磁盘文件（开关） |

```bash
redbeacon strategy image-ref-clear --account-id 8
```

### `redbeacon strategy image-ref-remove`
删账号单张参考图（按路径或序号）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--file` |  | 要删的参考图路径（来自 image-ref-list） |
| `--index` |  | 或按序号删（从 0 起，image-ref-list 的顺序） |
| `--keep-files` |  | 只删登记、保留磁盘文件（开关） |

```bash
redbeacon strategy image-ref-remove --account-id 8 --index 0
```


## 选题

### `redbeacon topics list`
列选题（可按内容类型/阶段/应用域筛）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--type` |  |  |
| `--stage` |  | 按阶段过滤：灵感 / 选题 / 弃用 |
| `--domain` |  | 按应用域过滤 |
| `--limit` |  |  |
| `--offset` |  |  |

```bash
redbeacon topics list --account-id 8
```

### `redbeacon topics add`
手加一条选题（全字段）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--content` | ✅ |  |
| `--type` | ✅ |  |
| `--stage` |  | 阶段（默认=选题；仿写/没拍板用 灵感） |
| `--domain` |  | 应用域（选题规划元数据，可选） |
| `--problem-type` |  | 问题类型（识别/盲区/决策/替代/反例/后果，可选） |
| `--idea` |  | 切入角度/落地要求，写进选题 brief（可选） |

```bash
redbeacon topics add --account-id 8 --content <值> --type <值>
```

### `redbeacon topics batch`
批量建题（stdin JSON 数组或纯文本每行一题；自动去重）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--type` |  | 纯文本模式的内容类型；--json 模式可省（每项自带 content_type） |
| `--stage` |  | 阶段（默认=选题；仿写灵感批量用 灵感） |
| `--json` |  | 从 stdin 读 JSON 数组，每项含 content/content_type/application_domain/problem_type/stage（开关） |
| `--text` |  | 选题内容，不传则从 stdin 读取 |

```bash
printf "AI 写周报的3个技巧\n用Claude做PPT\n" | redbeacon topics batch --account-id 8 --type 教程
```

### `redbeacon topics inspire`
旧命令名，现转 topics suggest（--text 当补充想法）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--text` |  |  |

```bash
redbeacon topics inspire --account-id 8
```

### `redbeacon topics suggest`
平台 AI 补一批选题候选（≈1 点，不入库，返回给人挑）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--count` |  | 补几条候选（1~20，默认10） |
| `--app-domain` |  | 限定使用场景/应用域（空=不限） |
| `--idea` |  | 这次的补充想法（优先照这个来） |

```bash
redbeacon topics suggest --account-id 8 --count 10 --idea "偏向职场副业"
```

### `redbeacon topics accept`
把勾选的候选写进选题库（阶段=选题，全字段落库）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--json` |  | 从 stdin 读候选 JSON 数组（topics suggest 输出的 items，每项含 text/内容类型等全字段）（开关） |

```bash
redbeacon topics suggest --account-id 8 > cand.json  # 挑/删后
cat cand.json | redbeacon topics accept --account-id 8 --json
```

### `redbeacon topics suggest-preview`
补题引导语「填充态」：拼出这次真会发给 AI 的完整提示词（不扣点）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--count` |  |  |
| `--idea` |  |  |
| `--template` |  | 要预览的引导语模板（传 - 从 stdin 读；不传=用账号已存的/系统默认） |

```bash
redbeacon topics suggest-preview --account-id 8
```

### `redbeacon topics suggest-template get`
读账号 AI 补题自定义引导语（空=系统默认）+ 可插入占位符。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon topics suggest-template get --account-id 8
```

### `redbeacon topics suggest-template set`
存/清账号 AI 补题引导语模板。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--text` |  | 新引导语模板；传 - 从 stdin 读 |
| `--reset` |  | 清空自定义、退回系统默认（开关） |

```bash
echo "你是{赛道}的选题官，补{补题数量}条…" | redbeacon topics suggest-template set --account-id 8 --text -
```

### `redbeacon topics stats`
选题库存盘面（选题余量、按应用域聚合）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon topics stats --account-id 8
```

### `redbeacon topics edit`
改某条选题（文本/阶段/优先级/应用域/brief 字段）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--id` | ✅ | 要修改的选题飞书 record_id（来自 topics list） |
| `--content` |  | 新的选题文本 |
| `--type` |  | 改归到的内容类型 |
| `--stage` |  | 改阶段：灵感 / 选题 / 弃用 |
| `--priority` |  | 改优先级：高 / 中 / 低 |
| `--domain` |  | 改应用域 |
| `--problem-type` |  | 改问题类型 |
| `--idea` |  | 切入角度，写进选题 brief（传空字符串清空） |
| `--outline` |  | 要点提纲，写进选题 brief（传空字符串清空） |

```bash
redbeacon topics edit --account-id 8 --id rec123 --stage 弃用
```

### `redbeacon topics reset`
〔已退役短路〕选题已无「已用/未用」态。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--type` |  |  |

```bash
redbeacon topics reset --account-id 8
```

### `redbeacon topics delete`
删选题（按 record_id，或按类型/全部）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--ids` |  | 逗号分隔的飞书 record_id，如 recA,recB |
| `--type` |  | 按内容类型删除 |
| `--all` |  | 删除该账号全部选题（防误删，需显式指定）（开关） |

```bash
redbeacon topics delete --account-id 8 --ids rec123,rec456
```

### `redbeacon topics types`
〔已退役短路〕本地内容类型管理，改走定位「内容支柱」/选题表单选。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon topics types --account-id 8
```

### `redbeacon topics types-init`
〔已退役短路〕同上。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon topics types-init --account-id 8
```

### `redbeacon topics types-add`
〔已退役短路〕同上。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--name` | ✅ | 新内容类型名 |
| `--prompt` |  | 该类型的文案风格指引（一句人话，可选） |

```bash
redbeacon topics types-add --account-id 8 --name <值>
```

### `redbeacon topics types-rename`
〔已退役短路〕同上。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--name` | ✅ | 原类型名 |
| `--to` | ✅ | 新类型名 |

```bash
redbeacon topics types-rename --account-id 8 --name <值> --to <值>
```

### `redbeacon topics types-delete`
〔已退役短路〕同上。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--name` | ✅ | 要删除的内容类型名 |
| `--force` |  | 该类型下还有未用选题时强制删除（开关） |

```bash
redbeacon topics types-delete --account-id 8 --name <值>
```


## 内容方案

### `redbeacon plans list`
列该账号所有方案（含默认标记，不甩长模板正文）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon plans list --account-id 8
```

### `redbeacon plans get`
看某方案全文（含长模板）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--plan-id` | ✅ |  |

```bash
redbeacon plans get --plan-id 28
```

### `redbeacon plans set-default`
设某方案为该账号默认。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--plan-id` | ✅ | 要设为默认的方案 id（来自 plans list） |

```bash
redbeacon plans set-default --account-id 8 --plan-id 28
```

### `redbeacon plans save`
新建/编辑整套方案模板（长模板走 stdin；编辑保留未给字段）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--plan-id` |  | 要编辑的方案 id；不传=新建 |
| `--name` |  | 方案名（新建必填；编辑不传则保留原名） |
| `--note-type` |  | 笔记类型：general 通用图文 / poster 大字报 / persona 人物形象 / selling 带货（可选：general / poster / selling / persona） |
| `--copy-template` |  | 文案提示词模板；传 - 从 stdin 读 |
| `--image-template` |  | 视觉提示词模板；传 - 从 stdin 读（与 --copy-template 不能同时用 -） |
| `--image-mode` |  | 配图方式（受类型约束，服务端归一）（可选：cards / ai / both） |
| `--image-count` |  | 带货出图张数（1~6，1 封面+其余展示） |
| `--style-tendency` |  | 带货风格倾向（空=AI 按品类自定） |
| `--display-with-text` |  | 带货展示图配卖点小字（开关） |
| `--no-display-with-text` |  | 带货展示图纯产品无字（开关） |

```bash
echo "标题《{标题}》\n{正文}" | redbeacon plans save --account-id 8 --name "日常版" --note-type general --copy-template -
```

### `redbeacon plans delete`
删方案（内置模板不可删）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--plan-id` | ✅ | 要删除的方案 id（内置模板不可删） |

```bash
redbeacon plans delete --plan-id 28
```

### `redbeacon plans material`
方案参考图/产品图：挂图 / 删单张 / 清空（拷贝入库，回写 reference_images）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--plan-id` | ✅ | 挂到哪套方案（带货=产品图 / 人物=形象图） |
| `--file` |  | 要挂的本地图片路径（png/jpg/webp，≤12MB） |
| `--replace` |  | 先清空该方案已有参考图再加这张（开关） |
| `--remove` |  | 删除该方案里这张参考图（传 reference_images 里的路径；连磁盘文件一起删） |
| `--clear` |  | 清空该方案所有参考图（连文件删）（开关） |

```bash
redbeacon plans material --account-id 8 --plan-id 28 --file ~/Desktop/product.jpg
redbeacon plans material --account-id 8 --plan-id 28 --remove /path/in/reference_images.jpg
```

### `redbeacon plans meta`
建方案的合法取值（笔记类型/视觉风格库/占位符/内置种子）——建方案前对照。

```bash
redbeacon plans meta
```


## 生成

### `redbeacon generate`
一次内容生成：写文案+出图+渲卡+入审核表（带货自动走多图）。两步模式见下方 --preview/--commit。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` |  |  |
| `--topic` |  | 本篇选题文本；配合 --topic-record-id 挑库里的题最全 |
| `--image-mode` |  | （可选：cards / ai / both） |
| `--content-type` |  | 选题内容类型标签（种草/教程/测评…） |
| `--idea` |  | 本篇用户想法/落地要求（最高优先级注入；不传则用选题自带的想法） |
| `--plan-id` |  | 用哪套方案（提示词模板）；不传=该号默认方案 |
| `--topic-record-id` |  | 选题在飞书选题表的 record_id；写成文案后删该行（§3.4） |
| `--app-domain` |  | 应用域，写进提示词占位符 + 审核表/归档表快照 |
| `--problem-type` |  | 选题的问题类型，写进提示词占位符 + 快照 |
| `--angle` |  | 选题切入角度，写进提示词占位符 + 快照 |
| `--outline` |  | 选题要点提纲，写进提示词占位符 + 快照 |
| `--value-point` |  | 选题价值点（读者能得到什么），写进提示词占位符 |
| `--hook` |  | 选题互动钩子（怎么引导互动），写进提示词占位符 |
| `--audience` |  | 选题聚焦人群（写给谁看），写进提示词占位符 |
| `--image-dir` |  | 选题配图方向，写进视觉提示词占位符 |
| `--note` |  | 选题备注，写进提示词占位符 |
| `--preview` |  | 只预生成文案+组装出图提示词（≈1点），输出草稿 JSON，不出图不入库（开关） |
| `--commit` |  | 拿 --draft-file 的草稿出图入库（配合先跑 --preview）（开关） |
| `--draft-file` |  | --commit 用：--preview 输出的草稿 JSON 路径；传 - 从 stdin 读 |

```bash
# 一把梭：
redbeacon generate --account-id 8 --topic-record-id rec123
# 两步（先看实发再花钱出图）：
redbeacon generate --account-id 8 --topic-record-id rec123 --preview > draft.json
redbeacon generate --account-id 8 --commit --draft-file draft.json
```


## 审稿

### `redbeacon review list`
列待审稿。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon review list --account-id 8
```

### `redbeacon review submit`
对一条稿标通过/驳回/只存改动（可同时改标题/正文/标签）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--record-id` | ✅ | 要处理的那条记录 record_id（来自 review list） |
| `--decision` | ✅ | approve=标通过 / reject=驳回 / save=只存改动仍待审（可选：approve / reject / save） |
| `--title` |  | 改标题（不给=沿用原值） |
| `--body` |  | 改正文（不给=沿用原值） |
| `--tags` |  | 改标签（不给=沿用原值） |

```bash
redbeacon review submit --account-id 8 --record-id rec9 --decision approve
```

### `redbeacon review send-back`
把一条已通过待发稿打回「未审核」再改。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--record-id` | ✅ | 要打回的记录 record_id（当前须在「通过」态） |

```bash
redbeacon review send-back --account-id 8 --record-id rec9
```

### `redbeacon review reject-to-topic`
驳回并退回选题库（从快照重建选题 + 删审核行；不扣点）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--record-id` | ✅ | 要退回选题的记录 record_id（从快照重建选题 + 删审核行） |

```bash
redbeacon review reject-to-topic --account-id 8 --record-id rec9
```

### `redbeacon review rewrite`
按修改意见让平台重写这篇（扣点）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--record-id` | ✅ |  |
| `--feedback` | ✅ | 修改意见（如「太啰嗦，开头改成提问式」） |

```bash
redbeacon review rewrite --account-id 8 --record-id rec9 --feedback "开头改成提问式，删掉第2段"
```

### `redbeacon review delete`
彻底丢弃一条稿（不退选题、不打回，直接从审核表删行）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--record-id` | ✅ | 要删除的记录 record_id（来自 review list；直接从审核表删行） |

```bash
redbeacon review delete --account-id 8 --record-id rec9
```


## 发布 / 内容 / 归档

### `redbeacon content list`
列内容（按状态筛）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--status` |  |  |
| `--limit` |  |  |
| `--offset` |  |  |

```bash
redbeacon content list --account-id 8
```

### `redbeacon content get`
看单条内容全文。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--id` | ✅ |  |

```bash
redbeacon content get --account-id 8 --id <值>
```

### `redbeacon content archive`
列已发布归档（交底「最近发了哪些」）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon content archive --account-id 8
```

### `redbeacon content archive-delete`
删一条已发布归档记录（只动归档表，不影响已发到小红书的那篇）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--record-id` | ✅ | 要删的归档记录 record_id（来自 content archive） |

```bash
redbeacon content archive-delete --account-id 8 --record-id rec9
```

### `redbeacon content archive-edit`
改一条已发布归档记录（标题/正文/标签/笔记链接）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--record-id` | ✅ |  |
| `--title` |  | 改标题 |
| `--body` |  | 改正文 |
| `--tags` |  | 改标签 |
| `--note-url` |  | 改笔记链接 |

```bash
redbeacon content archive-edit --account-id 8 --record-id rec9 --title "新标题"
```

### `redbeacon content feishu-push`
把生成了却没推上数据表的孤儿补推（对账兜底）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` |  |  |

```bash
redbeacon content feishu-push
```

### `redbeacon publish`
把审核「通过」的稿发到小红书（发前换 IP；--dry-run 只列不发）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` |  |  |
| `--all-accounts` |  | 依次发布所有账号（账号之间自动错峰）（开关） |
| `--dry-run` |  | 只预览即将发布的内容与发布配置，不实际发布（开关） |

```bash
redbeacon publish --account-id 8 --dry-run   # 先看要发什么
redbeacon publish --account-id 8
```


## 飞书绑表（现阶段搁置）

### `redbeacon feishu setup`
绑表：不传 --app-token=一键建四表并绑；传了=绑到已有 Base。（飞书搁置期少用）

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |
| `--app-token` |  | 绑到自己已有的某个 Base（不传=没绑过就一键建表、绑过就复用原表） |

```bash
redbeacon feishu setup --account-id 8
```

### `redbeacon feishu test`
测该账号飞书连通（写测试行+发消息）。（搁置期少用）

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` | ✅ |  |

```bash
redbeacon feishu test --account-id 8
```

### `redbeacon feishu perms`
打印自建应用要开的权限 JSON（单一真源）。（搁置期少用）

```bash
redbeacon feishu perms
```


## 配置 / 数据源

### `redbeacon config get`
读一个配置项。

| 参数 | 必填 | 说明 |
|---|---|---|
| `key` | ✅ |  |

```bash
redbeacon config get <key>
```

### `redbeacon config set`
写一个配置项（敏感字段自动加密存本机）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `key` | ✅ |  |
| `value` | ✅ |  |

```bash
redbeacon config set proxy_api_url 'https://…getips…'
```

### `redbeacon config unset`
彻底删一个配置项（删行，非设空）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `key` | ✅ |  |

```bash
redbeacon config unset proxy_api_url
```

### `redbeacon config list`
列所有配置（加密项已设的回传哨兵 __SET__）。

```bash
redbeacon config list
```

### `redbeacon config test-feishu`
验飞书 App ID/Secret。（搁置期少用）

```bash
redbeacon config test-feishu
```

### `redbeacon config test-proxy`
验代理 API 能否取到可用 IP（一次真实取 IP，约 0.05 元）。

```bash
redbeacon config test-proxy
```

### `redbeacon config feishu-users`
列可作通知接收人的飞书用户。（搁置期少用）

```bash
redbeacon config feishu-users
```

### `redbeacon source`
看/切业务数据源（local 本机 / feishu 云端；飞书搁置期恒 local）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `value` | ✅ | local=本机（默认）/ feishu=飞书云端；不带=看当前（可选：local / feishu） |

```bash
redbeacon source          # 看当前
redbeacon source local    # 切本机
```


## 系统 / UI / 运维

### `redbeacon ui app`
起本机操作台（原生窗口/浏览器）；--page 深链交棒某页。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--host` |  |  |
| `--port` |  |  |
| `--no-browser` |  | 只起服务、不开任何界面（调试/截图用）（开关） |
| `--browser` |  | 强制用系统浏览器打开（默认是无浏览器外壳的桌面客户端窗口）（开关） |
| `--page` |  | 直达某一页：看板/定位/选题/方案/生成/审稿/发布/归档/账号/设置（中英皆可） |
| `--account-id` |  | 深链时预选这个账号（多账号时用） |

```bash
redbeacon ui app --page 方案 --account-id 8   # 深链交棒到方案页
```

### `redbeacon ui setup`
首装引导（已改走对话）。

```bash
redbeacon ui setup
```

### `redbeacon update`
全量更新 RedBeacon：客户端整包、CLI 兼容通道、AI skill 一起处理。`--check` 只检查版本，不动文件。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--check` |  | 只检查有无新版，不执行升级（开关） |

```bash
redbeacon update
```

### `redbeacon setup`
首装：下载浏览器内核等。

```bash
redbeacon setup
```

### `redbeacon backup export`
导出工作数据（换机迁移）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--out` |  | 导出文件路径（默认当前目录带时间戳） |

```bash
redbeacon backup export
```

### `redbeacon backup import`
导入备份 JSON。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--file` | ✅ | 要导入的备份 JSON 路径 |
| `--force` |  | 当前库已有数据时强制覆盖（开关） |

```bash
redbeacon backup import --file ~/redbeacon-backup.json
```

### `redbeacon readiness`
onboarding 就绪进度（缺哪步）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--account-id` |  | 只看这一个账号的 onboarding 进度（多账号逐个开号用；不传=全局聚合判定） |

```bash
redbeacon readiness
```

### `redbeacon status`
全局运营概览（看板同口径）。

```bash
redbeacon status
```

### `redbeacon logs`
看运行日志尾部。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--tail` |  |  |

```bash
redbeacon logs
```
