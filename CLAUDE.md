# RedBeacon · 开发指南（CLAUDE.md）

> 本文件是**给 Claude Code 的工程约定**（开发 RedBeacon 本项目时用）。
> **产品/架构的唯一参照物 = `项目文档/` 分册**（见 `项目文档/README.md` 文档地图）。
> **实时进度看 `项目文档/项目进度.md`**（冷启动 `Read` 一次取最新）。
>
> ⚠️ **别和 `AGENTS.md` 搞混**：`AGENTS.md` 是给**运行时 agent**（装了 RedBeacon skill、帮终端用户跑小红书运营的那个 Claude/Codex）的工作台说明；**本 CLAUDE.md 是给开发 RedBeacon 这个产品的窗口**的工程契约。两者语境不同，都保留、别互相覆盖。
>
> **🔁 文档↔代码同步契约**：动 `cli/` / `.claude/commands/` 前后，以 `项目文档/` 对应文档为 spec 对齐；**实现有任何偏离/变更，必须回报，由 PM 窗口同步进文档**。PM 窗口（工作区 `项目文档/`）默认只活文档层、未经授权不读改代码层——**开发层可看文档层，文档层不反向窥探代码层**。

@项目文档/README.md

## 这是什么

RedBeacon = 小红书运营**数字员工**（CLI + skill），是「数字员工平台」(bytestaff) 上的**第一个 metered 员工**（靠生图扣算力点）。用户像带下属一样用大白话指挥，它把选题/文案/配图/审核/发布全包。

## 双层 / 双窗口（本次新建）

- **代码层（根目录）**：`cli/`（真引擎，闭源 Python CLI）+ `.claude/commands/redbeacon*.md`（skill 真源，Codex 端从此派生）+ `AGENTS.md`（运行时 agent 说明）+ `README.md`（产品介绍）。
- **文档层（`项目文档/`）**：产品/架构方案、平台接入规范、进度——PM 窗口维护。
- **两个 Claude 窗口**：**代码窗口**（根目录开机）+ **PM 窗口**（`项目文档/` 开机）。单向边界见上（开发层可看文档层、文档层不反窥代码层）。

## 架构（一句话，详见 `AGENTS.md`）

- 真引擎 = `redbeacon` CLI；能力以 skill 形式提供，真源在 `.claude/commands/`、Codex 端派生。
- 数据：业务数据单一真源在**飞书多维表格**（每用户自带飞书应用、CLI 直连、零跨用户风险）；隐私/钥匙/身份只在本地内核、不上传。
- 计费/登录/生图：**对接 bytestaff 平台**（外部依赖）——见下。

## 接入平台（计费 / 登录 / 生图）

- RedBeacon 的登录/生图/计费**对接 bytestaff 数字员工平台**；客户端只持账号级设备令牌、**永不持上游 key**。
- **客户端接平台后台的逐条契约 = `项目文档/RedBeacon-平台接入开发规范.md`**（device flow / checkin / 生图 / 错误码 / 铁律红线）。
- 平台侧契约真源在 bytestaff `项目文档/`（§6 接口 / §9 错误码 / §14.6 客户端规范 / §3.3a 会员模型）。

## 铁律（接平台时守）

1. 客户端**永不持上游/中转站 key**，唯一凭据 = 账号级设备令牌（device flow 签发、可吊销）。
2. **免费能力走宿主 AI + 本地**（文案/选题/定位/内容/文字卡/发布），不带令牌、不调平台；**只有生图带令牌走平台**。
3. `account_id` 服务端从令牌解，客户端不传（防 IDOR）。
4. 鉴权/扣点全平台服务端、每次现查、**fail-closed**。

## 代码结构 / 常用命令

- `cli/` CLI 源码；`.claude/commands/` skill 真源；`tools/` 同步脚本（如 `sync-codex-skills.py`）；`install/`、`pip/` 分发。
- 升级两端：`redbeacon update`（升 CLI + 刷 Claude `.claude/commands/` + 派生刷新 Codex skills）。
- ⚠️ 构建/测试/发布的细节以 `AGENTS.md` + 仓内现有约定为准；本文不杜撰。
