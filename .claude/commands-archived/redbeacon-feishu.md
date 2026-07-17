---
description: 飞书多维表格绑定 — 💤 现阶段搁置（默认纯本机，无需绑表）；以后线上模式再启用
argument-hint: 一般不用；飞书已搁置，审核/选题/发布数据都在本机
---

> 💤💤 **飞书现阶段整体搁置（2026-07 起）** —— 这个 skill 暂时休眠，正常流程里**别用、别把用户往这儿引**。
>
> - 客户端**默认纯本机**：审核 / 改稿 / 选题 / 发布数据全在本地，**不需要绑任何飞书表**。
> - 审核改稿走 `/redbeacon-review`（我直接帮你标/改）或操作台审稿页（`redbeacon ui app --page 审稿`）。
> - onboarding 链路里**没有「绑飞书表」这一关**了：登录平台 → 建号 → 扫码登录小红书 → 定位，直接就能产内容。
>
> **用户主动问「怎么用飞书 / 要不要绑表」时**，如实说一句：「飞书云端同步这块现在先搁置了，数据都在你本机、直接用就行，不用配飞书；以后上线云端模式会再开。」然后把他带回正常流程（`/redbeacon-generate` 写、`/redbeacon-review` 审、`/redbeacon-publish` 发）。

---

## 以下是绑表机制存档（休眠中，仅供以后线上模式重启时参照，当前别执行）

> 下面这套「每用户自带飞书应用 → 复制四表模板 Base → 授权转移 → 按账号绑 app_token」的流程**代码仍在**（`feishu setup/test/perms` 命令保留），只是本阶段不走。将来启用飞书云端源时，再把这套接回 onboarding。

- **绑表**：`redbeacon feishu setup --account-id {ID}`（不传 `--app-token`=一键建四表并绑；传了=绑到已有 Base）。CLI 会复制审核模板表 → 取表 ID → 授权给用户 + 转移所有权 → 回写账号；已绑过的幂等复用。
- **测连通**：`redbeacon feishu test --account-id {ID}`（写测试行 + 发消息，逐项报）。
- **权限清单**：`redbeacon feishu perms`（自建应用要开的权限 JSON，单一真源，别在 skill 里手写第二份）。
- **全局凭证**：飞书 App ID / Secret / 通知 User ID 在配置里（现搁置，见 `/redbeacon-config` B 段的休眠说明）。

> 重启飞书时要做的事（备忘）：① `/redbeacon-config` 恢复飞书凭证段；② onboarding 重新插入「绑表」stage；③ 各 skill 把「本机」口径改回「随数据源」；④ 数据源开关重新在 UI 放出（`FEISHU_ENABLED`）。
