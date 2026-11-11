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

最近代码回归（fd3b372对应本地证据）303项：301通过、2项跳过；另9项F6/F7合成逻辑通过。跳过为未启用真实PostgreSQL、未安装可选Matplotlib，不算通过。测试环境Python3.13.3/Pydantic2.10.6不替代远端原依赖；生产requirements未改。本轮文档整理不重跑代码测试，只核对文档/文件/指纹。

常规回归使用合成数据、HTTP/DB/进程/Blender对象替身和临时PowerShell/tar；不运行真实Blender/GPU、Docker、SSH/SCP或生产服务。模拟日志出现fire_final.mp4不代表新成片。

每次功能/缺陷修改新增相应测试并标注PRD/Architecture、输入输出、环境、副作用和命令。功能测试保留语义断言；目录变更需覆盖实际导入、CLI、AST定位、完整包及失败保护，不能只改预期使测试通过。新增API/CLI/后台/前端动作按[日志契约](../docs/OBSERVABILITY.md)覆盖关联、耗时、失败和脱敏。

真实PostgreSQL集成须显式启用且使用隔离schema/事务；真实timeline测试会改源场景文件，不能在V1目录误跑。远端GPU/GLB/视频/浏览器视觉、应用账号权限、恢复和重复导入分别验收，不以离线替身代替。历史记录见[测试归档](../docs/archive/20261111_process/testing_history.md)。
