# 场景、房间、资产与任务的一致性规范

更新：2026-11-13。区分“本地实现”与“远端验收”；本场景关系导入已核对，首批Room8产物登记CLI已实现但未远端上传。职责见 [ARCHITECTURE](ARCHITECTURE.md)，版本示例见 [RELEASES](RELEASES.md)。

## 1. 业务编号与数据库主键

| 规范名称 | Room8 示例 | 当前字段及含义 |
| --- | --- | --- |
| scene_id（业务字符串） | KK-EEz16cmU14 | 现有 scene_code；数据库 scenes.scene_code。**不是 scenes.id 整数主键** |
| room_id（源房间字符串） | Room8 | 现有 manifest.room_id、rooms.source_room_id；须同时绑定场景和户型版本，不是 rooms.id |
| layout_version | 已核验输入与 review 的指纹 | 数据库 layout_versions.fingerprint；不是目录时间戳，也不等于单份 alignment_report 的 SHA |
| asset_version | 20261102T025550Z-7f677509 | 独立房间目录名；基础资产版本，不是 MinIO 对象 version_id |
| render_job_id | 20261105T040552Z_91f5fb7d | render_jobs 目录名；不是数据库 render_jobs.id |
| attempt_id | 20261105T040552Z_2a5151 | 一次执行/续跑批次，不另立一份业务任务 |
| point_id（源点位号） | 22 | points.device；数据库 points.id 仍是内部外键 |

房间关系身份为 `(scene_id, layout_version, room_id)`；资产身份还包含 asset_version；任务可定位为 `(scene_id, room_id, render_job_id)`，其配置必须绑定相应户型和资产版本。新户型不能复用同一目录覆盖旧版 Room8。

同一 `(scene_id, room_id)` 路径下，asset_version 跨户型版本也不得重复使用；render_job_id 也不得复用覆盖。同一文件多份相同SHA只是内容相同，不自动合并其业务来源。时间戳/UUID后缀是现有命名方式，不是全系统唯一性证明；当前create_job只保证本目录不重名，未来查询必须带场景/房间上下文或有可验证的唯一索引。

现有 CLI/JSON 仍使用 scene_code/room_id，现有 catalog API 路径仍接收整数 room_id。后续适配器显式转换，不能全局替换字段，也不能让浏览器把 `Room8` 传给已有整数路由。

业务编号保留原大小写及连字符/下划线，不因命名规范重命名既有版本。新接口只接受登记值，不把用户提供的字符串直接拼接成路径；解析到允许的数据根后须检查路径越界及符号链接，不接受绝对路径、`..` 或伪造目录分隔符。

## 2. 各存储位置的职责

| 位置 | 保存什么 | 权威范围与边界 |
| --- | --- | --- |
| GitHub/Git | 源码、测试、公共 R3 配置、SQL迁移、脱敏文档和发布信息 | 代码版本依据；不保存真实模型、户型、全景图、视频或生产凭证 |
| 本地 data/ | 从远端取得的资产、核验输入、离线检查结果 | 调试/备份副本；以 manifest 和 SHA 确认版本，不靠“最新修改时间”认定正式资产 |
| 服务器 app-data | 当前真实资产与任务目录、帧、状态、日志 | 当前 Room8 运行文件依据；部署代码更新不能覆盖这些文件 |
| MinIO | 经登记的版本模型/图片/视频/关键报告 | 已上传对象的内容依据；未上传的本地文件不能显示 uploaded=true |
| PostgreSQL | 场景、户型、房间、点位、文件及任务关联 | 关系目录与查询摘要；不是 Blender 的输入接口或另一套实时状态机 |
| 基线备份 | 固定版本的源码包、数据包、SHA清单 | 恢复副本，不是日常任务读取的“最新目录”；同盘副本不等于独立异地备份 |

当前 Room8 主要在文件目录运行，Legacy 才已有成片上传/分享链路。“最终由 MinIO 管文件”不等于新版已完成入库上传。先登记关系和指纹，再逐项迁移；存储暂不可达与文件不存在须分开显示。

