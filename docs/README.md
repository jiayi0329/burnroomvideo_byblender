# 当前文档入口

更新：2026-11-07。本轮是工程基线整理；Room8 V1 暂不重新渲染。

| 要了解的内容 | 当前文档 |
| --- | --- |
| 产品目标、MVP和验收 | [PRD](PRD.md) |
| 已有调用链与目标系统 | [ARCHITECTURE](ARCHITECTURE.md) |
| 完成度、风险与下一步 | [PROJECT_STATUS](PROJECT_STATUS.md) |
| Room8 V1版本、视频、耗时和归档 | [RELEASES](RELEASES.md) |
| 目标目录、逐组映射、迁移前提 | [PROJECT_ORGANIZATION](PROJECT_ORGANIZATION.md) |
| 第4批引擎目录、完整代码包与兼容边界 | [room_engine_migration](room_engine_migration.md) |
| 编号、路径、数据库/MinIO对应关系 | [DATA_ASSET_SPEC](DATA_ASSET_SPEC.md) |

## 操作资料与适用范围

- [正式动画](room_animation_final.md)、[相机修复](room_animation_camera_fix.md)、[GPU修复](room_gpu_fix.md)：保留运行依据，**本轮不执行其渲染/重建命令**。成功GPU路径以当前生产配置和RELEASES实测为准。
- [R3静帧](room_style_round3.md)：当前样式依据；[R2](room_style_round2.md)、[R1](room_style_round1.md) 为实验追溯，不作为下一轮自动调参指令。
- [候选与独立资产](room_candidate.md)、[展示派生](room_display.md)：仅在另行授权生成资产时使用；当前基础房间已存在。
- [旧资产核验](room_asset_checks.md)、[断面诊断](room_section_diagnostics.md)、[最初动画测试](room_animation.md)：保留历史过程；等待物理地板完全确认、必须再跑短片等旧阶段要求不阻塞当前工程整理。
- [数据库操作](database.md)：已有部署/迁移/导入说明；真实导入尚未完成，本轮不执行。
- [脚本职责索引](../app/README.md)、[测试约定](../test/README.md)：保留现有路径与追溯引用；具体完成度以PROJECT_STATUS为准。

旧F8根场景API与新版Room8任务不互通。查看文档不表示授权触发旧API、重建容器、重渲染或导入数据库。

## 历史材料

原始PRD、架构、README与CLAUDE按字节复制到 [2026-11-07历史快照](archive/20261107_pre_baseline/README_ARCHIVE.md)，附SHA256。根PRD/architecture/README保留原内容并增加当前入口提示，兼容旧链接。

当前文档不逐次追加脚本修改日志：产品变化写PRD，组件/协议变化写Architecture或规范，完成状态写PROJECT_STATUS，已交付基线写RELEASES。历史资料不作为新的执行指令；会话中的最新用户授权与硬性进程/数据保护约束仍适用。
