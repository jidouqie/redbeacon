# xiaohongshu-mcp HTTP API 文档

> 源码：[xpzouying/xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)
> 
> RedBeacon 通过 `services/mcp_manager.py` 管理 MCP 进程，每个账号独占一个端口（默认从 18060 起），
> 所有请求直连 `http://127.0.0.1:{mcp_port}`，不经过代理（`trust_env=False`）。

---

## 通用规范

### 响应格式

**成功**
```json
{
  "success": true,
  "data": { ... },
  "message": "操作说明"
}
```

**失败**
```json
{
  "error": "错误说明",
  "code": "ERROR_CODE",
  "details": "详细信息"
}
```

### 启动参数

```bash
xiaohongshu-mcp -port :18060 -headless=true
```

| 参数 | 说明 |
|---|---|
| `-port` | 监听端口，格式 `:{port}` |
| `-headless` | `true`=无头模式（生产）/ `false`=有头模式（调试/登录） |
| `-bin` | 自定义 Chromium 路径（可选） |

**环境变量**

| 变量 | 说明 |
|---|---|
| `COOKIES_PATH` | Cookie 文件路径，每个账号必须独立（如 `data/cookies_1.json`） |
| `XHS_PROXY` | 代理地址（如 `http://host:port`），可选 |

---

## 接口列表

### 健康检查

```
GET /health
```

**响应**
```json
{
  "success": true,
  "data": { "status": "healthy", "service": "xiaohongshu-mcp" }
}
```

---

### 登录状态

```
GET /api/v1/login/status
```

通过浏览器导航到小红书验证当前 Cookie 是否有效。

**响应 data**
```json
{
  "is_logged_in": true,
  "username": "昵称"
}
```

> ⚠️ 此接口每次都启动新 Chromium 并导航到小红书，耗时较长（5–15s），且走代理。
> 建议用于手动验证，不要高频轮询。

---

### 获取登录二维码

```
GET /api/v1/login/qrcode
```

获取小红书登录二维码（Base64 图片），同时启动后台等待扫码完成后自动保存 Cookie。

**响应 data**
```json
{
  "is_logged_in": false,
  "img": "data:image/png;base64,...",
  "timeout": "4m0s"
}
```

| 字段 | 说明 |
|---|---|
| `is_logged_in` | 若已登录则为 `true`，`img` 为空 |
| `img` | Base64 二维码图片，前端可直接用于 `<img src>` |
| `timeout` | 二维码有效期 |

---

### 删除 Cookie（退出登录）

```
DELETE /api/v1/login/cookies
```

删除本地 Cookie 文件，重置登录状态。

**响应 data**
```json
{
  "cookie_path": "/path/to/cookies.json",
  "message": "Cookies 已成功删除，登录状态已重置。"
}
```

---

### 发布图文笔记

```
POST /api/v1/publish
Content-Type: application/json
```

**请求体**
```json
{
  "title": "标题（必填，最多20个中文字）",
  "content": "正文内容（必填）",
  "images": [
    "/absolute/path/to/image.jpg",
    "https://example.com/image.png"
  ],
  "tags": ["美食", "旅行"],
  "schedule_at": "2024-01-20T10:30:00+08:00",
  "is_original": false,
  "is_ai_generated": true,
  "visibility": "公开可见",
  "products": ["面膜", "防晒霜SPF50"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | ✓ | 最多 20 个中文字或英文单词 |
| `content` | string | ✓ | 正文，不含 `#标签` |
| `images` | []string | ✓ | 至少 1 张；支持本地绝对路径或 HTTP(S) URL |
| `tags` | []string | | 话题标签，不加 `#` |
| `schedule_at` | string | | ISO8601 定时发布，范围 1h–14天内；空则立即发布 |
| `is_original` | bool | | 声明原创，默认 `false` |
| `is_ai_generated` | bool | | 声明含 AI 合成内容，默认 `true` |
| `visibility` | string | | `公开可见`（默认）/ `仅自己可见` / `仅互关好友可见` |
| `products` | []string | | 带货商品关键词，账号需已开通商品功能 |

**响应 data**
```json
{
  "title": "标题",
  "content": "正文",
  "images": 3,
  "status": "发布完成",
  "post_id": "笔记ID（定时发布时可能为空）"
}
```

---

### 发布视频笔记

```
POST /api/v1/publish_video
Content-Type: application/json
```

