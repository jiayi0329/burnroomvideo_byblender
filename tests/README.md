# 测试入口与验收口径

测试实体只有tests一份，分backend/engine/tools/deploy；legacy包含原F6/F7的合成与私有场景回归，integration的真实timeline测试会写文件，须显式开关。公共源码定位和工具白名单在tests根。逐文件用途见[根清单](../README.md#完整文件清单)。

本地PowerShell、完整项目和已有依赖的Python：

```powershell
python -B -m tests.run_regression --list
python -B -m tests.run_regression
python -B -m tests.run_regression --group engine
python -B -m tests.run_regression --group backend --group tools
```

本机可用release/out/backend-test-env/Scripts/python.exe替代python。--list不导入测试；分组去重。--report写新JSON报告，已存在就拒绝；失败返回非零。使用显式清单，不以全仓库discover替代。默认入口拒绝ROOM_DB_INTEGRATION=1和ROOM_TIMELINE_INTEGRATION=1，不因继承环境而误操作。

2026-11-11操作日志实现后，全量离线回归329项：327通过、2项跳过；测试执行169.423秒，含加载的runner总耗时171.003秒。新增26项位于backend/test_operation_logging和engine/test_room_operation_logging，覆盖请求/CLI/任务关联、异常与取消、脱敏、线程/进程分片、轮转、响应后后台耗时、输出隔离和日志故障。报告为本地忽略产物release/out/operation-logging-final-offline-20261111.json。跳过为未启用真实PostgreSQL、未安装可选Matplotlib，不算通过。先前fd3b372对应303项及9项F6/F7合成逻辑仍保留为历史证据；本轮未重复运行私有场景。测试环境Python3.13.3/Pydantic2.10.6不替代远端原依赖，生产requirements未改。

常规回归使用合成数据、HTTP/DB/进程/Blender对象替身和临时PowerShell/tar；不运行真实Blender/GPU、Docker、SSH/SCP或生产服务。模拟日志出现fire_final.mp4不代表新成片。

2026-11-13首批Room8产物登记完成后，最终全量离线回归359项：357通过、2跳过，unittest执行119.768秒。新增30项位于backend/test_room_registration，覆盖只读计划、原R3与签名、数据库证据绑定、边界点排除、专用桶策略、完整回读SHA、拒绝覆盖、事务/幂等/失败重试、锁/中断、日志脱敏及跨平台不可变字节。报告：release/out/room-registration-release-offline-20261113.json。另在临时目录中用真实V1归档副本只读构造6份登记清单通过，没有访问数据库/MinIO；不算远端发布或新增视频解码验收。

本次回归发现分支checkout会改变原SQL和R1的换行，已恢复为Git中原批准字节并设置.gitattributes；R2/R3保留各自原批准CRLF字节。既有SQL/预设哈希常量未改，不能通过更新校验值掩盖输入漂移。

每次功能/缺陷修改新增相应测试并标注PRD/Architecture、输入输出、环境、副作用和命令。功能测试保留语义断言；目录变更需覆盖实际导入、CLI、AST定位、完整包及失败保护，不能只改预期使测试通过。新增API/CLI/后台/前端动作按[日志契约](../docs/OBSERVABILITY.md)覆盖关联、耗时、失败和脱敏。

真实PostgreSQL集成须显式启用且使用隔离schema/事务；真实timeline测试会改源场景文件，不能在V1目录误跑。远端GPU/GLB/视频/浏览器视觉、应用账号权限、恢复和重复导入分别验收，不以离线替身代替。历史记录见[测试归档](../docs/archive/20261111_process/testing_history.md)。