## 3. 当前物理目录（保持原样）

```text
本地项目/data/<scene_id>/
服务器 /data/zhaojy/burnroom-data/app-data/<scene_id>/
容器   /app/data/<scene_id>/
  mesh.obj / mesh.mtl / texture1.jpg / points.json
  <device>.jpg
  timeline.json / output.mp4 / render_status.json    # Legacy，非新版房间产物
  diagnostics/<kind>/<version>/                    # 户型、对齐、断面等私有依据
  rooms/<room_id>/<asset_version>/
    candidate.json
    asset/
      room.blend / room.glb / manifest.json / validation.json
      section_preview.blend / top.png / oblique.png / interior.png
    display_versions/<version>/                    # 历史展示派生（如有）
    style_round3/<run_id>/                         # 已验收样帧/配置/修复报告
  rooms/<room_id>/render_jobs/<render_job_id>/
    config_snapshot.json / effective_settings.json / room_timeline.json
    render_manifest.json / timing_report.json / video_receipt.json
    status.json / gpu_metrics.jsonl
    frames/ / keyframes/                            # 按stage实际生成
    fire_short.mp4 或 fire_final.mp4
    attempts/<attempt_id>/                          # 日志、renderer与本次计时
```

当前 F8-D 将 inspect/samples 的结果写入对应 style_roundN 版本目录；display_versions 是旧展示阶段的历史路径，不表示当前仍有独立写入入口。旧候选在本地的目录版本可与远端资产目录不同：只有文件 SHA 一致才可认定同一输入，不能根据名字相近认定。当前已归档的 candidate 是经过这种核对取得的同内容副本。

数据库持久化 `/data/zhaojy/burnroom-data/postgres/` 与 MinIO 持久化 `/data/zhaojy/burnroom-data/minio/` 各自独立。MinIO 数据目录由服务管理，业务代码不得直接操作其底层文件；必须走 SDK。真实环境变量不进入数据包或文档。

### 可变运行文件与不可变交付

任务运行时的 status、render_manifest、timing_report、GPU指标及日志会更新；它们是运行记录，不要求每次写入都新建业务任务。基础资产、冻结配置和已发布视频则按版本保护。

MinIO不可变key用于已定稿的交付或明确时间点的快照，不能持续覆盖同一个key以同步运行中的状态。成功任务定稿后发布视频/回执/必要报告；失败或续跑批次的报告快照放在任务前缀下的 `attempts/<attempt_id>/`，与根目录最新运行视图分开。快照记录采集时间和对应SHA；后续更正另建快照，不重写已发布证据。本轮不添加快照实现。

## 4. MinIO key：现状兼容与目标命名

| 类型 | 当前范围 | 对象命名 |
| --- | --- | --- |
| 旧场景输入 | burnroom-assets：`<scene_code>/<filename>` | 保留兼容，不把嵌套目录扁平下载到场景根 |
| 旧成片 | burnroom-outputs：`<scene_code>/output.mp4` | 保留；禁止写入 Room8 的 fire_final 来冒充旧产物 |
| 目录导入附件 | burnroom-assets：`<scene_code>/catalog/<sha256>/<filename>` | 保留已有代码规则 |
| 新版基础房间 | CLI本地实现，待远端 | 独立私有burnroom-room-assets：`scenes/<scene_id>/rooms/<room_id>/assets/<asset_version>/<filename>` |
| 新版任务交付 | CLI本地实现，待远端 | 独立私有burnroom-room-outputs：`scenes/<scene_id>/rooms/<room_id>/render_jobs/<render_job_id>/<filename>` |

版本 key 为不可变内容约定：相同 key/相同 SHA 可复用，相同 key/不同 SHA 必须拒绝并新建版本，不静默覆盖。不能仅凭 S3 ETag 当作 SHA256；上传器须明确验证内容指纹、字节数和媒体类型，完成后才登记。

新增对象的关系元数据必须绑定已核验的户型依据；数据库导入完成前用对齐报告/review SHA 引用，不填造一个 layout_versions.id。后续导入时解析到实际 layout fingerprint。当前旧下载器会跳过含子目录的 key，不会自动将版本资产拉入场景根；新版需专用下载/登记适配器。

