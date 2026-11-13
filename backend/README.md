# Backend

当前入口为backend.api.main:app。API、数据适配、服务和CLI的逐文件用途见[根清单](../README.md#完整文件清单)，调用链见[Architecture](../docs/ARCHITECTURE.md)。没有app兼容源码。

- api/main保留Legacy场景下载、F6/F7/F8-C编排、状态与分享；worker在render_engine/legacy，cwd为安装根，不是新版Room8任务入口。
- api/room_api在/api/catalog下按数据库整数主键查询；PostgreSQL失败返回503，健康与旧分享不依赖数据库。
- adapters/postgres负责延迟连接和显式迁移；SQL唯一位置database/migrations。原001文件/已应用SHA不变，不随启动建表或导入。
- adapters/minio保留下载、上传和7天预签名；room_objects的独立私有桶及回读SHA已完成首批远端登记验收，视频签名Range返回206。
- cli/import_rooms默认预览，--apply才写库，--upload-assets另行明确；cli/check_catalog只读核验应用账号/目录。
- cli/register_room_assets默认只预览已完成Room8的6份交付；显式--apply才依次校验数据库绑定、上传核对、事务登记。services/room_registration构造只读计划，adapters/postgres/room_asset_repository复用八表关联，原SQL不变。
- api/room_jobs新增受控Room8/R3任务接口，services/room_job_service分配独立任务并交给cli/run_room_job，再调用引擎安全启动器。仅本地实现/离线测试，尚未远端部署；网页尚未实现。
- services/observability保留Legacy日志/GPU能力；services/request_logging和引擎公共operation_logging已接入请求、主要CLI及Room8追踪，cli/log_timeline生成只读时间线；HTTP/单帧任务已远端验收，登记功能已验收但本次未单独提取完整trace，前端待实施，遵守[日志契约](../docs/OBSERVABILITY.md)。

CLI帮助支持`python -m backend.cli.import_rooms --help`、`python -m backend.cli.check_catalog --help`、`python -m backend.adapters.postgres.database --help`。帮助不写库；数据库CLI不带--help会执行迁移，不能当作只读检查。真实导入按[数据库计划](../docs/database.md)安排。

## Room8新版任务API（本地实现，远端待验收）

| 请求 | 用途 |
| --- | --- |
| GET /api/room-jobs/options | 允许的R3风格、质量、机位和服务端提交开关 |
| GET /api/room-jobs/sources | 数据库中已核验、已登记Room8基础blend的场景/资产版本/layout编号；最多100项，截断有标记 |
| POST /api/room-jobs | 明确确认后分配独立任务，返回202和文件job_id；不等待渲染完成 |
| GET /api/room-jobs?scene_code=SCENE | 指定场景Room8历史，支持limit（1–100）/offset |
| GET /api/room-jobs/JOB?scene_code=SCENE | 文件状态、已完成帧、技术完成、可用视频和本次尝试总耗时 |
| GET或HEAD /api/room-jobs/JOB/video?scene_code=SCENE | 校验原回执/配置/文件SHA后播放本地MP4，支持单Range/206/416及If-Range |

API使用业务room_id=Room8和文件job_id；catalog仍使用数据库整数主键。POST必须提供Idempotency-Key头（8–96个字母数字/下划线/短横线）；同键同请求返回原任务，不重新启动，包括失败任务。同键改参数返回409；重新尝试需新键，不自动清空旧任务。提交示例仅说明契约，本轮不执行：

```json
{
  "scene_code": "KK-EEz16cmU14",
  "room_id": "Room8",
  "asset_version": "20261102T025550Z-7f677509",
  "layout_version_id": 1,
  "style_preset": "r3",
  "preset": "test",
  "camera_mode": "overview",
  "confirm_render": true
}
```

只接受以上字段及可选approval_job_id，不接受路径、任意JSON配置、脚本、命令、点位或direct_final参数。test固定4秒/960×540/12fps/48帧，允许overview/closeup；final固定24秒/1280×720/24fps/576帧且必须overview。两者沿用13点BFS，32/42排除；火烟/灯光和基础几何不变。参考机位从该资产最早已登记成片的快照确定，不按mtime另选参考。

默认ROOM_JOB_RENDER_ENABLED=0，只开放查询；创建返回503。运行方准备接受提交后，才在现有prod.env追加ROOM_JOB_RENDER_ENABLED=1并通过已验证的GPU/acceptance覆盖更新应用容器，不覆盖其余凭证。本轮不执行部署。final必须提供已有审核短片的approval_job_id，交由原verify_approval完整核验；或由运维显式设置ROOM_JOB_DIRECT_FINAL_ENABLED=1允许受控总览正式档。客户端不能开启该策略，短片完成不自动启动正式档。这两个开关不是身份认证，接口仅供受控内网，公网权限另行实现。

提交需数据库可用且核验layout/review/成员关系、登记SHA和本地输入一致；读取已有任务/视频不访问数据库或MinIO。复用原GPU锁和进程冲突检查；发现其他新版活动状态或Legacy运行状态返回409，不排队。不能原子阻止旧API或其他用户非协作进程，验收期间须避免这些入口并发提交。

先用安全启动器create_job生成原格式快照/created状态，再事务登记running摘要；子进程收到父进程释放锁后的管道握手才执行。独立Python启动器使用resume复用这个新任务号，再由原启动器完成GPU/预检、Blender、编码和验证。API不直接启动Blender，不接管原状态机。

每个新任务额外保存api_request.json（来源/请求指纹/trace/数据库ID）、api_launch.json（PID）、api_launcher.log；失败可有api_failure.json。DATA_ROOT/.room_job_requests只保存幂等键哈希到任务的索引，不含另一个运行状态。原config_snapshot/status/manifest/timing/frames/attempts/video_receipt仍由引擎管理。进程退出后尽力同步数据库摘要；数据库失败只记录summary_sync错误，不丢弃成片、不重渲染。强制杀进程留下的created状态需人工核查，无自动抢占/清理或HTTP取消、续跑接口；已有CLI续跑规则不变。

awaiting_visual_review表示技术完成待人工审阅，不是人工批准。进度只计主镜头视频帧，后期额外检查图不增加视频帧数；total_seconds来自本次尝试的timing_report，不是多个attempt累计。video_url为后端相对路径，不暴露磁盘路径或完整签名URL。新任务不会自动上传MinIO，完成后仍需显式登记CLI。

## 后续远端验收步骤

本轮已完成代码，以下命令供下一轮部署后执行；当前旧镜像不会自动出现新路由。

1. 本地PowerShell、项目目录：运行离线回归；通过后使用现有deploy/scripts/build.ps1生成新包。部署仍按保留当前GPU/acceptance覆盖及备份的既有流程单独进行，不直接重启旧latest镜像。
2. 远程SSH：进入`~/burnroom-prod/burnroom-deploy-package`；先只读检查以下接口，预期options的render_enabled=false、sources含已登记版本，V1状态技术完成且视频可用。

```bash
curl -fsS http://127.0.0.1:8000/api/room-jobs/options
curl -fsS http://127.0.0.1:8000/api/room-jobs/sources
curl -fsS 'http://127.0.0.1:8000/api/room-jobs/20261105T040552Z_91f5fb7d?scene_code=KK-EEz16cmU14'
curl -fsS --range 0-0 -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8000/api/room-jobs/20261105T040552Z_91f5fb7d/video?scene_code=KK-EEz16cmU14'
```

最后一条预期206，不启动任务。3. 确认可查询后再显式启用提交并验收一次test请求、同键重试和trace；不自动执行final。4. WinSCP仅下载新任务状态/回执/日志和测试视频供审核，不改代码、基础资产、review或历史任务。
