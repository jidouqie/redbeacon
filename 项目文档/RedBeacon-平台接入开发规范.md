# RedBeacon 客户端 · 平台接入开发规范

> RedBeacon 客户端（CLI/skill/UI）接入「数字员工平台」(bytestaff) 线上后台的对接契约。
> **契约真源 = 平台文档**（bytestaff `项目文档/11-客户端接入指南.md` + §3.3a 会员 / §5 对话 / §5.4 生图 / §6 接口 / §9 错误码）。本文 = RedBeacon 落地指南，逐字字段已对在产代码核实；与平台真源冲突以平台为准、实现有偏离回报平台 PM。
> 线上域名 `https://bytestaff.jiomig.com`（走配置项、**勿硬编码**）。

## 0. 铁律红线（违反 = 改方案）
1. **客户端永不持上游/中转站 key**——唯一凭据 = 账号级**设备令牌**。
2. **AI 能力（文案/定位/选题/生图）一律带设备令牌走平台扣点**：文案/定位/选题走对话接口（§7）、生图走生图接口（§4）。**免费/本地只剩**文字卡渲染、发布、飞书读写。靠"每日赠点"让免费用户也能用 AI（§6），不靠白嫖宿主 AI。
3. **`account_id` 永远由服务端从令牌解出，客户端不传**（防 IDOR）。
4. **鉴权/扣点全在平台服务端、每次现查、fail-closed**——平台不可达即拒，客户端不存"已解锁"本地标志。
5. **两把钥匙别混**：客户端只持**设备令牌**（调平台能力），**绝不碰网站会话**。故客户端**不调 `/me/*`**（要网站会话、CLI 调会 401）；会员状态全从 `/device/checkin` 拿。

## 1. 鉴权：账号级设备令牌
- device flow 签发、**账号级**（不绑单员工）、可吊销、平台哈希存；明文仅签发时返一次。
- 客户端写本地**共享账号目录**（非 redbeacon 私有）→ 将来第二个员工 skill 读同一份令牌自动登录态。属用户隐私、明文存本地隐私内核、不上传。
- 调一切能力带 `Authorization: Bearer <令牌>`。
- **无 refresh**：过期/吊销 → 重新 `login`。**不限设备数**（计费闸=点数池，`DEVICE_LIMIT` 已退役）。

## 2. 登录 = OAuth 2.0 device flow（`redbeacon login`）
> ⚠️ 与登录小红书的命令是两套——后者叫 `redbeacon xhs-login`。平台登录 ≠ 订阅 ≠ 小红书登录态。别让用户在 CLI 输账号密码。

流程：`POST /device/code` → CLI 显示 user_code + 短链 → 按 `interval` 轮询 `POST /device/token` → 用户浏览器开短链授权 → CLI 拿令牌存本地。

**逐字字段（在产核实；⚠️ 非 RFC 8628，别按 RFC 惯例搭）：**
```
POST /device/code   { label?, product_code:"redbeacon" }
  200 → { device_code, user_code,
          verification_uri:          "{BASE}/device/approve",
          verification_uri_complete: ".../device/approve?code=<user_code>",  // 预填一键授权
          expires_in, interval }
  err → 400 {error:"invalid_product"}

POST /device/token  { device_code }
  200 待授权 → { status:"pending", interval }
  200 已授权 → { status:"approved", token:"<令牌明文·仅此一次>",  // ⚠️ 字段名 token 非 access_token
               expires_in_days, account:{ id } }
  err → invalid_grant/expired_token→400 · access_denied→403 · slow_down→429
```
轮询逻辑：HTTP 200 看 `status`（pending 续轮 / approved 取 `token`）、429 放慢、400/403 终止。**别等 RFC 的 `access_token`/`authorization_pending`**。

## 3. 轻打卡 = `POST /device/checkin`（客户端会员状态唯一来源）
- **时机**：每次 skill/UI 启动拉一次（不调 AI、近乎零成本）；**入参** `{ product_code:"redbeacon" }`、设备令牌 Bearer。
- **按需激活**：无使用权 → 自动建一条 free（幂等）。新 skill 首次打卡即进【我的员工】。
- **响应（已冻结）**：
```
{ ok, activated,                       // activated=本次是否新建 free（幂等已有=false）
  membership: {                        // ← 显示档/点数/临期 唯一来源
    tier, tier_name,                   // free|pro|promax
    points:{ total, used, remaining },  // 账号级共享池（跨所有员工）⚠️ 点数只在这、别去 entitlements 找
    valid_until,                       // free/不过期=null
    status,                            // active | free
    renewal_reminder },                // 临期{expiring_soon,valid_until,days_left} 否则 null
  entitlements:[ {id,account_id,product_code,product_name,status,valid_from,valid_until} ] }
    // 只表使用权·不含点数。⏳ features 块（号数下发）平台未实现、客户端容错
}
```
- 点数 = 账号级共享池、跨所有员工（一份会员玩遍全平台，可作卖点）。

