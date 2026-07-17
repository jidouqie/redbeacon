# RedBeacon · Claude 兼容入口

本项目后续以 Codex 维护为主。当前权威入口是 [AGENTS.md](AGENTS.md)，发布前测试方法见 [RedBeacon-测试版验证指南.md](RedBeacon-测试版验证指南.md)。

保留本文件只为兼容仍会优先读取 `CLAUDE.md` 的旧工具。不要在这里新增项目规则；新规则请写进 `AGENTS.md`。项目只构建干净制品树，不管理 OSS、下载节点或 manifest 切换；公开发布仅使用全局 `bytestaff-digital-employee-publish` Skill。

旧 GitHub 打包方案与旧项目内 OSS 发布方案已封装进 `.history/` 下的二进制冷归档。除非用户明确要求查看或恢复，旧工具同样不得列出、读取、解压、搜索、比较或引用该目录，也不得从 git 历史恢复旧 workflow/发布脚本；所有维护直接回到 `AGENTS.md`、中央接入契约和当前构建/安装代码。
