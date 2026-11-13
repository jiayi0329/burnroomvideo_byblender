# 阶段性发布与基线记录

更新：2026-11-07。只记录经过证明的交付与限制；不把 PRD 文档版本或 V6–V9 路线图当成产物标签。

## Room8 V1 演示基线

| 字段 | 值/结论 |
| --- | --- |
| 产品状态 | 用户接受为阶段性演示，保留已知问题，暂不重新渲染 |
| 基线源码提交 | 6725223dd6a1502bfe144411b6c94575be0ac210 |
| 整理分支 | chore/room8-v1-baseline |
| Git tag | 本轮检查尚无指向该提交的标签；建议名 room8-v1-demo，未代用户创建或推送 |
| 场景 / 房间 | KK-EEz16cmU14 / Room8 |
| 基础资产版本 | 20261102T025550Z-7f677509 |
| 正式任务 / 批次 | 20261105T040552Z_91f5fb7d / 20261105T040552Z_2a5151 |
| 配置 | app/room_fire_round3.json，原艺术/传播配置冻结 |
| 视频 | fire_final.mp4；24秒，1280×720，24fps，576帧；H.264/yuv420p/faststart |
| 相机 | 全帧独立 Room8_Overview，ORTHO；有效正交尺度约16.217573 |
| 时序 | 内部13点，22号0秒，其余层1.5/3秒；32/42排除 |
| 地板/几何 | floor_z=-1.35m工程近似，11顶点，零外扩；6835源房间三角形+9演示地板面 |
| 实际渲染器 | NVIDIA L20/PCIe/SSE2，OpenGL，驱动580.178.04 |

### 文件指纹与来源

```text
candidate.json
5093a409ef38a278b70b1f342c5dc0da5876a3a039a5e761cc766a4821bfc2d0
room.blend
3123e1373296c866602f683a22c80d80d4ac1507cf4a86243ee44a4852f3bce1
room.glb
519c4ee5a12e5e1177c0e9babcbe3c1444b8d95909bf3c9aaaef0e72ff740fd1
room_fire_round3.json
af9854a21f47e840c837b9299584d4d7d9fd74dfa4fac19251e91873369d4202
fire_final.mp4
c339c91d12709797b43989c680474286e5b2641a64de160d3fde7902267404dd
```

8 份运行源码的字节指纹与任务 config_snapshot 中的 codes 全部匹配；经换行规范化后的内容也与 6725223、149fff4、d0c5f15 的相应源码一致。**原远端执行提交号没有记录**，不得将11月7日的基线提交写成11月5日的原始运行提交。新文档提交后也不改写这份代码对应关系。

### 实测性能

| 指标 | 远端实测 |
| --- | --- |
| 任务总时间 | 360.542秒，约6分0.5秒 |
| Blender进程 | 348.744秒 |
| 576次render调用合计 | 231.063秒 |
| 每帧均值 / 中位数 / P90 | 0.401 / 0.317 / 0.323秒 |
| 最慢帧 | 首帧50.495秒，不能仅凭该值认定具体初始化瓶颈 |
| 编码 / 探测 / 完整解码 | 9.215 / 0.747 / 0.258秒 |
| GPU采样 | 69次，约5秒间隔；GPU 0利用率峰值95%，显存1142MiB，温度56°C |

其他三卡采样利用率为0%，不是四卡并行渲染。指标为整卡采样，不是独占进程计量。总时间包含启动、场景、文件I/O、状态与视频处理；逐帧合计不能替代总时间。该结果只适用于这次Room8配置。

### 验收与尚缺证据

- 服务端基础blend重载、贴图、点位和坐标验证通过；GLB导出为自包含文件。没有把GLB结构检查等同于浏览器展示验收。
- 成片视频回执记录576帧/24秒/720p及整段解码通过；本地下载文件SHA一致。用户已播放查看。
- 本地归档核验129项通过；本地MP4检查为容器/样本表/文件边界检查，没有重新调用解码器或Blender。
- 原始 status 为 awaiting_visual_review，基础validation保留早期ready_for_fire_effects=false；原证据不改写。用户对V1演示的阶段性接受在本发布记录中另行表达，不伪造旧审批文件。
- 原始576张PNG帧未下载；4份R3原始参考文件未下载：sample_manifest.json、requested_config.json、overview_3.5s.png、repair_report.json。任务快照记录其SHA与机位参考，但不等于已保存原文件。

