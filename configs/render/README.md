# 公共渲染预设

此目录为第4批迁移后的默认寻址位置。三份JSON逐字节复制，未调参：

- `room_fire_round3.json`：已验收的Room8 V1艺术基线，当前默认。
- `room_fire_round1.json`、`room_fire_round2.json`：用于历史对比与回归，不自动选用。

`app/room_fire_round*.json`暂时保留为旧路径兼容副本；本轮不删除。安装包要求新旧副本SHA256一致，避免两套配置静默分叉。后续如果调整预设，须单独授权、审核，并同步处理兼容策略；本轮不进行此操作。

JSON中的art/events/quality及R3批准指纹不变。正式画质仍由任务preset决定，不能通过文件迁移绕过R3审核。配置源文件与任务`config_snapshot.json`职责不同；历史任务快照不会随迁移更新。

真实户型、appkey、模型、图片、视频或运行报告不得放入本目录；打包仅接纳这三份命名预设。
