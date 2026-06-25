# RedBeacon 客户端 · 平台接入开发规范（v1）

> 本文 = RedBeacon 客户端（CLI/skill）接入「数字员工平台」**线上后台**的操作规范，供客户端开发**照此对接**。
> **契约真源 = 平台文档**（bytestaff `项目文档/`：§3.3a 会员模型 / §5.4 生图网关 / §6 接口清单 / §9 错误码 / §14.6 客户端接入规范）。本文是**客户端侧落地指南**、不重复后端设计（避免第二真源）；本文与平台真源冲突时以平台真源为准，实现有偏离回报平台 PM 同步。
> 本文**已按最新平台校准**（会员重构 2026-06-24 + 平台上线 2026-06-25），**取代《RedBeacon-重构开发方案.md》§5 中与会员重构冲突的旧描述**（见末节「与方案 §5 的差异」）。
> 线上后台域名：`https://bytestaff.jiomig.com`（唯一入口，**勿硬编码**、走配置项；平台后端 T0–T5 已上线在产）。
> 编写：2026-06-25 · 平台侧 PM。

---

## 0. 铁律红线（违反任一 = 改方案，别绕）
1. **客户端永不持上游 / 中转站 key**——唯一凭据 = 账号级**设备令牌**。
2. **免费能力（定位/选题/文案/内容/文字卡渲染/发布）走宿主 AI + 本地**，不带令牌、不调平台、不烧平台钱。**只有「生图」带令牌调平台**。
3. **`account_id` 永远由服务端从令牌解出，客户端不传**（防 IDOR）。
4. **鉴权/扣点全在平台服务端、每次现查、fail-closed**——平台不可达即拒，客户端**不存"已解锁"本地标志**。
5. **两把钥匙别混**：客户端只持**设备令牌**（调平台能力）；**绝不碰网站会话**（那是浏览器/门户的）。⚠️ 故客户端**不调 `/me/*` 系列**（那些要网站会话、CLI 调会 401）——客户端要的会员状态**全从 `/device/checkin` 拿**。

---

## 1. 鉴权模型：账号级设备令牌
- 令牌 = device flow 签发、**账号级**（不绑单个员工）、可吊销、平台哈希存。
- **明文仅签发时返回一次**；客户端写本地后**存「共享账号目录」、非 redbeacon 私有目录**——将来第二个员工 skill 读同一份令牌即自动登录态（多 CLI 共享）。属用户自己的隐私数据、明文存本地隐私内核即可、不上传。
- 调平台一切能力带 `Authorization: Bearer <设备令牌>`。
- **令牌无 refresh 机制**（已知缺口）：过期/被吊销 → 重新 `login`。
- **不限设备数**（计费闸 = 账号点数池、设备数非闸）：连授多台都行，用户可在门户逐台取消授权。`DEVICE_LIMIT` 错误码已退役、别处理。

---

## 2. 登录 = OAuth 2.0 device flow
命令 `redbeacon login`（⚠️ 与登录**小红书**的命令是两套东西——后者改名 `redbeacon xhs-login`，命名别冲突；平台登录 ≠ 订阅 ≠ 小红书登录态）。

1. `POST /device/code`（无需登录，**带 `product_code=redbeacon`**）→ 返回 `device_code` / `user_code` / 授权短链（预填 user_code 的 `verification_uri`）/ `interval` / `expires_in`（10 分钟）。
2. CLI 显示 user_code + 短链，提示浏览器打开授权；按 `interval` 轮询 `POST /device/token`（带 `device_code`）。
3. 轮询返回：未授权 `authorization_pending` / 过快 `slow_down` / 成功 → 返回**设备令牌**（写本地共享账号目录）。
4. （用户侧）浏览器开短链 → 门户已登录态 → 点「授权这台设备」→ 平台 `/device/approve`，**授权成功时按需激活 redbeacon 的 free 使用权**。
- **别让用户在 CLI 输账号密码。**

---