**请求体**
```json
{
  "title": "标题（必填）",
  "content": "正文（必填）",
  "video": "/absolute/path/to/video.mp4",
  "tags": ["vlog"],
  "schedule_at": "",
  "visibility": "公开可见",
  "products": []
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | ✓ | 最多 20 个中文字 |
| `content` | string | ✓ | 正文 |
| `video` | string | ✓ | 本地视频绝对路径，仅支持单个文件 |
| `tags` | []string | | 话题标签 |
| `schedule_at` | string | | ISO8601 定时，空则立即 |
| `visibility` | string | | 同图文发布 |
| `products` | []string | | 带货商品 |

---

### 获取 Feeds 列表（首页推荐）

```
GET /api/v1/feeds/list
```

获取小红书首页推荐内容列表。

**响应 data**
```json
{
  "feeds": [
    {
      "id": "笔记ID",
      "xsec_token": "访问令牌",
      "title": "标题",
      "author": "作者昵称",
      "likes": 1234
    }
  ],
  "count": 20
}
```

---

### 搜索 Feeds

```
GET  /api/v1/feeds/search?keyword=关键词
POST /api/v1/feeds/search
```

**POST 请求体**
```json
{
  "keyword": "搜索关键词",
  "filters": {
    "sort_by": "综合",
    "note_type": "不限",
    "publish_time": "不限",
    "search_scope": "不限",
    "location": "不限"
  }
}
```

| `filters` 字段 | 可选值 |
|---|---|
| `sort_by` | `综合`（默认）/ `最新` / `最多点赞` / `最多评论` / `最多收藏` |
| `note_type` | `不限`（默认）/ `视频` / `图文` |
| `publish_time` | `不限`（默认）/ `一天内` / `一周内` / `半年内` |
| `search_scope` | `不限`（默认）/ `已看过` / `未看过` / `已关注` |
| `location` | `不限`（默认）/ `同城` / `附近` |

---

### 获取笔记详情

```
POST /api/v1/feeds/detail
Content-Type: application/json
```

**请求体**
```json
{
  "feed_id": "笔记ID",
  "xsec_token": "从Feed列表获取",
  "load_all_comments": false,
  "limit": 20,
  "click_more_replies": false,
  "reply_limit": 10,
  "scroll_speed": "normal"
}
```

| 字段 | 说明 |
|---|---|
| `feed_id` | 必填 |
| `xsec_token` | 必填，从 Feed 列表的 `xsec_token` 字段取 |
| `load_all_comments` | `false`=只取前 10 条评论（默认）/ `true`=滚动加载更多 |
| `limit` | `load_all_comments=true` 时有效，最多加载评论数，默认 20 |
| `click_more_replies` | 是否展开二级回复，默认 `false` |
| `reply_limit` | 跳过回复数超过此值的评论，默认 10 |
| `scroll_speed` | `slow` / `normal`（默认）/ `fast` |

---

### 获取用户主页

```
POST /api/v1/user/profile
Content-Type: application/json
```

**请求体**
```json
{
  "user_id": "小红书用户ID",
  "xsec_token": "从Feed列表获取"
}
```

---

### 获取当前登录用户信息

```
GET /api/v1/user/me
```

返回当前 Cookie 对应的账号基本信息。

---

### 发表评论

```
POST /api/v1/feeds/comment
Content-Type: application/json
```

**请求体**
```json
{
  "feed_id": "笔记ID",
  "xsec_token": "从Feed列表获取",
  "content": "评论内容"
}
```

---

### 回复评论

```
POST /api/v1/feeds/comment/reply
Content-Type: application/json
```

**请求体**
```json
{
  "feed_id": "笔记ID",
  "xsec_token": "从Feed列表获取",
  "comment_id": "目标评论ID",
  "user_id": "目标评论用户ID",
  "content": "回复内容"
}
```

---

## RedBeacon 调用约定

RedBeacon 调用 MCP 时的固定规则：

1. **Cookie 必须隔离**：每个账号用独立的 `COOKIES_PATH`（`data/cookies_{account_id}.json`），否则多账号 Cookie 互相覆盖
2. **发布流程不走代理**：`mcp_manager.py` 里 `proxies={"http": "", "https": ""}` 直连本地，MCP 内部网络请求（访问小红书）走 `XHS_PROXY`
3. **发布前检查登录状态**：调 `/api/v1/login/status`，未登录直接跳过该账号
4. **每条发布后等待**：`random.randint(30, 90)` 秒，避免触发小红书频率限制
5. **多账号间等待**：`random.randint(60, 180)` 秒
6. **`headless=True` 用于生产**：仅登录时用 `headless=False`，正常发布始终无头