数据库永久保存 bucket、object_key、sha256、size_bytes 和关联；临时预签名 URL 按需生成，不作为主键、不写入长期 manifest。浏览器可达端点与签名主机必须一致，不能换签名 URL 的主机/端口；预签名不提供网络穿透。

新版使用专用私有桶，是为隔离旧桶可能存在的公开读策略；不更改旧桶或Legacy命名。首批仅登记基础blend/GLB、三张检查图和正式MP4，不自动上传原始快照、完整运行报告。已有任何桶策略时保守拒绝，不静默修改管理员策略。

### 上传与登记顺序（首批CLI已实现，待远端）

1. 本地预览先确认场景/房间/版本、来源指纹与技术产物，保持 `upload_status=not_uploaded`、`registration_status=not_registered`，不连数据库/MinIO；apply先校验明确的数据库版本及人工证据。基础资产已生成不表示已允许公开外发。
2. 上传版本化对象；相同key已存在时先核对内容，不能直接覆盖。首次登记前回读对象并计算SHA，核对字节数和媒体类型，成功后才标记对象verified；仅metadata中的自报SHA或ETag不足以证明回读内容一致。
3. 在独立数据库事务中登记对象与关系，成功后才标记registered。MinIO与PostgreSQL没有共享事务：上传成功但事务失败可能留下未登记对象，应保留并单独重试登记，不重新渲染、不自动删除原文件或回退其他任务。

上传可用性、目录登记和人工审核是不同维度。登记CLI回执已有upload_status/registration_status，任务config摘要保留runtime_state/human_acceptance；未来API需分别表达，现有表没有独立的完整状态组合列，不把这些名称当成SQL字段。

原始config_snapshot、完整日志和私有模型默认不作为可公开分享附件。当前代码支持可选桶级公开策略，但本轮未查询远端实际桶策略；新增上传器必须先确认访问范围。若旧产物桶存在全桶匿名读取，不将原始运行报告直接上传到该公开范围；私有报告的隔离方式另行设计，不在本轮改变旧视频访问权限。

## 5. PostgreSQL：已有八表与缺口

| 现有表 | 关系用途 | 当前需注意的边界 |
| --- | --- | --- |
| scenes | scene_code 唯一、场景入口 | scenes.id 仅内部主键 |
| layout_versions | 输入/变换/review 指纹版本 | fingerprint 由整套输入与结论生成 |
| rooms | 户型版本下的 source_room_id、多边形、有效性 | Room11 为本场景异常记录，不能因此删除源记录 |
| points | 场景内 device、原始XYZ | 22 个原始点，不因 Room8 裁切删点 |
| point_room_memberships | 算法归属与人工修正 | 门口关联不等于允许传播；重导入不覆盖人工结论 |
| assets | kind、路径、SHA、字节数、bucket/key | 尚无独立 asset_version/layout_version 列；需后续显式设计关联 |
| render_jobs | 场景/房间/户型/起火点、config、状态摘要 | 尚无独立文件任务号列；不可把整数 id 当 render_job_id |
| render_job_assets | 输入/输出资产与任务的关系 | 并未自动从新版 job manifest 写入 |

迁移元数据表 schema_migrations 不计入上述八张业务表。后续 users、scene_memberships 是同一业务数据库内的新表，不需要为每个房间或用户另建数据库；本轮不实施权限体系。

现有 SQL 的任务状态只允许 unknown/running/done/failed；文件还含 created、preparing、rendering、encoding、awaiting_visual_review、interrupted。目标同步规则：活动阶段→running，技术验证通过且待审核→done，failed/interrupted→failed，缺失/无法核验→unknown。**这是待实现映射**，done 只表示技术完成，必须在 API 中另保留原始 runtime_state 与人工审核信息；现有表没有独立审核列，不冒称已能保存全部审核状态。

