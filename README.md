# RedBeacon · 小红书全自动运营系统

**选好题，其他不用你管。**

---

## 这是什么

一套跑在你本地的小红书自动化运营系统。

你只需要做一件事：**审核内容**。

其他的——选题、写文案、配图、发布、排期——全部自动完成。

```
你审核通过 → 系统自动发布 → 继续生成下一篇 → 循环
```

适合：**图文引流、账号矩阵、内容批量生产**。

---

## 它能帮你做什么

### 全自动内容生产

- 从你的选题库自动取题
- 调用 AI 生成标题 + 正文 + 标签
- 自动生成图文卡片（7 种主题可选）或 AI 封面图
- 生成完成推送到飞书，等你审核

### 全自动发布

- 你在飞书里把内容状态改为「通过」
- 系统检测到后自动发布到小红书
- 发布时间可以精确控制（定时排期）
- 多账号同时跑，互不干扰

### 账号策略管理

- 第一次使用时引导你梳理账号定位、变现路径、内容方向
- 所有生成的内容都基于这套定位，不会乱
- 随时可以调整策略，下次生成立即生效

### 选题质量把关

- 内置四维匹配评估：赛道、受众、内容支柱、增长目标
- 把外部看到的内容灵感扔进来，系统判断适不适合你的账号
- 不匹配的直接拒绝，不让跑偏的内容污染选题库

---

## 你真正需要做的

1. **第一次**：花 15 分钟梳理账号定位
2. **日常**：在飞书里看内容，点「通过」或「驳回」
3. **偶尔**：补充选题库（也可以让 AI 帮你生成）

就这些。

---

## 下载即用，无需安装任何环境

> 点击右侧 **Releases** 下载对应平台的压缩包，解压后直接双击启动，无需安装 Python、Node.js 或任何依赖。

| 平台 | 启动方式 |
|---|---|
| **macOS**（Apple Silicon）| 解压 → 双击 `mac/RedBeacon.app` |
| **Windows**（x64）| 解压 → 双击 `win\RedBeacon.exe` |

启动后访问 `http://localhost:8000` 即可使用。

---

## 还需要准备

| 必需 | 说明 |
|---|---|
| **AI API Key** | 支持 OpenAI 兼容格式（GPT / Claude / Gemini 均可）|
| **小红书账号** | 扫码登录，Cookie 仅存本地，不上传任何服务器 |
| **[Claude Code](https://claude.ai/download)** | AI 对话操作界面（免费版足够）|

| 可选但推荐 | 说明 |
|---|---|
| **飞书账号** | 手机端审核，随时随地，审核通过自动发布 |
| **图片生成模型** | AI 封面图功能（支持多模态输出的模型）|

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11 + FastAPI |
| 前端 | Next.js 16 + TailwindCSS |
| 数据库 | SQLite（本地，无云端）|
| 渲染 | Playwright（图文卡片）|
| AI 接口 | OpenAI 兼容格式 |
| 发布引擎 | [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) |

---

## 开发者本地启动

```bash
# 安装依赖
pip install -r backend/requirements.txt
playwright install chromium
cd frontend && npm install && cd ..

# 启动（后端 :8000，前端开发模式 :3000）
bash start.sh
```

打包构建见 `build.py`（macOS）和 `build-win.bat`（Windows）。

---

## 第三方工具说明

`tools/` 目录包含以下预编译二进制，版权归原作者所有：

| 文件 | 说明 | 来源 |
|---|---|---|
| `xiaohongshu-mcp-darwin-arm64` | 小红书 MCP 服务（macOS）| [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) |
| `xiaohongshu-mcp.exe` | 小红书 MCP 服务（Windows）| 同上 |
| `xiaohongshu-login-darwin-arm64` | 扫码登录工具（macOS）| 同上 |
| `xiaohongshu-login.exe` | 扫码登录工具（Windows）| 同上 |

---

## 联系 & Pro 版

免费版支持 1 个账号。**Pro 版支持无限账号矩阵、一号一 IP**。

扫码联系作者，或关注微信公众号 / 抖音 **吉豆茄**：

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

*选好题，其他不用你管。*