### 私有归档位置与恢复范围

私有本地根：`release/out/baseline-backups/20261107T082810Z_708ce646/`，由Git忽略，不能提交整个目录。

独立包：`verification_runs/20261107T084523Z_92e4711d/private-room8-v1.zip`，23,172,580字节，SHA256为 `7014ae7657abe5eaf9669d60c34a5970bbe4e2b4f887e20dcad60d0fa788f375`。

包保存24份收到的资产/任务文件，以及从指纹一致的本地副本补齐的candidate、8份源码与R3配置；另附核验清单。包外 verification.json 补充归档自身指纹，archive-catalog.sha256.json 记录本地文件清单。此前Git bundle、源码ZIP和140份私有数据的备份仍保留。

这是关键交付物基线，不含本地原帧续跑包，也不等于服务器镜像、数据库、MinIO的完整恢复备份。恢复到新目录再检查，不能将包直接解压覆盖当前场景。公开仓库只保存本脱敏记录，不携带真实户型或报告内容。

### 已知限制与后续版本

火焰生命周期偏短、后段烟雾主导；Hybrid未实现；火烟体积没有墙面几何遮罩；平层地板是工程近似；灾前重建未实现；其他房间未验证。此处登记问题，不触发V1重渲染。

下一次修改样式、时序、相机、裁切或源码应创建新任务并记录新指纹。后续main合并与tag不改变已交付资产/任务ID，也不宣称既有V1来自更新后的源码。

## 2026-11-12 工程基线服务器验收

证据来源为用户在远程SSH执行并回传的输出。本次验证目录迁移、操作日志及现有服务兼容性，不重新生成Room8 V1完整视频，不改写上面的原始发布证据。

### 代码与安装包

| 项目 | 核验结果 |
| --- | --- |
| 源码 | chore/room8-v1-baseline，3be7124e039cc64ad577cb6e3975253729fe26a4 |
| 包名 | burnroom-deploy-package-v1.0.0-20261112-150934814-ba781485.tar.gz |
| 包大小 / SHA256 | 327443字节；dec4aed391de55b9267b5d212324d103c4264e2de5e2eae396b95b36006d8c96；服务器sha256sum检查OK |
| 验收镜像 | burnroom-app:acceptance-3be7124，OCI revision与上述源码一致 |
| 应用入口 | uvicorn backend.api.main:app；使用新路径backend及render_engine |
| 本地回归 | 329项：327通过、2跳过，runner总耗时171.003秒；真实PG集成与可选Matplotlib跳过 |
| 安装包复核 | 136个文件，其中103份源码与工作区字节一致；安装包日志回归26项通过 |

### 远端结果与范围

| 检查 | 实际结果 | 不能据此宣称 |
| --- | --- | --- |
| 后端与配置 | GET / 返回200、Backend is running、appkey_loaded=true | 所有业务API均已实测 |
| HTTP操作日志 | trace=acceptance-3be7124-http；start/success落盘，耗时7.936ms，无损坏行 | 真实前端按钮链路已完成 |
| 数据库应用账号 | check_catalog返回ok、role=burnroom_app、tables_checked=8 | 6房间/22点及人工关联已导入 |
| Room8预检 | 固定基础资产、点位、R3参考及29份源码/配置保护通过 | 其他房间已通用验证 |
| 新版Blender入口 | camera_check / test / overview，输出3.5秒单帧，总耗时56.260秒 | 新版代码已完成576帧复测，或该耗时代表稳态逐帧速度 |
| 实际渲染器 | NVIDIA L20/PCIe/SSE2，NVIDIA Corporation，OpenGL 4.6.0，驱动580.178.04；software_rendering_suspected=false | 四卡并行或独占GPU |
| 任务日志 | start 3、accepted 1、success 3、progress 1；prepare、worker、job_attempt均success，malformed_lines=0 | 完整视频编码/失败恢复已在本次远端重测 |
| 旧视频分享 | 用户反馈Range读取返回206；测试经服务器localhost:9000并保留签名Host | 公网、校园网或浏览器连通性已重新验证；新版Room8已登记MinIO |