## 3. 轻打卡 = `POST /device/checkin`（客户端会员状态的唯一来源）
- **时机**：每次 skill 启动拉一次（**不调 AI、近乎零成本**）——给平台可见性 + 客户端显示会员/点数/临期。
- **鉴权**：设备令牌(Bearer)。**入参**：`{ product_code: "redbeacon" }`。
- **按需激活**：账号对 redbeacon 无使用权 → 自动建一条 free（幂等、已有不动）。新 skill 首次打卡即自动进【我的员工】，连第二次 login 都不用。
- **响应（已冻结契约）**：
```
{ ok: true,
  activated,                       // 本次是否新建 free 使用权（幂等：已有=false）
  membership: {                    // ← 客户端显示「档/点数/临期」唯一来源
    tier, tier_name,               // free|pro|promax · 免费版/Pro/Max
    points: { total, used, remaining },     // 账号级共享点数池（跨所有员工）
    valid_until,                   // 到期(UTC)；free/不过期 = null
    status,                        // active(有付费会员) | free(隐式免费)
    renewal_reminder },            // 临期 {expiring_soon, valid_until, days_left}；否则 null
  entitlements: [ {product_code, product_name, status, valid_from, valid_until,
                  features} ] }  // 已激活员工；features=该员工×当前档解析的分档开关（如 {max_xhs_accounts}）= 软控数据源
}
```
- ⚠️ **点数只在 `membership.points`**——别去 entitlements 找点数（会员重构后那里没有）。
- 点数是**账号级共享池、跨所有员工**——**一份会员玩遍全平台收费能力**（可作卖点叙事）。
- `membership` 与门户 `GET /me/membership` 同源、含惰性过期（打卡即把到期会员翻 expired、`remaining/status` 永远现查真值）。

---

## 4. 生图 = `POST /v1/images/generations`（唯一平台计量能力）
- **鉴权**：设备令牌(Bearer)。**请求**声明 `product=redbeacon` / `capability=image_gen` / **`request_id`（幂等键）** + prompt / 尺寸 / 张数。
- **平台链路**：认令牌 → 查 redbeacon 使用权 → **原子扣账号共享点数池**（N = 张数 × 单价，当前 10 点/张）→ 调上游出图 → 落 OSS → 回**下载链接**。响应含：图片下载链接、本次扣的点数、**临期提醒标志**。
- **幂等**：同 `request_id` 重试 → 不重复扣点、返回原图链接。
- **失败不扣**（预扣后失败回补）。**点数不足 / 无付费会员 / 会员过期 → 拒、不调上游**（fail-closed）。
- **下载走 OSS/CDN、不碰平台服务器**：客户端拿链接直接从 CDN 拉图、缓存本地 `~/.redbeacon/data/images/`、照旧 cloakbrowser 发布。
- **生图失败/平台不可达只影响图**：纯文字卡笔记照样落库、可后补图。

---

## 5. 错误码 → 友好提示（§9）
| code | HTTP | 客户端提示 |
|---|---|---|
| `UNAUTHENTICATED` | 401 | 登录失效，请重新 `redbeacon login` |
| `NO_ENTITLEMENT` | 402 | 未激活该员工，去门户「加入我的团队」 |
| `ENTITLEMENT_EXPIRED` | 402 | 会员已过期，去网站续费会员 |
| `POINTS_EXCEEDED` | 402 | 算力点用尽 / 无付费会员，升级会员或下期再用 |
| （能力不可用 / 账号被冻结封禁） | 403 | 该能力暂不可用 / 账号状态异常，联系客服 |
| （重复 request_id 幂等命中 / 未计费） | 409 | （幂等命中：直接返原图链接，不报错给用户） |
| `RATE_LIMITED` | 429 | 操作太频繁，稍后再试 |
| （上游出图错） | 502 | 出图失败，请重试（不扣点） |
| `SERVICE_UNAVAILABLE` | 503 | 服务繁忙，稍后重试（fail-closed） |
- 402 是一个大类（会员/点数三种原因），按返回 code 分别给"去激活 / 去续费 / 去升级"提示。

---

