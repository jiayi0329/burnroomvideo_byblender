# 房间边界与任务起火点：只读元数据方案

当前状态（2026-11-18）：副本核验、远端CPU隔离、限定备份和用户批准的app-server更新均已完成，生产GET返回200，本机网页已启用真实摘要并通过边界/点位/历史起火点浏览器核验。当前镜像为`burnroom-app:spatial-readonly-aded5eb08095`，证据见[RELEASES](RELEASES.md)与[演示清单](DEMO_20261119.md)。以下方案形成于11月17日，历史待办文字不改变此最新状态；22号标记来自实际冻结文件核验，不能由源码约束推断生成。

## 已找到的来源与适用范围

| 来源 | 确认的字段 | 能说明什么 |
| --- | --- | --- |
| render_engine/geometry/prepare_room_candidate.py生成candidate.json | polygon_raw_xy、ignition_device、interior_devices、boundary_devices、floor_z、provenance、source_fingerprints | 候选裁切边界与当时输入的起火点；须由已验证资产指纹绑定，不能任选最新候选 |
| render_engine/blender/F8_prepare_room_asset.py生成asset/manifest.json | candidate_sha256、clipping_parameters.polygon_raw_xy、engineering_policy.floor_z、raw_to_asset_matrix、glb_coordinate_mapping、点位/成员及artifacts SHA | 基础资产采用的裁切输入和坐标约定；不证明物理墙厚或真实地板 |
| config_snapshot.json | signature、inputs.asset、inputs.points、inputs.guards、inputs.timeline.start_point/allowed_devices/spread_events | 特定历史任务冻结的输入；是该任务起火点的优先来源，不能被当前场景timeline替代 |
| 现有/api/catalog及/api/room-jobs | 动态房间主键、资产SHA、已核验点位关系、文件任务号/版本与状态 | 目录与文件身份关联；当前没有边界和实际起火点的网页字段 |

当前工作站没有可据此独立复核的candidate/manifest/任务快照私有副本；已有MinIO登记的GLB、三图与视频不等于原始报告已全部上传。当前SSH仅由用户保持只转发9000的隧道，不应绕过该边界猜测文件访问地址或遍历MinIO对象。

## 本地已实现的最小接口（未部署）

实现位于backend/services/room_spatial_context.py，经原room_jobs路由与日志上下文调用：

`GET /api/room-jobs/{job_id}/spatial-context?scene_code=...&room_id=Room8`

以明确文件任务身份解析来源，复用既有安全路径/快照校验。请求不接受文件路径、任意配置或目录；不返回原始完整快照、guard绝对路径、review正文、凭证或签名URL。当前必须明确关联历史任务，不提供无任务的资产摘要，也不隐式取“最近任务”。

摘要应包含：

- schema_version、scene_code、room_id、layout_version_id、asset_version、file_job_id。
- source：候选/manifest/快照相关文件SHA和原坐标约定；按实际核对结果填写，不假造指纹。
- boundary：有限的原始XY多边形、工程近似floor_z及policy；不是墙面语义、真实净高或CFD边界。
- ignition：从该任务快照提取的点位号、经核对的原始坐标与来源；不接受浏览器传入的新点位。
- 有限成员列表和核验结论。证据缺失、过期或不一致时返回明确错误，不退回当前场景值或客户端推断值。

## 校验顺序

1. 按现有允许根和标识校验定位任务；验证原快照签名、场景/房间/资产版本及冻结输入，不改快照或重新签名。
2. 验证本地manifest、candidate及GLB的SHA关联；manifest的candidate_sha256须匹配实际候选，任务guards也须匹配所使用的文件。原历史源码指纹不能用当前源码替换。
3. 核对候选、manifest、快照中的版本/成员、点位源SHA和坐标映射；多边形只接收有限数值、有效顶点数和非退化结果，不由GLB包围盒反推边界。
4. 起火点优先取inputs.timeline.start_point，须存在于该任务allowed_devices和已核验内部点中；与候选绑定不一致即拒绝，不能把门口点当内部起火点。
5. 前端原始点/边界仅转换一次(x,y,z)→(x,z,-y)，模型保持原导出坐标；用独立标记显示已证实的历史起火点，保留“只读查看”的语义。

catalog资产列表目前没有逐项asset_version字段。扩展多版本时需显式返回与sources版本对应的GLB/检查图ID，不能按列表第一项或mtime挑选。现阶段仅Room8单一登记版本已实测。

## 计划验收与后续边界

实现时须新增缺失/篡改文件、签名不符、场景/版本错配、路径越界、错误成员/起火点及坐标转换回归；通过现有operation_logging记录请求、核验阶段、结果、耗时、trace/request/job上下文，并验证脱敏。只读失败不触发渲染、不写数据库、不修复历史文件。

代码实现、服务器原文件只读核验及部署分别验收。在摘要经真实证据核对前，网页继续不画边界或标起火点。随后才安排受控测试任务：明确确认、幂等键、服务端允许列表、正式档审批及可信操作日志；自由参数和公网仍单独排期。

## 本地实现的具体行为

成功返回schema_version=1、scene_code/room_id/asset_version/file_job_id，boundary（原始XY闭合边界和工程近似floor_z）、ignition（冻结任务起火点和原始XYZ）、members、坐标约定及必要文件SHA。verified仅表示file_consistency_only，不代表人工视觉或建筑语义认可。layout_version_id返回null，layout_binding=file_fingerprints_only，并提供alignment/review SHA；不猜旧任务的数据库主键。

缺少任务返回404/job_not_found；已存在任务的证据缺失返回409/spatial_evidence_missing；签名/版本/路径/指纹/边界/成员不一致返回409/spatial_evidence_invalid。其他房间及非法标识由参数校验拒绝，写方法返回405。JSON拒绝重复键与非有限数值，单文档限16MiB；边界限128个不同顶点（允许输入重复首尾点），拒绝退化和自交，坐标绝对值上限1e6米。读取末尾再次核验数据指纹，原历史源码guard不拿当前代码替换或重新签名。

不连接数据库、MinIO，不启动Blender或执行迁移；JSONL阶段日志复用operation_logging。部署包白名单已纳入新模块，但没有执行部署。前端本机代理仅扩展GET/HEAD允许路由，页面尚不自动调用该接口或展示边界；服务器原文件验证后再安排展示与受控任务提交。

2026-11-17真实文件副本核验补充：用户通过只读SSH复制7份指定原文件到本机忽略目录后，新服务按同一校验逻辑通过；结果为11个边界顶点、工程floor_z=-1.35、起火点22、13个内部点与1个边界/门口点，candidate/GLB匹配V1公开归档指纹，副本读取前后不变。实际坐标格式是pose.translation，已增加兼容与冲突拒绝回归；这仍不是已部署API的在线验收。