单帧任务为`20261112T075439Z_b67eb9b7`，attempt为`20261112T075439Z_a346fc`。任务目录：

```text
/app/data/KK-EEz16cmU14/rooms/Room8/render_jobs/20261112T075439Z_b67eb9b7/
```

检查图为`keyframes/overview_3.5s.png`，状态保留`awaiting_visual_review`；尚无本次检查图的明确人工视觉通过反馈。任务日志trace为`b489b65c38114040b13dbc48f0ad65eb`，位于该attempt的`operations/`。服务操作日志位于`/app/data/logs/operations/`。

基础资产仍为`20261102T025550Z-7f677509/asset`；配置为`/app/configs/render/room_fire_round3.json`。固定R3参考为该资产版本下`style_round3/20261104T020954Z_a023be3c/sample_manifest.json`。没有修改第三轮艺术参数、数据库数据、原始模型或历史视频。

### 当前部署组合与回退

只重建了app-server容器，PostgreSQL和MinIO保持原服务。Runtime为nvidia，NVIDIA EGL/GLX库可加载；数据挂载继续为`/data/zhaojy/burnroom-data/app-data -> /app/data`，原环境配置保留。

验收代码解压位置：`/home/zhaojy/burnroom-prod/acceptance-3be7124-20261112T072559Z-2542924/burnroom-deploy-package`。

**当前运行依赖三份Compose文件**：原`docker-compose.yml`、原`docker-compose.gpu.yml`，以及下列override；override仅替换应用镜像及新路径启动命令，不含凭证：

```text
/home/zhaojy/burnroom-prod/acceptance-3be7124-20261112T072559Z-2542924/app-image.override.yml
```

原Compose的latest镜像没有改标签。后续重建/更新app-server需保留三文件组合；仅运行原Compose的up可能切回旧镜像。以下命令仅供后续维护，**在远程SSH的原Compose目录执行**，不因阅读文档自动运行：

```bash
accept_override="/home/zhaojy/burnroom-prod/acceptance-3be7124-20261112T072559Z-2542924/app-image.override.yml"
docker compose -p burnroom-deploy-package -f docker-compose.yml -f docker-compose.gpu.yml -f "$accept_override" config --quiet
```

部署前保护脚本执行成功，回传备份目录`/data/zhaojy/burnroom-data/deploy-backups/20261112T072324Z-2543781`及旧镜像标签`burnroom-app:rollback-20261112T072324Z-2543781`。脚本的数据库备份受运行条件控制；本次没有提供dump大小/指纹或隔离恢复结果，不能据此宣称数据库恢复已验收。

若需回退，先冻结新任务并核对无活动任务，建立独立rollback override，仅设置`services.app-server.image`为上述旧镜像标签。使用原base、GPU及rollback三文件，**不叠加验收override的新路径command**，先config检查，再只对app-server执行`up -d --no-deps --force-recreate --pull never`。旧入口由原配置/旧镜像提供；不清空数据盘、数据库或其他容器。该回退路径已记录，尚未实际执行恢复演练。

### 结论与下一步

新路径、HTTP日志、应用账号目录检查、新版Room8单帧GPU及任务日志、旧视频Range读取的最小服务器验收通过。检查图人工审核仍独立保留；本次不代替原V1的完整视频验收。

下一步提交本次文档记录，复核main最新状态与差异后，由用户审阅并决定合并main；不以真实数据库导入或前端完成作为本轮合并前置条件。之后依次进行真实数据导入、新版MinIO登记、Room8/R3任务API和最小网页。尚未执行merge、tag或新完整视频渲染。

## 2026-11-13 真实数据库导入验收

证据为用户回传的远程SSH输出。既有验收镜像`burnroom-app:acceptance-3be7124`未重建。当前本地main及origin/main指向f29d662，已包含上述工程基线记录；本次不再执行Git合并或修改原Room8 V1证据。