## 6. 客户端行为规范（落地要点）
- **路 B**：`generate` = 渲染 + 入库 + 出图；文案 JSON 由宿主在 skill 层写好传入，CLI **不调文案 API**。纯文字卡全程零平台零成本；含 AI 图才带令牌扣点。
- **config 重构**：移除 `ai_api_key / ai_base_url / ai_model / image_model`（文案走宿主、生图走令牌、模型由平台服务端别名选）；`redbeacon-config` = **平台登录 + 飞书 + 代理**。
- **临期提醒**：读 checkin / 生图响应的 `renewal_reminder` → 过期前 5 天起、每天最多 2–3 次（客户端节流）；用户关了自动续费才提醒。
- **号数软控**：`max_xhs_accounts` = **free 1 / Pro 3 / Max 5**（已定值）。**客户端本地软控、平台不强校验**（可破，符合"能破就破不投入"）。✅ **值由 checkin 的 `entitlements[].features.max_xhs_accounts` 下发**（2026-06-25 选 B 平台下发）——客户端**无脑读、不硬编码**，平台改档位号数客户端不动。**不卖无限号、不打矩阵卖点。**
- **弃解锁码**：下线 `services/license.py` 的离线强制点（机器码降级为防滥用指纹、不再是授权手段）。
- **doctor**：`redbeacon doctor` 检运行时（Python/uv、playwright 内核）+ 登录态/令牌有效性 + 小红书 cookie + **checkin 连通性**，对常见故障给可执行修复动作。
- **结构要求**：**账号对接代码与小红书业务逻辑物理隔离、可单独拎出**——RedBeacon 当参考实现，接第二个员工时把这块抽成共享 SDK（封装 login / 令牌存取 / Bearer 调用 / checkin / §5 错误码映射 / doctor）。

---

## 7. 飞书读写：CLI 直连、不走平台网关
- 每用户自带飞书应用、钥匙只碰自己飞书 → CLI 直连飞书 API。平台网关只管 AI/生图、**不持飞书凭证**、飞书 ops 不加网关延迟。

---

## 8. 待平台确认 / 开放项（不阻塞主链路）
1. ✅ **已定（2026-06-25 用户拍板选 B）：checkin 补 `features` 块**下发分档功能（`entitlements[].features`）——号数 `max_xhs_accounts` 先下发、客户端无脑读（§3/§6 已据此改）；**mimic 待归档定后加**。⏳ 待平台开发实现 checkin 返回 features 块。
2. **仿写 mimic 软解锁**：归 Pro 还是 Max 平台**未定**；定 + 下发后客户端再接，**v1 可先不做 mimic 判断**（或粗判 tier≥pro）。
3. **公告**：平台 checkin **暂无公告字段**；MVP 客户端**不做公告**。
4. **接口逐字 schema**：§2/§4 的 device flow、生图字段以平台 §6 + 实际实现为准；**建议平台开发像 checkin 那样回报一次完整 JSON schema 冻结**、补进本文 §2/§4。

---

## 9. 过渡态已废止（重要）
平台后端**已上线在产**（生图网关真出图、真扣点验过）——客户端**直接做正式态（令牌走网关）**，**不必再实现"回退直连 aihub、不计费"那段过渡代码**，并据此**摆脱本地持中转站 key 的安全隐患**（方案 §5.1 痛斥的现状）。

---

## 附 · 与《RedBeacon-重构开发方案.md》§5 的差异（本文校准点）
- **算力点归属**：方案 §5.2"挂 entitlement"**已过时** → 现为**账号级 `membership` 共享点数池**（一份会员跨所有员工，§3.3a）。客户端拉点数走 `checkin.membership.points`。
- **过渡态**：方案 §5.7 的"回退直连 aihub"**作废**（平台已上线，直接正式态，本文 §9）。
- **令牌存储**：方案"存隐私内核目录" → 校准为**共享账号目录**（多 CLI 共享，本文 §1）。
- **补全方案漏项**：§9 错误码映射、临期提醒、生图 `request_id` 幂等、号数已定值 1/3/5 —— 本文 §5/§6 已纳入。
- 其余（路 B / 不持 key / 控制面数据面分离 / device flow / config 重构 / doctor）与方案 §5 一致。
