# Backend

当前入口为backend.api.main:app。API、数据适配、服务和CLI的逐文件用途见[根清单](../README.md#完整文件清单)，调用链见[Architecture](../docs/ARCHITECTURE.md)。没有app兼容源码。

- api/main保留Legacy场景下载、F6/F7/F8-C编排、状态与分享；worker在render_engine/legacy，cwd为安装根，不是新版Room8任务入口。
- api/room_api在/api/catalog下按数据库整数主键查询；PostgreSQL失败返回503，健康与旧分享不依赖数据库。
- adapters/postgres负责延迟连接和显式迁移；SQL唯一位置database/migrations。原001文件/已应用SHA不变，不随启动建表或导入。
- adapters/minio保留下载、上传和7天预签名；新版Room8产物未完整登记。
- cli/import_rooms默认预览，--apply才写库，--upload-assets另行明确；cli/check_catalog只读核验应用账号/目录。
- services/observability是已有Legacy日志/GPU能力；统一请求/操作/CLI关联尚待实现，遵守[日志契约](../docs/OBSERVABILITY.md)。

CLI帮助支持`python -m backend.cli.import_rooms --help`、`python -m backend.cli.check_catalog --help`、`python -m backend.adapters.postgres.database --help`。帮助不写库；数据库CLI不带--help会执行迁移，不能当作只读检查。真实导入按[数据库计划](../docs/database.md)安排。
