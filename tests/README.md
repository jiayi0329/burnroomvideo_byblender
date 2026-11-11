# 分组离线回归

> 2026-11-11：原test用例实体已移入本目录四组，F6/F7位于legacy、真实timeline集成位于integration，定位辅助在tests根；test旧包及命令已移除。默认命令仍为python -B -m tests.run_regression，拒绝真实DB/timeline集成开关。旧测试过程说明在TEST_HISTORY.md，下面第7批“保留test实体”的描述是历史布局。当前见[正式路径](../docs/canonical_paths.md)。

本次新增`deploy/test_canonical_layout.py`，追溯PRD工程整理及Architecture进程/数据边界，8项检查覆盖唯一源码位置、SQL/R3、测试清单、依赖隔离、Legacy worker、28文件指纹及旧40文件任务拒绝续跑。最终回归303项：301通过、2项跳过；补充9项F6/F7纯逻辑通过。执行环境及未验证项见正式路径说明；模拟视频日志不是远端新成片。

第7批先迁移测试组织入口，复用`test/`中的已有用例与共享替身，不批量移动测试实体，不复制另一套测试类。旧`python -m unittest test.test_...`命令继续可用。新增收尾测试放在`tests/deploy/`；以后逐个功能迁移用例，不需要为目录整齐一次改完全部路径。

在本地PowerShell、完整项目目录、已有依赖的Python运行：

```powershell
python -B -m tests.run_regression --list
python -B -m tests.run_regression
python -B -m tests.run_regression --group engine
python -B -m tests.run_regression --group backend --group tools
```

本机可用隔离解释器为`release/out/backend-test-env/Scripts/python.exe`，将上面的python替换即可。Python3.13/Pydantic2.10.6的结果不能代替远端原依赖验证；不改生产requirements。

backend/engine/tools/deploy四组显式列出模块，不扫描整个仓库；重复分组不重复执行。`--list`不导入测试或业务代码。`--report release/out/自定唯一目录/regression.json`保存数量、跳过原因、Python版本与耗时；文件存在即拒绝覆盖，失败返回非零。不指定report则不写报告。

离线入口拒绝ROOM_DB_INTEGRATION=1或ROOM_TIMELINE_INTEGRATION=1，避免继承环境后误操作。`test/test_api.py`会写真实timeline，现须显式ROOM_TIMELINE_INTEGRATION=1，未纳入此回归；根API探测及依赖私有场景的F6/F7旧回归也不在默认模块清单。它们没有被删除或冒充离线通过。

本轮只用合成数据、进程/数据库/HTTP替身及临时目录PowerShell/tar，不调用真实SSH/SCP、Docker、Blender或服务。PostgreSQL集成和可选绘图的跳过单列，不算通过。不要用全仓库discover替代此清单；新增功能仍须按[测试约定](README.md)增加用例，并登记所属组。
