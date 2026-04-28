# RedBeacon · 小红书 AI 运营系统

---

## 你的精力，值得花在更重要的事情上

做小红书，很多人陷在一种循环里：

打开 AI 写文案 → 复制 → 打开做图工具 → 下载图片 → 打开小红书 → 上传 → 发布。

每天重复。不出错就是成功。

这不是在运营账号，这是在做赛博搬运工。这种工作，本不应该消耗你的时间和注意力。

RedBeacon 把这条流水线完整接管。你从流水线上解脱出来，把精力放回到真正值钱的地方——想清楚你要做什么，以及怎么做好。

---

## Skill：对整个系统拥有完整操作权的 AI 界面

RedBeacon 的核心设计理念，是把 AI 做成**真正的操作界面**，而不是一个聊天助手。

你用自然语言跟它说话，它真实地执行后端操作——读数据、写配置、生成内容、调用发布接口。所有的事情，都在一次对话里完成。

```
你："帮我生成这周的内容，用图文卡片"
Skill：从选题库取题 → 调用 AI 生成文案 → 渲染图文卡片 → 写入待审核 → 推送飞书 → 告知完成
```

```
你："我刚看到一篇讲副业收入的文章，感觉不错"
Skill：读取你的账号定位 → 四维匹配评估 → "这个方向和你的账号受众不重合，建议放弃"
```

---

## 功能概览

- **账号策略**：引导完成赛道定位、受众画像、变现路径、内容策略规划
- **选题库**：批量导入、AI 灵感生成、外部内容四维匹配评估
- **内容生成**：图文卡片（7 种主题）、AI 封面图、两者结合
- **内容审核**：飞书多维表格审核 / Web UI 审核
- **自动发布**：审核通过自动发布到小红书，支持定时排期
- **自动化调度**：每个账号独立配置生成排期，全局开关控制

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11 + FastAPI |
| 前端 | Next.js 16 + TailwindCSS |
| 数据库 | SQLite |
| 渲染 | Playwright（图文卡片渲染）|
| AI 接口 | OpenAI 兼容格式 |
| 发布引擎 | xiaohongshu-mcp（Go，需单独获取）|

---

## 开发环境启动

### 前置条件

- Python 3.11+
- Node.js 18+
- xiaohongshu-mcp 二进制（放入 `tools/` 目录）

### 1. 克隆仓库

```bash
git clone https://github.com/your-username/redbeacon.git
cd redbeacon
```

### 2. 安装后端依赖

```bash
pip install -r backend/requirements.txt
playwright install chromium
```

### 3. 安装前端依赖

```bash
cd frontend && npm install && cd ..
```

### 4. 一键启动

```bash
bash start.sh
```

启动后访问：
- **Web UI**：`http://localhost:3000`（开发模式 Next.js dev server）
- **API 文档**：`http://localhost:8000/docs`

### 5. 配置 AI 接口

打开 `http://localhost:3000/settings`，填写 AI Base URL 和 API Key，点击测试连通性。

---

## 打包发布

打包产物完全自包含，用户无需安装任何依赖，双击即可运行。

```bash
# macOS（在 Mac 上执行）
python build.py
# 产物：redbeacon-dist/mac/

# Windows（在 Windows 机器上执行）
build-win.bat
# 产物：redbeacon-dist/win/
```

**打包后用户端访问 `http://localhost:8000`**（前端由 FastAPI 静态托管，无需 Node.js）。

详见 [CLAUDE.md](CLAUDE.md) 中的打包策略说明。

---

## 项目结构

```
redbeacon/
├── backend/              # FastAPI 后端
│   ├── main.py           # 应用入口
│   ├── routers/          # API 路由
│   ├── services/         # 飞书、MCP、图片生成等服务
│   ├── tasks/            # 内容生成、发布任务
│   └── render_xhs_v2.py  # 图文卡片渲染器（Playwright）
├── frontend/             # Next.js 前端
│   ├── app/              # 页面（App Router）
│   ├── lib/api.ts        # API 调用封装
│   └── components/       # 公共组件
├── .claude/commands/     # Skill 文件（Claude Code 命令）
├── tools-src/            # 平台工具二进制（构建时复制到 dist）
├── backend_server.py     # 后端 PyInstaller 入口
├── renderer_main.py      # 渲染器 PyInstaller 入口
├── launcher.py           # GUI Launcher PyInstaller 入口
├── build.py              # 打包脚本（macOS / Linux）
├── build-win.bat         # 打包脚本（Windows）
├── start.sh              # 开发启动脚本
└── CLAUDE.md             # AI 协作手册（架构、踩坑、打包规范）
```

---

## 需要准备什么

| 必需 | 说明 |
|------|------|
| AI API Key | 支持 OpenAI 兼容格式（GPT / Claude / Gemini 均可）|
| 小红书账号 | 扫码登录，Cookie 仅本地保存 |
| Claude Code | Skill 系统运行环境，[下载](https://claude.ai/download) |

| 可选 | 说明 |
|------|------|
| 飞书账号 | 手机端审核内容，审核通过自动发布 |
| 图片生成模型 | 支持多模态输出，用于 AI 封面图 |

---

## 第三方工具说明

`tools/` 目录包含以下预编译二进制文件，版权归原作者所有，随本仓库分发仅为方便使用：

| 文件 | 平台 | 说明 | 来源 |
|---|---|---|---|
| `xiaohongshu-mcp-darwin-arm64` | macOS Apple Silicon | 小红书 MCP 服务端 | [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) |
| `xiaohongshu-mcp.exe` | Windows x64 | 小红书 MCP 服务端 | 同上 |
| `xiaohongshu-login-darwin-arm64` | macOS Apple Silicon | 小红书扫码登录工具 | 同上 |
| `xiaohongshu-login.exe` | Windows x64 | 小红书扫码登录工具 | 同上 |

> 如需其他平台版本（Linux / macOS Intel），请前往原仓库下载后放入 `tools/` 目录。

---

## 联系 & 支持

微信公众号 / 抖音搜索 **吉豆茄**，或扫码联系作者升级 Pro 版（多账号矩阵、一号一 IP）：

<table>
  <tr>
    <td align="center">
      <img src="assets/qr-wecom.jpg" width="160" /><br/>
      <sub>企业微信（联系作者）</sub>
    </td>
    <td align="center">
      <img src="assets/qr-wxmp.jpg" width="160" /><br/>
      <sub>微信公众号 · 吉豆茄</sub>
    </td>
  </tr>
</table>

---

*你的注意力是稀缺资源。把它留给真正需要判断力的事情。*
