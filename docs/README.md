# 文档入口

更新：2026-11-11。文件用途总表只在[根README](../README.md)维护；本页提供阅读入口。Room8 V1暂不重渲染，源码已结束app/release/test兼容期。

| 问题 | 当前有效文档 |
| --- | --- |
| 产品目标、MVP与验收 | [PRD](PRD.md) |
| 当前链路、组件与边界 | [ARCHITECTURE](ARCHITECTURE.md) |
| 已完成、待实施及下一步 | [PROJECT_STATUS](PROJECT_STATUS.md) |
| Room8 V1资产/任务/视频/实测 | [RELEASES](RELEASES.md) |
| 分类标准与依赖方向 | [PROJECT_ORGANIZATION](PROJECT_ORGANIZATION.md) |
| 编号、版本、文件与存储关系 | [DATA_ASSET_SPEC](DATA_ASSET_SPEC.md) |
| 房间裁切、基础资产与展示 | [房间资产](rendering/room_assets.md) |
| 当前R3火烟/灯光与六张样帧 | [R3风格](rendering/style.md) |
| 完整包、总览动画、GPU证据和续跑 | [动画运行](rendering/animation.md) |
| PostgreSQL现状及真实导入计划 | [数据库](database.md) |
| 老师要求的操作时间线/监控 | [日志实现、使用与待验收边界](OBSERVABILITY.md) |

当前指南标出环境，命令存在不等于授权执行。源码与资产换版本后应新建任务；旧全场景HTTP渲染不能代替Room8入口。

历史资料合并为[主题归档](archive/20261111_process/README.md)：风格三轮、动画/相机/GPU、房间核验/裁切/展示、目录迁移、数据库旧流程和测试过程。原文在源码块中，不作为当前命令；manifest记录来源提交与指纹。更早原始需求/架构/约束快照在[2026-11-07归档](archive/20261107_pre_baseline/README_ARCHIVE.md)。

维护规则：产品变化写PRD，技术边界写Architecture，进度写PROJECT_STATUS，交付事实写RELEASES，操作方式写对应指南。不把每轮脚本改动重复追加到所有文档，不把计划写成已部署事实。
