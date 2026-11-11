# 2026-11-11主题归档

此目录保存整理前原文，不是当前运行手册。来源提交为fd3b372，完整提交号和逐文件记录在[manifest.json](manifest.json)。原文换行统一为LF，以Markdown源码块保留，旧链接/命令不作为活动指南；原工作副本SHA、Git blob和合并后内容范围均可核对。

| 合并文件 | 原资料 | 当前替代入口 |
| --- | --- | --- |
| [render_style_history.md](render_style_history.md) | R1/R2/R3三轮风格原文 | [R3风格](../../rendering/style.md) |
| [animation_history.md](animation_history.md) | 动画、相机修复、正式出片、GPU修复 | [动画指南](../../rendering/animation.md) |
| [room_assets_history.md](room_assets_history.md) | 导入核验、断面、候选、展示 | [房间资产](../../rendering/room_assets.md) |
| [engineering_history.md](engineering_history.md) | 引擎迁移、七批收尾、去重及原状态/架构/目录规范 | [当前架构](../../ARCHITECTURE.md)、[目录规则](../../PROJECT_ORGANIZATION.md) |
| [database_history.md](database_history.md) | 旧数据库部署与导入步骤 | [数据库计划](../../database.md) |
| [testing_history.md](testing_history.md) | 原tests/TEST_HISTORY.md | [测试入口](../../../tests/README.md) |

校验时先将整份合并文档规范化为UTF-8无BOM及LF，再计算archives.sha256或按字节范围提取normalized_content_sha256，避免Windows检出CRLF影响偏移。source_worktree_sha256记录原始换行字节，不能与规范化内容SHA混用。精确历史源码使用记录的提交/归档版本，不给旧任务换当前路径改签续跑。

更早四份原始规范快照及指纹在[2026-11-07归档](../20261107_pre_baseline/README_ARCHIVE.md)，此次保持原样。新开发从[根README](../../../README.md)或[当前文档索引](../../README.md)进入。
