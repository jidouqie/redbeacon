# RedBeacon · CLI 命令能力总表

> ⚠️ **飞书暂时阉割（2026-07-06）**：客户端默认**纯本机**，UI 已藏掉数据源开关与飞书配置。
> 写 skill 时**先不接飞书**——`🔀 数据源` 一律按本机来，`feishu setup/test/perms`、`source` 这些命令
> 现阶段搁置（代码保留、以后线上模式再启）。第 9 组飞书命令**本阶段不用**。
>
> 📖 **配套全量手册**：每条命令的**完整参数 + 调用示例**见 [`RedBeacon-CLI命令手册.md`](./RedBeacon-CLI命令手册.md)（由解析器自动生成，85 条全覆盖）。本表偏「速查语义」，手册偏「怎么调」。
>
> **这是给 skill 编写用的主参照**。铁律：**UI 能干的，CLI 都能干**——CLI 是 skill 的地基，
> 纯对话能触达每一项能力。写 skill 时对着这张表就知道：某能力有没有 CLI 命令、命令长什么样、
> 读还是写、扣不扣算力点、随不随数据源切换、要不要交棒 UI。
>
> 所有命令输出 **JSON**（TTY 下 indent=2、管道下紧凑单行）；失败走 stderr 的 `{"error":...,"next":...}`。
> `--account-id` 几乎所有账号级命令必填。长文本参数支持 **stdin**（传 `-`），规避 shell 转义/长度限。
>
> **图例**：⚡=调平台扣算力点 · 👁=只读 · ✍️=写数据 · 🔀=行为随数据源(本机/飞书)切换 · 🤝=高信息密度、skill 宜深链交棒 UI（能力仍在 CLI，交棒是 UX 选择）。

---

## 1. 登录 / 配置 / 系统（不随数据源切换）

