# RedBeacon 项目文档归档

本目录保存历史产品方案、平台接入细节和旧测试清单。它们有参考价值，但不再是当前维护入口。

当前维护优先级：

1. 根目录 [AGENTS.md](../AGENTS.md)：Codex 后续维护的当前事实与工程规则。
2. 根目录 [RedBeacon-测试版验证指南.md](../RedBeacon-测试版验证指南.md)：测试版安装、下载路径、隔离矩阵和发布前验收。
3. 根目录 [README.md](../README.md)：面向项目读者的当前简介。
4. 代码和脚本事实源：全局 `bytestaff-digital-employee-publish` Skill、`docs/download-node-*`、`install/`、`tools/build_desktop_local.sh`、`tools/build_channel_skills.py`、`cli/src/redbeacon/services/updater.py`。

本目录里提到的飞书主链路、PM 双窗口、旧官网、旧分发方式、Cloud/Claude Code 作为唯一维护方式，均按历史资料处理。后续如果要恢复某个能力，必须先回到代码和当前发布流程里重新设计，不要直接照搬旧文档。

仍可查阅的深度资料：

| 文档 | 用途 |
|---|---|
| `RedBeacon-平台接入开发规范.md` | bytestaff 平台 device flow、checkin、AI 接口和错误码的历史接入细节 |
| `RedBeacon-代码架构规范.md` | 六边形架构和核心用例收口原则的背景资料 |
| `RedBeacon-skill改版-现状与任务.md` | skill 本机化改版的历史记录 |

旧构建方案的冷归档刻意不列入文档索引，也不参与日常上下文；只有用户明确要求恢复时才允许查阅。