## 4. 生图 = `POST /v1/images/generations`（平台计量能力）
- 设备令牌 Bearer；声明 `product=redbeacon` / `capability=image_gen` / **`request_id`（幂等键）** + prompt/尺寸/张数。
- 链路：认令牌 → 查使用权 → **原子扣共享点数池**（N=张数×单价，现 10 点/张）→ 上游出图 → 落 OSS → 回下载链接。
- **幂等**：同 `request_id` 不重复扣、返原图。**失败不扣**（预扣后回补）。**点数不足/无会员/会员过期 → 拒、不调上游**（fail-closed）。
- 下载走 OSS/CDN、不碰平台服务器；客户端拉图缓存本地 `~/.redbeacon/data/images/` 照旧 cloakbrowser 发布。**生图失败/平台不可达只影响图**，纯文字卡笔记照样落库可后补。

**逐字字段（在产核实）：**
```
请求 { prompt(必), request_id(必·≤64·uuid),
       product:"redbeacon"(⚠️ 非 product_code), capability:"image_gen",
       size?, n?(默 1·MVP=1) }
200 → { created, data:[{ url:"CDN链接" }](⚠️ OpenAI 风数组非单 url), request_id,
        points:{cost,used,total,remaining,addon:0},
        renewal_reminder:null|{...}, idempotent:true(仅幂等命中) }
```

### 4.1 图生图 / 参考图（契约定稿 2026-06-26；⏳ 平台未部署、当前走文生图）
capability 仍 `image_gen`、按张同价扣点、文生图不受影响。⚠️ **图字节直传 OSS、绝不经平台**（出口仅 5Mbps）。三步：
1. `POST /v1/images/inputs { content_type:"image/png|jpeg|webp" }` → `{ object, upload_url, method:"PUT", headers:{Content-Type}, max_bytes(默 1.2MB), expires_in(默 300s) }`。
2. `HTTP PUT 图字节 → upload_url`（**必带 headers 的 Content-Type**否则签名不匹配）。
3. `/v1/images/generations` 加可选 `image?:"<object>"`（图生图）/ `mask?:"<object>"`（局部重绘，给 mask 必同时给 image），响应结构与文生图一致。
- **约束**：输入图 ≤1.2MB·仅 png/jpeg/webp·客户端先压缩；只用平台签发的 object（别自备公网 URL）；image/mask 必须本账号传的。

## 5. 错误码 → 友好提示（在产核实）
⚠️ **按 HTTP body 小写 `error` 匹配**（不是大写语义码），响应体统一 `{ error, message, ...extra }`。

| `error` | HTTP | 提示 |
|---|---|---|
| `unauthorized` | 401 | 登录失效，重新 `redbeacon login` |
| `no_entitlement` | 402 | 未激活该员工，去门户「加入我的团队」|
| `entitlement_expired` | 402 | 会员过期，去续费（`extra.cost`）|
| `insufficient_points` | 402 | ⚠️名字全变(≠POINTS_EXCEEDED)！点数不足/无会员，升级（`extra.cost,remaining`）|
| `account_disabled` | 403 | 账号冻结，联系客服 |
| `capability_denied` | 403 | 该员工无此能力 |
| `not_priced` | 409 | 无计费配置（fail-closed）|
| `duplicate_pending` | 409 | 同 request_id 处理中，稍候用同 id 重试取结果 |
| `duplicate_failed` | 409 | 同 request_id 上次失败（已退点），换**新** id 重试 |
| `rate_limited` | 429 | 太频繁，稍后再试 |
| `upstream_error` | 502 | 出图/对话失败，可重试（已退点）|
| `moderation_unavailable` / `service_unavailable` | 503 | 服务暂不可用（已退点 / fail-closed 兜底）|
- 幂等命中（同 request_id 上次成功）直接返原图、带 `idempotent:true`，**不是错误**。

