# 发布实现与兼容入口

2026-11-10第7批。正式实现位于`deploy/scripts/{build.ps1,deploy.ps1,prepare_deploy.sh}`；生产/GPU模板及无密钥示例位于本目录。根Dockerfile和开发docker-compose.yml仍为有效入口，不移动、不改部署拓扑。

旧的`release/scripts/build.ps1`和`deploy.ps1`只转调新实现，原命令继续可用；输出仍在被Git忽略的`release/out/`。`release/`下三个模板及prepare_deploy.sh保留兼容副本，打包比较字节SHA，不一致或缺失即停止。修改模板/保护脚本时须同步副本；真实prod.env仍仅存在于服务器，不用本地模板覆盖。

| 位置 | 操作与边界 |
| --- | --- |
| 本地PowerShell | 离线回归：`python -B -m tests.run_regression`；打包：`.\release\scripts\build.ps1`或`.\deploy\scripts\build.ps1` |
| 本地PowerShell，另行确认后 | `.\release\scripts\deploy.ps1`或`.\deploy\scripts\deploy.ps1`会连接SSH/SCP、备份并解压；本轮不执行 |
| WinSCP | 以后需要时手工传输安装包/下载产物，不编辑远端源码，不覆盖数据盘 |
| 远程SSH，另行确认后 | 进入既有Compose目录；独立安装包帮助检查按[引擎说明](../docs/room_engine_migration.md)；构建/重建/数据库导入不随本次迁移自动执行 |

prepare_deploy在任何备份/解压前只读核对旧render_status和房间render_jobs状态；created/preparing/rendering/encoding会阻断，损坏JSON也会失败。历史状态过期时需人工核对，不自动删除状态或强行放行。该检查不是原子调度锁；维护期间仍须暂停提交新任务，避免检查后又启动渲染。

打包保留Backend、引擎、诊断和原SQL/R3校验，新增tests入口必需文件检查；test/tests只收Python和README，不带PNG/JSON/模型/缓存。生产包不是完整开发仓库，不携带本地发布工具及真实数据；发布回归应在完整源码检出中执行，而不是声称所有本地PowerShell测试都能在Linux运行镜像里执行。

本轮没有运行Docker、部署、数据库或Blender。Windows离线验证不替代远端原Python/依赖、NVIDIA库和实际GPU验收；Room8 V1及旧任务不因目录整理重签续跑。下一步合并审阅见[收尾说明](../docs/migration_closeout.md)。