| 命令 | 干什么 | 类 | 关键参数 | 背后 core / 说明 |
|---|---|---|---|---|
| `login start` | 平台设备授权登录（device flow，不输账密） | ✍️ | `--force` 重登 | `session.begin/complete_platform_login` |
| `login status` | 看登录态 / 会员 / 剩余算力点 | 👁 | | `session.get_platform_status` |
| `login logout` | 退出平台 | ✍️ | | `session.logout_platform` |
| `checkin` | 打卡：拉会员状态 + **剩余算力点唯一来源** | 👁 | | 平台 `/device/checkin` |
| `doctor` | 平台连通性自检 | 👁 | | 排障用 |
| `config get/set/unset/list` | 读/写/**删**配置项（代理/平台域名等；unset=删行非设空） | 👁✍️ | `key` `value` | `config.py` |
| `config test-feishu` / `test-proxy` | 测飞书凭证 / 代理连通 | 👁 | | |
| `config feishu-users` | 列可作通知接收人的飞书用户 | 👁 | | |
| `source` | 看/切业务数据源（本机 SQLite / 飞书云端） | 👁✍️ | `local`\|`feishu` | 全局二选一，`composition` 据此注入 |
| `status` | 全局就绪/运营概览 | 👁 | | `dashboard.load_dashboard` |
| `readiness` | onboarding 进度（缺哪步） | 👁 | `--account-id` 可选 | 逐账号或全局 |
| `logs` | 看运行日志 | 👁 | `--tail N` | |
| `backup export/import` | 导出/导入工作数据（换机迁移） | 👁✍️ | `--out` / `--file --force` | CLI 独有运维 |
| `update` | 全量更新客户端 + CLI + skill | ✍️ | `--check` 只查 | |
| `setup` | 首装：下浏览器内核等 | ✍️ | | |
| `ui app` | 起本机操作台 / 深链交棒某页 | — | `--page <页名> --account-id` `--browser/--no-browser` | skill→UI 交棒入口 |
| `ui setup` | 首装引导（已改走对话） | — | | |

## 2. 账号（身份，始终本机）

| 命令 | 干什么 | 类 | 关键参数 | 背后 core |
|---|---|---|---|---|
| `accounts list` | 列所有账号 | 👁 | | `onboarding.list_managed_accounts` |
| `accounts get` | 看单账号 | 👁 | `--account-id` | |
| `accounts create` | 新建账号 | ✍️ | `--name` | `onboarding.create_account` |
| `accounts delete` | 删账号（连根拔：库行+本机数据+cookie+配图） | ✍️ | `--account-id` | `onboarding.delete_account` |
| `accounts patch` | 改账号（改名/代理…） | ✍️ | `--data '{...}'` | |
| `xhs-login start` | 弹二维码扫码登录小红书 | ✍️ | `--account-id` | `onboarding.begin/await_xhs_login` |
| `xhs-login status` / `verify` | 查登录态 / 发布前校验在线 | 👁 | `--account-id` | 掉线要重登 |
| `xhs-login delete` | 退出小红书登录态 | ✍️ | `--account-id` | `onboarding.logout_xhs` |

## 3. 定位 / 策略（账号变量，🔀 真源随数据源）

| 命令 | 干什么 | 类 | 关键参数 | 背后 core |
|---|---|---|---|---|
| `strategy get` | 读账号定位全档（赛道/受众/内容支柱…） | 👁🔀 | `--account-id` | `account_profile.get_profile` |
| `strategy patch` | 改定位任意字段（**26 项整档同一写口**） | ✍️🔀🤝 | `--data '{"field":"value"}'` | `account_profile.save_profile`（逐项编辑宜 UI 定位页） |
| `strategy image-get` | 看本地视觉素材半（卡片主题/参考图/模型） | 👁 | `--account-id` | 本地 image_strategy |
| `strategy image-set` | 设卡片主题 / 配图方式等 | ✍️ | `--data '{"card_theme":...}'` | |
| `strategy image-ref-add/list/clear/remove` | 账号级人物/风格参考图 增/查/清空/**删单张** | 👁✍️ | `--file` `--index` `--replace` `--keep-files` | 拷贝入库；remove 按路径或序号删一张 |
| `strategy prompt-*` | 〔已退役短路〕内容类型提示词，改走定位「内容支柱」 | — | | 提示信息 |

## 4. 选题（🔀 真源随数据源；补题 ⚡ 扣点）

| 命令 | 干什么 | 类 | 关键参数 | 背后 core |
|---|---|---|---|---|
| `topics list` | 列选题（按类型/阶段/域筛） | 👁🔀 | `--stage --type --domain --limit --offset` | `TopicAdminPort` |
| `topics stats` | 库存盘面（选题余量、按域聚合） | 👁🔀 | `--account-id` | `topic_manage.load_topic_board` |
| `topics add` | 手加一条选题（全字段） | ✍️🔀 | `--content --type --domain --idea…` | `add_manual_idea` |
| `topics batch` | 批量建题（stdin JSON/纯文本；去重） | ✍️🔀 | `--json` / `--text` `--stage` | `bulk_topics` |
| `topics edit` | 改某条（文本/阶段/优先级/域/brief…） | ✍️🔀 | `--id --stage --content …` | `edit_topic_brief` / `set_topic_stage` |
| `topics delete` | 删选题 | ✍️🔀 | `--ids recA,recB` / `--all` | `delete_topic` |
| **`topics suggest`** | **平台 AI 补一批候选**（不入库，返回给人挑） | 👁⚡🔀 | `--count --app-domain --idea` | `suggest_topics`（对应 UI「AI补题」） |
| **`topics accept`** | **把勾选候选写库**（阶段=选题，全字段） | ✍️🔀 | `--json`（stdin 读 suggest 的 items） | `accept_suggestions` |
| **`topics suggest-preview`** | 补题引导语**填充态**：拼出真会发给 AI 的提示词 | 👁🔀 | `--count --idea --template -` | `suggest_prompt_preview`（不扣点） |
| **`topics suggest-template get`** | 读 AI 补题自定义引导语（空=系统默认） | 👁 | `--account-id` | `get_suggest_template` |
| **`topics suggest-template set`** | 存/清补题引导语模板 | ✍️ | `--text -` / `--reset` | `save_suggest_template` |
| `topics inspire` | 旧名，现转 `topics suggest`（`--text`=补充想法） | 👁⚡🔀 | `--text` | 兼容别名 |

> 加粗行 = 本轮补齐（此前 CLI 缺、只有 UI 有）。补题候选流：`topics suggest > cand.json` → 挑/删 → `topics accept --json < cand.json`。

## 5. 方案（生成模板；始终本机，不随数据源）

| 命令 | 干什么 | 类 | 关键参数 | 背后 core |
|---|---|---|---|---|
| `plans list` | 列方案（含默认标记，不甩长模板） | 👁 | `--account-id` | `content_plan.list_plans` |
| `plans get` | 看某方案全文（含长模板） | 👁 | `--plan-id` | `get_plan` |
| `plans set-default` | 设账号默认方案 | ✍️ | `--plan-id` | `set_default` |
| **`plans save`** | **新建/编辑整套方案**（长模板走 stdin；编辑保留未给字段） | ✍️🤝 | `--plan-id`(空=新建) `--name --note-type --copy-template - --image-template - --image-mode --image-count --style-tendency --display-with-text` | `save_plan`（长模板可视化微调宜交棒 UI） |
| **`plans delete`** | **删方案**（内置只读不可删） | ✍️ | `--plan-id` | `delete_plan` |
| **`plans material`** | 方案参考图/产品图：挂图 / **删单张** / 清空（拷贝入库，回写 reference_images） | ✍️ | `--plan-id --file` / `--remove <路径>` / `--clear` / `--replace` | 本地落盘 + `save_plan` |
| **`plans meta`** | 建方案的合法取值（笔记类型/视觉风格库/占位符/内置种子） | 👁 | | `note_types`/`visual_styles`/`placeholders`/`builtin_seeds` |

> 笔记类型：`general` 通用图文 / `poster` 大字报 / `persona` 人物形象 / `selling` 带货。建方案前先 `plans meta` 拿合法取值。

## 6. 生成（⚡ 扣点；🔀 入审核表随数据源）

| 命令 | 干什么 | 类 | 关键参数 | 背后 core |
|---|---|---|---|---|
| `generate`（一把梭） | 文案+出图+渲卡+入审核表（带货自动走多图） | ✍️⚡🔀 | `--topic/--topic-record-id --plan-id --idea --image-mode …`（+全套选题 brief 字段） | `generate.generate_content` / `generate_selling_set` |
| **`generate --preview`** | **只写文案(≈1点)+组装最终出图提示词**，出草稿 JSON，不出图不入库 | 👁⚡ | 同上 | `generate.generate_copy`（对应 UI 预生成·看实发） |
| **`generate --commit`** | 拿草稿出图入库 | ✍️⚡🔀 | `--draft-file <preview输出> / -` | `generate.render_from_draft` |

> 两步流：`generate --preview … > draft.json`（核对标题/封面文案/`image_prompt_final`）→ `generate --commit --account-id N --draft-file draft.json`。取消则只花了文案那点。

## 7. 审稿（🔀 随数据源；重写 ⚡ 扣点）

| 命令 | 干什么 | 类 | 关键参数 | 背后 core |
|---|---|---|---|---|
| `review list` | 列待审 | 👁🔀 | `--account-id` | `review.list_pending_reviews` |
| `review submit` | 标通过 / 驳回（可带改动） | ✍️🔀 | `--record-id --decision --title --body --tags` | `submit_review` |
| `review send-back` | 把已通过待发稿打回未审核 | ✍️🔀 | `--record-id` | `publish.send_back_to_review` |
| `review reject-to-topic` | 驳回并退回选题库（不扣点） | ✍️🔀 | `--record-id` | `reject_to_topic` |
| `review rewrite` | 按修改意见让平台重写 | ✍️⚡🔀 | `--record-id --feedback` | `rewrite_review` |
| `review delete` | **彻底丢弃一条稿**（不退选题、不打回，直接删行） | ✍️🔀 | `--record-id` | `discard_review` |

## 8. 发布 / 内容归档（🔀 随数据源）

| 命令 | 干什么 | 类 | 关键参数 | 背后 core |
|---|---|---|---|---|
| `publish` | 发已通过内容到小红书（发前换 IP；`--dry-run` 只列不发） | ✍️🔀 | `--account-id` / `--all-accounts` / `--dry-run` | `publish.list_pending_publish` / `publish_one` |
| `content list` | 列内容（按状态） | 👁🔀 | `--status --limit --offset` | |
| `content get` | 看单条内容 | 👁🔀 | `--id` | |
| `content archive` | 列已发布归档（交底「最近发了哪些」） | 👁🔀 | `--account-id` | `publish.list_archive` |
| `content archive-edit` | 改一条已发布归档记录（标题/正文/标签/链接） | ✍️🔀 | `--record-id --title --body --tags --note-url` | `publish.edit_archive` |
| `content archive-delete` | 删一条已发布归档记录（只动归档表） | ✍️🔀 | `--record-id` | `publish.delete_archive` |
| `content feishu-push` | 把没推上飞书的孤儿补推 | ✍️ | `--account-id` | 对账兜底 |

## 9. 飞书绑表（每用户自带应用，CLI 直连不走平台）

| 命令 | 干什么 | 类 | 关键参数 | 背后 core |
|---|---|---|---|---|
| `feishu setup` | 绑表：**不传 `--app-token`=一键建四表并绑**；**传了=绑到已有 Base** | ✍️ | `--account-id --app-token` | `onboarding.create_and_bind_base` / `bind_account_base` |
| `feishu test` | 测该账号飞书连通（写测试行+发消息） | 👁 | `--account-id` | |
| `feishu perms` | 打印自建应用要开的权限 JSON（单一真源） | 👁 | | `feishu_api.permissions_json` |

---

## 附：skill 编写取数原则（配合本表）

- **「读」尽量都用 CLI**：让 skill 有眼睛才能交底/判断（几乎每个 👁 命令都值得给 skill 一条）。
- **「写」按信息密度劈**：一句话能说清的短动作（标通过/打回/设默认/改单个定位字段）直接 CLI；
  要在一堆字段/长模板间比对微调看实时效果的（🤝：整套方案模板、26 项定位逐项编辑），**深链交棒 UI**——
  但**能力本身 CLI 都有**（`plans save`/`strategy patch`），交棒是为体验、不是因为够不到。
- **⚡ 扣点命令**（`generate`、`generate --preview/--commit`、`topics suggest`、`review rewrite`）：
  执行前先跟用户确认，别在自动流程里默默烧点。
- **🔀 数据源**：选题/审稿/发布/内容/定位/生成入库 的落点随 `source`（本机/飞书）切换，core 用例无感；
  方案(plans)与平台登录/配置/备份**始终本机**、不随数据源变。