## 6. 客户端行为规范
- **config 重构**：移除 `ai_api_key/ai_base_url/ai_model/image_model`；`redbeacon-config` = **平台登录 + 飞书 + 代理**。
- **临期提醒**：读 checkin/生图响应 `renewal_reminder` → 过期前 5 天起、每天≤2–3 次（客户端节流）。
- **号数软控**：`max_xhs_accounts` = free 1 / Pro 3 / Max 5。客户端本地软控、可破（"能破就破不投入"）；✅ **值由 checkin `entitlements[].features.max_xhs_accounts` 下发**、客户端无脑读不硬编码（⏳ 平台未实现、暂容错 None/按 tier 约定值）。**不卖无限号、不打矩阵卖点。**
- **弃解锁码**：下线 `services/license.py` 离线强制点（机器码降级为防滥用指纹）。
- **doctor**：`redbeacon doctor` 检运行时（Python/uv、playwright）+ 令牌有效性 + 小红书 cookie + checkin 连通性，给可执行修复。
- **结构要求**：账号对接代码与小红书业务逻辑**物理隔离、可单独拎出**——RedBeacon 当参考实现，接第二个员工时抽成共享 SDK（login/令牌存取/Bearer/checkin/错误码映射/doctor）。
- **赠点（计费兜底）**：free 每日 50 点（自然日重置不累积）+ 新账号首次 checkin 迎新一次性 100 点，并入共享池；客户端零改动（照旧读 `points.remaining`，全空才报 `insufficient_points`）。换算：文案 1 点/次≈50 篇/天、生图 10 点/张≈5 张/天。⚠️🔴 **时序红线**：赠点要等平台上线才生效，**上线前别在 UI/官网承诺"免费试用额度"**。

## 7. 大模型对话接口 = `POST /v1/chat/completions`（文案/定位/选题的 AI）
OpenAI 兼容透传 + 平台契约：设备令牌、`request_id` 幂等、按次扣固定点（现 1 点/次、成功才计、失败/中断回补）、支持 SSE 流式。

**请求** `{ messages:[{role,content}], request_id(必·≤64), stream?(默 false), temperature?, max_tokens?, product?:"redbeacon", capability?:"llm_chat" }`
**非流式响应** `{ created, request_id, message:{role:"assistant", content}(⚠️ 文案在 message.content), model, points:{cost,used,total,addon:0,remaining}, renewal_reminder, idempotent? }`
**流式**（`stream:true`，`text/event-stream`）：`data:{"delta":"增量"}` 拼接 → `data:{"done":true,request_id,points,renewal_reminder}` → `data:[DONE]`；上游中途失败发 `data:{"error":...}`（已回补）无 [DONE]；客户端断连服务端中止上游并回补。

**落地**：`generate` 写文案 = 调本接口（system 放账号定位拼的提示词骨架、user 放选题 brief → 取 `message.content`/拼 delta → 渲染/入库/出图）。定位起草、选题补题同理。每次新 `request_id`（uuid）、重试用同 id、终态失败换新 id。限频 20/分/账号超 → `429 rate_limited`。fail-closed：平台不可达/点数全空 → 写不了文案（与生图同，"独立性依托平台"的既定代价）。

## 8. 飞书读写：CLI 直连、不走平台网关
每用户自带飞书应用、钥匙只碰自己飞书 → CLI 直连飞书 API。平台网关只管 AI/生图、不持飞书凭证、不加延迟。

## 9. 待平台确认（不阻塞主链路）
1. ⏳ checkin `features` 块（号数 `max_xhs_accounts` 下发，已选 B 平台下发）待平台实现；mimic 软解锁归 Pro/Max 平台未定，v1 可先不做。
2. checkin 暂无公告字段，MVP 不做公告。
3. 图生图待平台部署上线后联调真接口（§4.1）。

---
> **changelog**：① 过渡态（回退直连 aihub）已废止——平台后端已上线在产，客户端直接正式态、零上游 key。② 原"文案走宿主免费/路 B"已整条退役（2026-06-27 转向）→ 文案/定位/选题改走对话接口（§7）、铁律#2 已改写、计费改每日赠点（§6）。③ 算力点从"挂 entitlement"改为账号级 `membership` 共享池；令牌存共享账号目录（非 redbeacon 私有）。
