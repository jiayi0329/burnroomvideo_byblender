# 场景、房间、资产与任务的一致性规范

更新：2026-11-07。区分“当前实现”与“目标约定”；本文不执行迁移、上传、导入或重命名。职责见 [ARCHITECTURE](ARCHITECTURE.md)，版本示例见 [RELEASES](RELEASES.md)。

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

现有 CLI/JSON 仍使用 scene_code/room_id，现有 catalog API 路径仍接收整数 room_id。后续适配器显式转换，不能全局替换字段，也不能让浏览器把 `Room8` 传给已有整数路由。

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

## 4. MinIO key：现状兼容与目标命名

| 类型 | 当前实现 | 后续版本化约定（未实现上传器） |
| --- | --- | --- |
| 旧场景输入 | burnroom-assets：`<scene_code>/<filename>` | 保留兼容，不把嵌套目录扁平下载到场景根 |
| 旧成片 | burnroom-outputs：`<scene_code>/output.mp4` | 保留；禁止写入 Room8 的 fire_final 来冒充旧产物 |
| 目录导入附件 | burnroom-assets：`<scene_code>/catalog/<sha256>/<filename>` | 保留已有代码规则 |
| 新版基础房间 | 尚未完整登记 | burnroom-assets：`scenes/<scene_id>/rooms/<room_id>/assets/<asset_version>/<filename>` |
| 新版任务交付 | 尚未完整登记 | burnroom-outputs：`scenes/<scene_id>/rooms/<room_id>/render_jobs/<render_job_id>/<filename>` |

版本 key 为不可变内容约定：相同 key/相同 SHA 可复用，相同 key/不同 SHA 必须拒绝并新建版本，不静默覆盖。不能仅凭 S3 ETag 当作 SHA256；上传器须明确验证内容指纹、字节数和媒体类型，完成后才登记。

新增对象的关系元数据必须绑定已核验的户型依据；数据库导入完成前用对齐报告/review SHA 引用，不填造一个 layout_versions.id。后续导入时解析到实际 layout fingerprint。当前旧下载器会跳过含子目录的 key，不会自动将版本资产拉入场景根；新版需专用下载/登记适配器。

数据库永久保存 bucket、object_key、sha256、size_bytes 和关联；临时预签名 URL 按需生成，不作为主键、不写入长期 manifest。浏览器可达端点与签名主机必须一致，不能换签名 URL 的主机/端口；预签名不提供网络穿透。

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

后续增加任务外部标识、资产版本索引/关联及审核元数据时，新增迁移文件，评审唯一性和跨场景约束；不得修改已应用的 001_rooms.sql。可以先设计登记清单，不在本轮写库。

真实导入验收目标：6 条房间记录（含无效 Room11）、22 个点位；22 属 Room8，32 为门口关联，42 在户型外。Room8 13 个内部传播点、另有 1 个边界锚点，两类数量分开。当前仍未完成真实导入，以上是预期，不是查询实测。

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
  "registration_status": "not_registered",
  "runtime_state": "awaiting_visual_review",
  "human_acceptance": "provisional_demo_with_known_limits"
}
```

所有文件描述条目须记录 kind、业务关联、source_relative_path、sha256、size_bytes；上传后才填实际 bucket/object_key。发布文件和运行缓存分别列出，不凭本示例自动创建上传记录或填充 SQL ID。

## 7. 新版网页 API 的文件适配边界（待实现）

拟议房间查询 `/api/room-scenes/<scene_id>/rooms` 返回业务 room_id、可用资产版本、内部/边界点数量、可用预览与发布状态；避免与已有 catalog 的整数 ID 语义混用。

拟议 `POST /api/room-jobs` 只接收可信业务字段，例如 scene_id、room_id、asset_version、preset、camera_mode、受控 style preset 引用。后端查清单并检查版本，再构建当前引擎所需的真实 CLI/JSON；不允许客户端指定工作目录、Python路径、任意命令或未经审核的 direct-final 绕过参数。

`GET /api/room-jobs/<render_job_id>` 返回原始任务阶段、技术完成、人工审核、有效帧数、日志摘要与可用产物引用；仅凭 MP4 文件存在不能标记成功。视频通过后端可信路径或经登记对象按需签名交付，浏览器不能自行遍历服务器路径。这些路由尚未实现。

## 8. 一致性与恢复规则

源数据/核验→candidate→基础资产→任务快照→帧清单→视频回执形成单向指纹链。文件 SHA 按实际字节计算，不在 WinSCP 传输时做文本换行转换；规范化 JSON 指纹仅用于定义了 canonical 规则的配置契约，两者不能混用。

只读核验结论追加保存；不得为“修复通过”改旧 manifest 的 SHA 或人工结论。关系目录/对象存储可重试登记，但不能因登记失败重新启动 Blender。备份不反向覆盖当前工作目录；恢复到新目录，核对版本后显式切换。

Room8 V1 当前缺少本地原帧和四份 R3 原始参考附件，历史远端 Git checkout 号也未记录；已有关键文件归档不宣称完整灾难恢复。详细证据与范围见发布记录。
