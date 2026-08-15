---
name: source-command-redbeacon-generate
description: "生成内容 — 按 AI 客户端实际能力优先使用宿主文案与生图；缺失能力按账号授权回退 RedBeacon 平台或本机文字卡"
metadata:
  short-description: "生成内容"
---

> **运行前自检**：先执行 `redbeacon --version`。如果命令不存在，必须从中央 `https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com/projects/redbeacon/stable/latest.json` 精确读取当前系统的 `installers/install.ps1` 或 `installers/install.sh` URL 并执行；不得猜版本、包名、节点地址或直接解压客户端。

# 目标

把用户一句“帮我写一篇/几篇”负责到底：自动选账号、选题和默认方案，逐篇生成文案与图片，安全写入本机审稿台，最后只打开一次审稿页。

- 当前宿主明确是 Codex 时：默认使用 Codex 自身的文案能力；当前会话有生图/改图工具时也优先使用。两者都成功则平台 AI 调用为 0、算力点消耗为 0。
- 其它受支持 AI 客户端：按当前会话真实可调用的能力逐项路由。能写文案就先用宿主文案；有可靠生图能力就用宿主图片；没有生图能力时只把图片阶段交给 RedBeacon 平台或本机文字卡兜底，不能因此把已经能由宿主完成的文案也改走平台。
- 任一宿主的某项能力不存在、失败或结果无法安全交接时：严格按该账号对应的文案/图片回退策略处理。未经允许不得调用收费平台能力。
- 不自动通过、不自动发布；成稿只进入审稿台。
- 生成是用户主动触发的前台动作，不承诺后台常驻或自动排期。

给用户只说人话，不暴露内部命令、状态名和文件协议；除非用户主动索要命令。需要用户选择时一次只问一个问题，给 2～3 个编号选项。

# 入口判断

1. 执行 `redbeacon accounts list`。
2. 没有账号：转账号管理。
3. 只有一个账号：直接使用。
4. 多个账号：若用户已明确账号就使用；否则只问一次账号选择，不能猜。
5. 用户未指定篇数时按 1 篇；允许 1～20 篇，超过 20 明确拒绝。
6. 用户未指定选题、方案或图片模式时不要逐项追问，交给 `creation batch-prepare` 自动选择最高优先级未预留选题、默认方案和账号默认图片方式。

运行 `redbeacon plans check --account-id {ID}`。发现疑似占位符只用一句话提醒，不能中止已经要求的创作。选题不足时转选题规划补充，不要静默减少篇数。

# 路线 A：AI 宿主能力创作（默认推荐）

Codex 默认走本路线。其它受支持 AI 客户端只要能可靠读取工作包、生成文案并通过本机文件交接结果，也走同一条宿主中立协议；不能因为“不是 Codex”就整篇改走平台。宿主身份只依据系统上下文，不用环境变量、用户输入或结果 JSON 伪造。

## 1. 创建稳定批次

为本次请求生成一个稳定 `batch_id`，并为每篇生成稳定且互不重复的 `generation_id`。同一次重试必须复用这些 ID，不能重新生成。

用宿主原生 JSON 序列化和文件写入能力创建 UTF-8 批次请求文件；不要把中文、多行或嵌套 JSON 塞进命令行，不要使用 Bash heredoc、`/tmp/` 或 PowerShell 不通用的重定向。若命令工具可直接、安全地提供 stdin，也可用 `--json -`。

批次请求使用对象字段：

- `host_id`: 当前真实宿主标识；Codex 使用 `codex`，其它宿主使用自己的稳定标识
- `batch_id`
- `generation_ids`: 与篇数等长
- `account_id`
- `count`: 1～20
- 用户明确给出时再加 `topic_record_ids`、`topics`、`topic_text`、`plan_id`、`idea`、`image_mode`

执行：

```text
redbeacon creation batch-prepare --json-file <批次请求文件>
```

批次创建或幂等复用后，立刻读取耐久恢复计划：

```text
redbeacon creation batch-recover --batch-id <batch_id>
```

按 `actions[].sequence` 严格串行处理；一篇完整成功、明确失败或取消后才开始下一篇，不能并发。恢复计划里的动作按下列规则执行：

- `item-prepare`：取得或复用工作包。
- `copy-validate`：使用返回的 `repair_prompt` 和原结果文件继续唯一一次文案修复。
- `copy-fallback` / `image-fallback`：回到对应的账号授权步骤，不重复已经成功的文案或图片工作。
- `image-prepare`：取得或复用原图片任务。
- `commit`：使用 `paths.result_file` 继续幂等提交，不重新写文案、不重新生图、不再次调用可能扣点的平台能力。
- `retry`：只在崩溃恢复后的新一轮、或用户明确要求重试时执行 `redbeacon creation retry --generation-id <generation_id>`，再按返回的 `action` 继续；同一轮已经明确失败的任务不能立刻无限重试。
- `done` / `cancelled`：跳过，不重做。

