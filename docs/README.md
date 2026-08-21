# RedBeacon 当前文档入口

RedBeacon 当前是一套以本机客户端为主、可由五种 AI 助手协同操作，并支持账号级全流程自动化值守的小红书运营数字员工。公开根仓只包含 Skill、安装脚本、公开说明和非敏感辅助内容；客户端与 CLI 核心源码位于私有仓库。

本目录只让当前维护资料停留在主路径，历史方案统一放入 `archive/`。阅读顺序如下：

1. `../AGENTS.md`：当前产品事实、架构边界、安装更新和发布纪律的最高优先级真源。
2. `../README.md`：面向使用者的最新能力、固定安装入口，以及开源 Skill / 专有内核边界。
3. `../RedBeacon-测试版验证指南.md`：测试通道安装、卸载和包含自动化、对标、审稿、发布在内的人工验收。
4. `local-desktop-build.md`：当前 macOS / Windows 双平台构建和源码客户端启动入口。
5. `download-node-integration.md`、`download-node-project-intake.yaml`、`download-node-project-receipt.json` 与 `../release/release-contract.json`：受保护的下载节点与发布契约，禁止归档或改写为历史方案。

`download-node/releases/` 主路径只保留近期完成的发布回执，以及尚未完成的当前发布回执。更早回执进入 `archive/legacy-2026-08-15/release-receipts/`，不参与构建和发布。

`archive/` 中的文件仅用于追溯，不是当前操作说明。维护、实现、构建和发布时不得把归档内容当作依据；需要恢复其中方案时，必须先由用户明确提出。