首批登记仅实现“已完成final且awaiting_visual_review→SQL done”这一分支，并在config保留原始状态与未记录人工审核；活动/失败同步和API表达仍未实现。

首批登记CLI使用render_jobs.config桥接file_job_id、asset_version、snapshot_signature、原运行状态及未记录人工验收状态，schema_version独立标记为registration_schema_version=1；通过场景advisory锁与Room8本地登记锁避免协作写入重复。输入/输出经render_job_assets关联；done仅表示技术完成。此方案不提供外部ID独立列的唯一约束，后续多机/其他写入方接入前需评审新迁移、唯一性及跨场景约束；不得修改已应用的001_rooms.sql。尚未远端执行登记。

现有points按场景/device唯一保存坐标，import_rooms.py:111–115会拒绝同场景既有点位的坐标变更。新layout_version只解决户型/归属版本，不能自动解决扫描点位空间变化；如以后重新扫描，须另行设计scene revision及兼容关系，不静默覆盖points。

2026-11-13真实导入版本1已核对：6条房间记录（5条有效，含无效Room11）、22个点位；22人工关联Room8内部，32为Room8门口，42户型外且不关联房间。Room8 API返回内部13点、门口1点，两类数量分开；相同输入再次导入复用版本1并保留review。Room8本次数据库主键为6，仅用于查询，不可写死。详细证据及备份见[数据库记录](database.md#本次实际验收)；独立房间模型/视频登记仍待完成。

## 6. Room8 V1 跨存储完整示例

| 位置 | 基础房间 | 对应视频 |
| --- | --- | --- |
| 本地 incoming | `rooms/Room8/20261102T025550Z-7f677509/asset/room.blend` | `rooms/Room8/render_jobs/20261105T040552Z_91f5fb7d/fire_final.mp4` |
| 服务器/容器 | 在上述场景数据根下使用同样相对路径 | 同左；任务快照绑定基础房间与 R3 指纹 |
| MinIO 目标 key | `scenes/KK-EEz16cmU14/rooms/Room8/assets/20261102T025550Z-7f677509/room.blend` | `scenes/KK-EEz16cmU14/rooms/Room8/render_jobs/20261105T040552Z_91f5fb7d/fire_final.mp4` |
| PostgreSQL 目标关系 | scenes/rooms → assets 的对应行，实际 ID 入库后才有 | render_jobs → render_job_assets(input/output) → 对应资产行 |
| Git | 基线源码、R3、[脱敏发布记录](RELEASES.md) | 只记录任务号、参数和指纹，不提交视频 |

本地 incoming 指基线备份内的 incoming，本次下载没有将正式资产复制进项目日常 data/。资产与视频 SHA 分别为：

```text
room.blend      3123e1373296c866602f683a22c80d80d4ac1507cf4a86243ee44a4852f3bce1
fire_final.mp4  c339c91d12709797b43989c680474286e5b2641a64de160d3fde7902267404dd
```

拟议登记描述示例（仅文档约定；不是现有 manifest 的替代，也未创建实际登记文件）：

```json
{
  "contract_version": "draft-1",
  "scene_id": "KK-EEz16cmU14",
  "room_id": "Room8",
  "asset_version": "20261102T025550Z-7f677509",
  "render_job_id": "20261105T040552Z_91f5fb7d",
  "layout_version_ref": {
    "database_id": null,
    "alignment_report_sha256": "95bdfd18aa233a718b6f21114fd84f3bd102dee68ea07561e46860c6c0114b8b",
    "review_sha256": "883de043a2a8106b8daac1299fe99a7f598ddfc200eeb4c91fbaffdb8c95bfdc"
  },
  "upload_status": "not_uploaded",
  "registration_status": "not_registered",
  "runtime_state": "awaiting_visual_review",
  "human_acceptance": "provisional_demo_with_known_limits",
  "objects": [
    {
      "kind": "room_blend",
      "source_relative_path": "rooms/Room8/20261102T025550Z-7f677509/asset/room.blend",
      "sha256": "3123e1373296c866602f683a22c80d80d4ac1507cf4a86243ee44a4852f3bce1",
      "size_bytes": 2262936,
      "bucket": null,
      "object_key": null
    },
    {
      "kind": "video_final",
      "source_relative_path": "rooms/Room8/render_jobs/20261105T040552Z_91f5fb7d/fire_final.mp4",
      "sha256": "c339c91d12709797b43989c680474286e5b2641a64de160d3fde7902267404dd",
      "size_bytes": 1062049,
      "bucket": null,
      "object_key": null
    }
  ]
}
```

所有文件描述条目须记录 kind、业务关联、source_relative_path、sha256、size_bytes；上传后才填实际 bucket/object_key。发布文件和运行缓存分别列出，不凭本示例自动创建上传记录或填充 SQL ID。

这里的source_relative_path以场景数据根为基准，实际位置可以是服务器场景根或归档incoming中的同场景根，由可信适配器映射；不将开发者Windows路径永久写入跨环境业务标识。表中MinIO key是计划位置，示例bucket/key为null，表示没有冒充远端上传验收。

## 7. 新版网页 API 的文件适配边界（待实现）

拟议房间查询 `/api/room-scenes/<scene_id>/rooms` 返回业务 room_id、可用资产版本、内部/边界点数量、可用预览与发布状态；避免与已有 catalog 的整数 ID 语义混用。

拟议 `POST /api/room-jobs` 只接收可信业务字段，例如 scene_id、room_id、asset_version、preset、camera_mode、受控 style preset 引用。后端查清单并检查版本，再构建当前引擎所需的真实 CLI/JSON；不允许客户端指定工作目录、Python路径、任意命令或未经审核的 direct-final 绕过参数。

拟议查询为 `GET /api/room-jobs/<render_job_id>?scene_id=<scene_id>&room_id=<room_id>`，按三元组定位；不凭一个UUID后缀全盘扫描或挑最新任务。如未来另建全局唯一索引，可在另一版接口中简化上下文。返回原始任务阶段、技术完成、人工审核、有效帧数、日志摘要与可用产物引用；仅凭 MP4 文件存在不能标记成功。视频通过后端可信路径或经登记对象按需签名交付，浏览器不能自行遍历服务器路径。这些路由尚未实现。

## 8. 一致性与恢复规则

源数据/核验→candidate→基础资产→任务快照→帧清单→视频回执形成单向指纹链。文件 SHA 按实际字节计算，不在 WinSCP 传输时做文本换行转换；规范化 JSON 指纹仅用于定义了 canonical 规则的配置契约，两者不能混用。

现有schema_version=1任务快照还包含asset/points/config/guards的绝对路径，check_resume要求新预检结果与整个快照一致。因此“同内容换了位置”不保证能续跑原任务；跨目录恢复可以只读核验/播放已有产物，如需重新生成则创建新任务并记录来源。不能手改旧快照路径、signature或帧指纹来绕过续跑检查。跨环境可移植的新版运行契约应另行版本化，不在本轮改写历史任务。

只读核验结论追加保存；不得为“修复通过”改旧 manifest 的 SHA 或人工结论。关系目录/对象存储可重试登记，但不能因登记失败重新启动 Blender。备份不反向覆盖当前工作目录；恢复到新目录，核对版本后显式切换。

Room8 V1 当前缺少本地原帧和四份 R3 原始参考附件，历史远端 Git checkout 号也未记录；已有关键文件归档不宣称完整灾难恢复。详细证据与范围见发布记录。

## 9. 本次工程审阅结论

2026-11-07：保留现有业务编号映射和版本key方向；补齐唯一性范围、路径约束、可变状态/不可变交付、两阶段上传登记及跨路径续跑边界。示例已列出真实文件大小和SHA，bucket/key维持null。

本规范可以指导下一步纯函数解耦；尚未具备直接实施数据库迁移、批量上传或改名既有资产的条件。后续登记功能须新增隔离测试，覆盖对象已存在但SHA不同、上传成功登记失败、状态/审批分离、同任务号跨房间歧义以及路径变化后拒绝续跑。测试与实际接入分别验收，不用文档状态代替运行结果。
