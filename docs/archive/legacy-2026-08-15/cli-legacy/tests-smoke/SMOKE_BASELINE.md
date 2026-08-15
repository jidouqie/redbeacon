# 独立 UI 第一刀 · 前置冒烟基线（开工前 2026-06-27）

> 目的（开工指令 §5）：动 UI 前先确认手头那套重构没塌，给 UI 一个稳地基。
> 本机限制：飞书 app_secret **本机解不开**（见 memory `feishu-creds-undecryptable-here`），
> 故"四表 live 读写 / status 飞书真取数 / generate 走平台对话 / publish move-to-archive"
> 这些**联网链路无法在本机 live 跑**；离线能跑的全跑了，live 部分以**桩件用例测**覆盖逻辑、
> 真接口留 `tests/smoke/feishu_live_smoke.py` 给能解密的环境。

## 离线冒烟结果（本机可跑）

| 项 | 结果 | 说明 |
|---|---|---|
| `import redbeacon` | ✅ | editable→src，version 0.1.25 |
| `redbeacon --version` | ✅ | `redbeacon 0.1.25` |
| `redbeacon status`（空库） | ✅ | fail-soft 正常：空 accounts、platform_logged_in=false，无异常 |
| 全 .py 模块 import | ✅ | 见 `import_all_smoke.py` |
| 既有 pytest（database/部分 config） | ✅ 11 passed | |

## 既有用例里的"陈旧测试"（**非本刀引入**，route-B/WP1 重构遗留，需另窗口更新）

- `tests/test_generate_helpers.py` → 导入 `_fix_embedded_quotes`（route-B 已删该符号）→ collection error。
- `tests/test_config.py::test_encrypted_field_stored_encrypted` / `::test_get_all_public_sentinel`
  → 断言 `ai_api_key` 为加密键，但 route-B 已把 `ai_api_key` 从 `ENCRYPTED_KEY_NAMES` 移除 → 失败。

> 结论：地基健康。3 个失败用例全部指向 route-B 重构**故意删掉**的符号/键，属测试未跟上、
> 不是回归。本刀不动这些（属别的工作包），仅在此登记，建议归属窗口更新。

## Live 飞书链路（本机解不开密、留脚本）

`tests/smoke/feishu_live_smoke.py` —— 在能解密 app_secret 的环境用
`REDBEACON_DATA_DIR=/tmp/rb_e2e` 跑，覆盖：四表 resolve、status_counts fail-soft、
审核表 list-pending→改→写回。本机未执行。