## 2. 为单篇取得工作包

```text
redbeacon creation item-prepare --generation-id <generation_id>
```

读取返回的 `work_file`。只把 `work.copy_task.system_prompt` 与 `work.copy_task.user_prompt` 用于当前这一篇，不自行重新拼定位、选题或方案。工作包里的路径由当前通道 CLI 分配，不能猜 `~/.redbeacon` 或 `~/.redbeacon_test`。

## 3. 当前 AI 宿主写文案并校验

按工作包提示词生成严格符合 `redbeacon_copy_v1` 的 JSON 文案。用当前宿主的 JSON 序列化能力把结果写到 `work.paths.result_file`，结构为：

```json
{
  "schema": "redbeacon-host-result/v1",
  "generation_id": "当前 generation_id",
  "host": {"id": "当前真实宿主标识", "capabilities": ["copy"]},
  "copy": {"attempt": 1, "raw_output": "这里是序列化后的 redbeacon_copy_v1 JSON 字符串"},
  "images": []
}
```

执行：

```text
redbeacon creation copy-validate --generation-id <generation_id> --json-file <result_file>
```

- `ok=true`：继续图片阶段。
- `can_repair=true`：只自动修复一次。把上一版原始输出、返回的 `repair_prompt` 和原工作包提示词交给当前宿主；不改变选题和核心意思。把 `attempt` 改为 2、覆写同一个结果文件，再校验一次。
- 第二次仍不合格且 `needs_fix=true`：账号策略已拒绝平台文案，保留待修稿并直接继续图片阶段。
- 第二次仍不合格且 `needs_fix=false`：执行 `redbeacon creation copy-fallback --generation-id <generation_id>`。
  - `consent_required=false`：按返回继续；账号策略为 `allow` 才会用平台文案，`deny` 会保全原稿并标记需要修正。
  - `consent_required=true`：此时才问用户一个问题：
    1. 仅本次使用平台文案（推荐）
    2. 以后此账号自动使用平台文案
    3. 不使用平台，保留为待修稿
    对应再次执行 `copy-fallback`，`--decision` 分别使用 `allow_once`、`allow_always`、`deny_once`。

不得在询问前调用平台，也不得无限让宿主重写。如果当前宿主连可靠文案输出或本机 JSON 交接都无法完成，才改走路线 B 的完整平台生成。

## 4. 当前 AI 宿主生图或安全回退

```text
redbeacon creation image-prepare --generation-id <generation_id>
```

- `image_plan.tasks` 为空：不调用任何生图工具，直接进入提交；RedBeacon 会生成本机文字卡。
- 有任务且当前 AI 客户端提供可靠的内置生图能力：按任务顺序调用内置生图工具。
  - 普通任务使用 `task.prompt` 生成。
  - `task.reference_images` 非空时，把这些本机绝对路径作为编辑参考图，不得忽略参考图另做一张。
  - 必须取得工具返回的明确本机图片绝对路径；临时 URL、聊天预览或 base64 不能写进结果协议。
  - 禁止把生图工具的原始文件直接复制、移动或链接到 `work.paths.asset_inbox`，也不要只改扩展名。原始文件路径只交给下一步 RedBeacon 图片接管命令读取。
  - 全部图片生成完成后，用宿主原生 JSON 序列化能力在 `work.paths.result_file` 同目录创建 UTF-8 图片交接文件：

```json
{
  "schema": "redbeacon-host-image-import/v1",
  "generation_id": "当前 generation_id",
  "images": [
    {"task_id": "工作包 task_id", "path": "生图工具返回的本机绝对路径", "kind": "generated"}
  ]
}
```

执行：

```text
redbeacon creation image-import --generation-id <generation_id> --json-file <图片交接文件>
```

  - 只有 `ok=true` 才算图片接管成功。把命令返回的 `images` 数组原样写进同一个宿主结果文件，不能继续使用原始图片路径。
  - 把 `host.capabilities` 加上实际完成的 `image_generate` 或 `image_edit`。参考图编辑任务仍按工作包返回的 `task_id` 和 `kind` 交接。
- 生图工具不存在、任务失败、没有本机路径或图片接管失败：执行 `redbeacon creation image-fallback --generation-id <generation_id>`。
  - `consent_required=false`：按账号策略自动使用已授权的平台图片，或改用本机文字卡。
  - `consent_required=true`：此时才问用户一个问题：
    1. 仅本次使用平台图片
    2. 以后此账号自动使用平台图片
    3. 不使用平台，改用本机文字卡（推荐）
    对应 `--decision` 为 `allow_once`、`allow_always`、`deny_once`。

