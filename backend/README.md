# 后端目录与兼容边界

> 2026-11-11当前状态：app兼容源码已删除，正式入口为backend.api.main:app；F6/F7/F8-C移入render_engine/legacy。SQL唯一位置为backend/database/migrations，按固定SHA及原schema_migrations记录校验，未改表结构或导入数据。以下第5批兼容表为历史过程；当前使用[正式路径](../docs/canonical_paths.md)。

2026-11-09第5批迁移。仅整理已有实现，不新增Room8任务API、文件fallback、用户权限或资产登记流程，不导入真实数据。

| 旧路径（继续保留） | 实际实现 | 职责 |
| --- | --- | --- |
| app/main.py | api/main.py | 既有FastAPI与Legacy场景编排 |
| app/room_api.py | api/room_api.py | 数据库目录只读查询及已上传资产签名 |
| app/database.py | adapters/postgres/database.py | 延迟连接、显式迁移/应用账号授权 |
| app/s3_io.py | adapters/minio/s3_io.py | 既有下载、上传、7天预签名及可选桶策略 |
| app/import_rooms.py | cli/import_rooms.py | 默认预览；显式--apply才写库，--upload-assets另行明确 |
| app/check_catalog.py | cli/check_catalog.py | 只读应用账号权限与目录核验 |
| app/observability.py | services/observability.py | Legacy状态、日志、GPU采样及超温处理 |

7份兼容模块与新模块是同一对象，旧函数名和测试替换继续有效。ASGI入口仍为`app.main:app`；Docker只追加backend重载监控目录，未改服务、端口或挂载。Legacy main仍使用app/F6、F7和旧F8-C，其worker路径及工作目录不变；它不能作为新版Room8任务入口。

三条CLI均保留原命令，并支持对应新包命令：

```text
python -m app.import_rooms --help
python -m backend.cli.import_rooms --help
python -m app.check_catalog --help
python -m backend.cli.check_catalog --help
python -m app.database --help
python -m backend.adapters.postgres.database --help
```

帮助命令不连接数据库；迁移本身仍须显式运行，不能当作启动前自动动作。本轮不执行上述迁移或真实导入。完整操作资料见[数据库说明](../docs/database.md)，其中写库步骤需另外授权后执行。

原始`001_rooms.sql`逐字节复制至`db/migrations/001_rooms.sql`，app/db副本继续保留。实际迁移读取新目录，仍用原文件名和SHA256对比schema_migrations记录；新旧副本缺失或不同会在连接前拒绝。打包同样检查，不能编辑已应用迁移后强行更新校验值。没有新增SQL语句、表或字段。

初始化包不连接服务。数据库连接仍延迟到请求或显式CLI调用；不可用时catalog返回503，健康检查和既有视频分享不依赖数据库。MinIO配置名、桶/key、7天签名及错误脱敏不变；新版Room8视频并未因此自动登记。

引擎不反向导入Backend，也不导入bpy到后端。第6批后import_rooms直接复用render_engine/geometry/floorplan_alignment的只读分析，不再导入诊断CLI；inspect诊断仍复用纯build_plan，不会自动连库。分析算法、SQL与导入事务不变。

发布包增加15份后端Python及1份原样SQL，保留app入口；不携带后端目录内的私有JSON、视频、env或额外SQL。必须使用完整包，不能单独覆盖app兼容文件。部署、数据库持久化和MinIO对象均未改动。