生产库burnroom首次导入成功：场景KK-EEz16cmU14，layout_version_id=1，6条房间、5条有效、22点，xy_verified=true，输出assets=29。相同输入再次apply复用版本1，返回reused=true、review_preserved=true。burnroom_app目录检查ok；关键人工关联及房间列表API与[数据库验收表](database.md#本次实际验收)一致。

导入前备份目录：`/home/zhaojy/burnroom-prod/db-backups/20261113T062919Z-2763655/`，保存dump、archive-list、两份核验输入及restore.log。用户显示dump约31KB，pg_restore --list可读取；恢复到独立`burnroom_verify_20261113063131_2763655`退出码0，业务表8、迁移1，场景/房间/点位均0。没有恢复覆盖生产库，备份及验证库保留。

| 文件 | 用户实测SHA256 |
| --- | --- |
| burnroom.dump | e3f9d5e686a223d1fd814cd84a86bcdd559b23e96640ee32d4abefff6c4d25b9 |
| alignment_report.json | 95bdfd18aa233a718b6f21114fd84f3bd102dee68ea07561e46860c6c0114b8b |
| review.json | 883de043a2a8106b8daac1299fe99a7f598ddfc200eeb4c91fbaffdb8c95bfdc |

这是导入前备份恢复、实际导入、幂等、人工关系和API查询的验收；未做生产故障回滚、导入后全库恢复或全部原文件重新验SHA，导入日志trace也未单独提取。未启动渲染、上传MinIO或变更R3配置；29份输入文件索引不代表Room8模型/视频登记完成。下一步为新版Room8产物上传核对与关系登记。

## 2026-11-13 Room8产物上传与登记验收

证据来自用户回传的远程SSH输出。开发分支为feat/room8-web-registration-api；源码已提交822528a。实际执行的是独立代码包，不冒充服务镜像已升级：

- 包：burnroom-deploy-package-v1.0.0-20261113-151113333-67a9f9fb.tar.gz，347144字节。
- SHA256：5a36693d3b054017c36cc5765939eb51824386e944a37b4579aca62f2871135a；用户服务器校验OK。
- 容器代码目录：/tmp/room8-registration.81IX4m。后台服务仍是验收镜像burnroom-app:acceptance-3be7124；本次没有重建容器或部署整个分支。
- 资产版本仍为20261102T025550Z-7f677509，文件任务仍为20261105T040552Z_91f5fb7d，未重新渲染。

| 检查 | 远端实际结果 |
| --- | --- |
| 首次登记 | layout_version_id=1，database_room_id=6，database_job_id=1，file_count=6，reused_job=false，upload_status=verified，registration_status=registered |
| 再次登记 | 同一数据库任务1，reused_job=true，仍verified/registered；上传器逐对象回读验证后复用 |
| 数据库资产 | room_blend 1、room_glb 1、room_preview 3、room_video 1；6份均有bucket/key |
| 任务关系 | SQL任务1为done；实际渲染输入1份room.blend、视频输出1份；GLB及三视图仅关联房间 |
| 查询与签名 | 既有catalog资产列表及share接口可用；视频资产ID=64，七天签名有效期604800秒 |
| 视频读取 | 服务器localhost:9000连接，保留签名Host，Range bytes=0-0返回206、video/mp4、1字节 |

首次回执：`/app/data/KK-EEz16cmU14/rooms/Room8/registrations/20261113T105526Z_09bb04ba/registration_receipt.json`。

重复登记回执：同一registrations根下`20261113T113520Z_9d510484/registration_receipt.json`。两次独立保存，未覆盖原任务证据。模型/三视图使用burnroom-room-assets，视频使用burnroom-room-outputs；与旧桶分离，不改变Legacy分享策略。

本次验收证明6份指定交付的上传回读、数据库关联、重复登记和服务器侧签名Range读取；不代表所有运行报告/原帧已上传，不是新增完整视频渲染/解码或浏览器整段播放验收，不证明公网可达。CLI关联日志已实现并指定持久化目录，但此次未单独提取完整trace或注入远端失败；不能将这些列为已实测。当前库的登记前备份命令已提供，用户未回传该备份的具体路径及校验输出，不将其与前一节已验证的导入前备份混同。

第一批完成；同一分支下一批为新版Room8/R3任务API，再下一批为最小网页及真实按钮日志。既有catalog查询/分享不等于已有任务创建API。新分支未合并main，本条只补验收记录。
