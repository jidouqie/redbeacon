# 发布排期保存与开发版验收

发布页每篇的“发布选项”现在把发布方式和时间写入本机业务库。修改后自动保存，也可点击“保存排期”重试；显示“排期已保存到本机”后可切换账号、刷新或重开客户端。时间以北京时间显示，数据库保存 Unix 毫秒时间戳。

排期与审核独立。未审核稿可以先保存排期，审核通过后发布页会带出原有排期；保存只更新 `local_review.publish_mode` 和 `schedule_ms`，按账号 ID 与稿件 ID 双重匹配。标题、正文、图片、审核状态、失败原因和生成来源保持原值。排期保存也不修改原创声明、AI 声明与可见范围；本次发布仍使用用户逐篇选择的选项。

按用户 2026-09-09 最新要求，定时时间缺失、无效、过期或超出有效范围时，提交方式自动变为立即发布；有效时间继续按定时发布。页面保留原输入以便修改，同时在列表、单篇按钮和批量汇总显示实际发布方式。保存中或保存失败仍阻止提交。后端逐篇执行以及浏览器最终点击前按分钟精度重算“至少 1 小时、最多 14 天”；轮到提交时已失效的时间同样改为立即发布。

## 本机保存接口

这些保存与查询接口不创建发布任务，也不请求浏览器或平台计费。认证沿用当前客户端的本机 API 认证。

| 接口 | 请求 | 用途 |
| --- | --- | --- |
| `POST /api/publish/timing` | 单条排期对象 | 保存一篇 |
| `POST /api/publish/timings` | `{"entries": [...]}` | 原子批量保存，可跨账号 |
| `GET /api/publish/timings?account_id=1` | 可加 `record_id` | 查询该账号审核表中的排期，含未审核稿 |
| `GET /api/publish?account_id=1` | 既有发布列表 | 返回通过稿的 `schedule_mode`、`schedule_ms`、`timing_error` 和时间标签 |

一条排期包含：

- `account_id`：正整数内部账号 ID，使用列表返回的真实 ID。
- `record_id`：稿件 ID 字符串。
- `mode`：必填，`immediate` 或 `scheduled`。
- `schedule_ms`：整数毫秒时间戳；立即发布必须为 `null`，定时发布允许暂存 `null`，提交时按立即发布执行。

批量最多 1000 篇，账号不存在、稿件不属于账号、稿件已归档、重复稿件、方式或 JSON 字段类型错误都会拒绝整批，前面的稿件也不会部分写入。缺失、过期或超出 14 天的定时时间可以保存，响应通过 `invalid_count` 和每篇 `validation_error` 说明原时间的问题，通过 `fallback_to_immediate`、`effective_mode` 和 `effective_schedule_ms` 表示实际方式。`publishable` 包含按新规则立即发布的情况，但审核、登录、素材与声明等条件仍需满足。

## UTF-8 文件入口

CLI 支持排期对象数组或包含 `entries` 的对象。业务文件里的标题、账号名、说明、展示时间及顶层 `publish_options` 只是元数据，不会覆盖稿件或发布选项；实际保存以四个排期字段为准。

以下示例保留空的定时输入；只保存、不发布，之后提交时将立即发布：

```json
{
  "entries": [
    {"account_id": 1, "record_id": "101", "mode": "scheduled", "schedule_ms": null}
  ]
}
```

当前修复仅在开发源码中，已安装旧版尚未包含该命令。准备 `排期.json` 后，从仓库根目录使用当前源码 CLI；先确认 CLI 的通道与数据目录和客户端一致。

macOS：

```text
cli/.venv/bin/python -I -m redbeacon.cli publish timings save --json-file "排期.json" --dry-run
cli/.venv/bin/python -I -m redbeacon.cli publish timings save --json-file "排期.json"
cli/.venv/bin/python -I -m redbeacon.cli publish timings list --account-id 1
```

Windows：