当前宿主有图片任务和真实生图工具时优先调用，不能为了省步骤直接谎称不可用；没有生图工具时直接进入图片 fallback，不影响已经完成的宿主文案。`image-import` 必须先在内存中解码图片、应用 EXIF 方向、把嵌入色彩配置转换到 sRGB，再只用像素重写为 PNG；进入 RedBeacon 业务目录的第一份图片就必须不含 EXIF、XMP、ICC、文本、注释、时间戳或未知附加块。普通 RGB/RGBA 图片不缩放、不裁切、不改变像素；净化失败立即丢弃本次接管结果并走图片 fallback，绝不能保存原始容器字节。该步骤只做隐私清理和格式规范化，不宣称改变画面内容或规避平台基于画面本身的识别。

## 5. 幂等提交

```text
redbeacon creation commit --generation-id <generation_id> --json-file <result_file>
```

同一 `generation_id` 重复提交会返回同一审稿记录，不得另建一篇。提交失败若明确是宿主图片不可接管，先走图片回退再重提；其它错误记录后继续下一篇，不要把已成功的篇目重做。

## 6. 单篇失败继续与取消

任何无法通过前述校验、修复或已授权回退解决的单篇错误，都必须先用宿主原生 JSON 写入一个 UTF-8 失败文件。工作包已经取得时放在 `work.paths.result_file` 所在目录，否则放在批次请求文件所在目录；不要使用内联 JSON。文件只含：

```json
{
  "error_code": "稳定的英文错误码",
  "error_message": "给用户看的简短中文原因"
}
```

然后执行：

```text
redbeacon creation fail --generation-id <generation_id> --json-file <失败文件>
```

登记成功后继续下一篇。不能因为第 3 篇失败就停止第 4、5 篇，也不能假装失败篇已经入审。平台是否收费、平台调用次数、已完成的文案/图片和失败前阶段都会保留在原任务里；后续仍使用同一个 `generation_id` 恢复。

用户明确放弃一篇时执行：

```text
redbeacon creation cancel --generation-id <generation_id>
```

用户明确取消整个批次时执行：

```text
redbeacon creation batch-cancel --batch-id <batch_id>
```

取消只释放未完成任务和选题预留，已经进入审稿台的成稿不删除。若返回正在确认入审结果，先执行批次恢复，不能强行取消一个提交结果未知的任务。

# 路线 B：宿主无法执行工作包协议

只有当前 AI 客户端无法可靠读取工作包、生成合约文案或用本机文件交接结果时，才整篇走 RedBeacon 平台。不要仅以“不是 Codex”为理由进入本路线。先执行 `redbeacon checkin`；未登录平台时转平台登录，成功后再继续。

自动读取库存并按用户要求挑选不同选题：

```text
redbeacon topics list --account-id <ID> --stage 选题 --limit 20
```

逐篇、严格串行执行现有平台生成入口；每篇都传自己的选题记录 ID 和实际字段，未指定方案时不传方案 ID：

```text
redbeacon generate --account-id <ID> --topic-record-id <record_id> --topic <选题> --content-type <内容类型> --app-domain <应用域> --problem-type <问题类型> --angle <切入角度> --outline <要点提纲> --idea <本篇要求> --image-mode <本篇覆盖值>
```

平台路径按实际用量消耗算力点。失败时把 `error` 转成人话并按 `next` 自愈，不得用宿主随手写一段冒充平台结果。用户临时指定的题没有库存记录时，不传 `--topic-record-id`。

# 批次收尾

每篇成功、失败或取消后执行：

```text
redbeacon creation batch-status --batch-id <batch_id>
```

这条只适用于路线 A。即使某篇失败，也继续处理状态仍未终结的下一篇。整批处理完后按 `items[]` 汇总成功、需要修正、失败和取消篇数；只有出现新成稿时才执行一次：

```text
redbeacon ui app --detach --page 审稿 --account-id <ID>
```

告诉用户 RedBeacon 已把成稿放进审稿台，可以在客户端核查，也可以回到对话继续改稿。不要自动标通过或进入发布。

最后执行 `redbeacon topics stats --account-id <ID>`；`unused < 5` 时只提醒一句选题快见底，不打断已完成结果。

# 不可突破的边界

- 标题最终必须为 1～20 字，正文 1～888 字，至少一张图片；仍标记“需要修正”的稿不能通过。
- 未获得对应能力授权时，平台文案和平台图片调用次数必须为 0。
- 文案授权与图片授权独立，账号之间不共享。
- 批量 1～20 篇严格串行，不用线程或并行工具同时生成多篇。
- 只消费成功入审的选题；失败任务保留预留供恢复，不能手工删选题。
- 同批失败不会阻断后续；失败、取消和过期任务由耐久状态与租约处理，不得手工改数据库或删除工作目录。
- 恢复必须按 `batch-recover` / `retry` 返回的阶段继续；已经成功或可能扣点的阶段不能凭猜测重跑。
- 所有嵌套、多行中文 JSON 使用 UTF-8 文件或安全 stdin，不使用脆弱的内联 JSON 参数。
- 不把平台令牌、Cookie、代理信息写进工作包或宿主结果。