```text
cli\.venv\Scripts\python.exe -I -m redbeacon.cli publish timings save --json-file "排期.json" --dry-run
cli\.venv\Scripts\python.exe -I -m redbeacon.cli publish timings save --json-file "排期.json"
cli\.venv\Scripts\python.exe -I -m redbeacon.cli publish timings list --account-id 1
```

`--json -` 与 `--json-file -` 沿用 stdin 契约。预检返回 `saved=false`，不写入排期；保存返回 `saved=true`。两者都通过 `invalid_count` 和逐篇原因提示将改为立即发布的记录，不自动顺延日期。保存入口本身始终不触发发布。

## 本机客户端生效

退出正在运行的正式通道客户端后，在仓库根目录运行 `tools/run_desktop_dev.sh stable`，使用正式数据；隔离体验使用 `tools/run_desktop_dev.sh test`。完整重启后才会加载新后端和前端。首次启动由版本化迁移新增两列（数据库 schema 3），保留旧稿的默认立即发布行为；后续应使用支持此数据库版本的客户端，旧安装包不会获得这次源码修复。

本修复的隔离验证使用临时数据库与模拟发布口，覆盖三账号各 42 篇的 UTF-8 文件保存、重新打开数据库、跨账号整批回滚、页面切换时慢请求、保存失败重试、全选逐篇时间和声明、无效时间回退、队列等待后失效、最终点击前失效及实际归档时间。后两种情况会关闭小红书定时开关，确认关闭后才点击，并把实际立即发布结果返回核心归档。

随后按用户追加授权，用正式数据启动源码客户端，关闭安装版客户端。实机验证原生日期控件保存、切换账号及完整重开后的恢复，并完成主要页面与业务核心验收；临时验收账号和样稿已清理。用户进一步授权导入业务排期、审核和定时提交，业务结果单独记录在本机验收目录中，不能继续将原计划文件当作“尚未导入”的状态依据。

## 提交控件与最终验收

实测中的一次提交超时触发停止。检查发现旧逻辑可能把发布控件的空白区当作按钮、保留日期弹层焦点，或误判新版原创开关状态。当前源码先结束编辑，再读取原创开关的实际状态；声明设置失败会阻止提交。对于封闭的发布控件，从该控件截图中定位唯一的红色主按钮并适配像素缩放，无法唯一定位则不点击。在截图和指针移动后、唯一一次点击前，再验证定时时间与原创声明。成功仍必须有页面明确回执；按用户最新要求，发布动作失败后最多重试 3 次，重试前先检查迟到回执，详见 publish-retries.md。

控件修复与最新无效时间规则已完成隔离回归，并已重启源码客户端加载。在正式数据的原生发布页验证了实际方式提示与数量；用户随后启动了批量发布，运行结果须以每篇实际回执为准。

2026-09-09 最终源码验收：macOS 全量 1308 项通过；Windows x64 全量 1304 项通过、3 项按平台跳过（2 项 POSIX 进程组、1 项 AppleScript），1 项既有采集提醒测试因跨秒文案从“1 分钟”变为“59 秒”失败，该项单独复验通过。排期专项与提交控件专项两端全部通过，代码规模检查、JavaScript 语法检查及差异空白检查通过。两端各有一项既有 Starlette 测试客户端弃用警告。

两端验证使用相同的源码与测试快照，SHA-256 为 `566d75121ac9685404c277abc27f3efd47236746e57fb38a6c7639d7621416ed`。保留原有未提交改动，本次没有构建或发布新版安装包。

日期控件补充修复：定时开关兼容 aria-checked 与原生 checkbox 状态，已经开启时不再误关。时间输入复用整段键盘输入，按 Enter 确认、Tab 移出焦点，再回读；最终点击前再次核对平台页面值。已在账号自身的真实浏览器中验证两个有效时间及立即发布切换，测试阶段阻断提交请求，没有提交笔记。最终源码客户端已于 2026-09-09 12:27 完整重启加载。
