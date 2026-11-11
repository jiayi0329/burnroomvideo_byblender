# 正式路径去重：2026-11-11

本次是用户确认后的兼容期结束：源码只保留新路径，不再保留app、release源码副本或test包。仅本地实现与离线回归；不部署、不连接数据库、不运行Blender、不合并main。根README完整文件说明与过程文档合并属于下一项任务。

| 内容 | 唯一正式位置 |
| --- | --- |
| FastAPI启动 | backend.api.main:app |
| 原F6/F7/F8-C | render_engine/legacy/，旧HTTP接口保留；worker子进程工作目录显式为项目根 |
| Room8裁切、样式、动画 | render_engine/各职责包；普通Python不导入Blender worker |
| 诊断与手工API | tools/diagnostics及tools/integration/probe_scene_api.py |
| R1/R2/R3 | configs/render/room_fire_round*.json；内容不变，R3仍默认 |
| 数据库SQL | backend/database/migrations/001_rooms.sql；内容、文件名及已应用迁移记录不变 |
| 发布脚本、生产/GPU模板 | deploy/；不再使用release/scripts旧命令 |
| 测试 | tests/{backend,engine,tools,deploy,legacy,integration}；公共定位/清单在tests根 |

本地PowerShell、项目根目录：

```powershell
python -B -m tests.run_regression
.\deploy\scripts\build.ps1
```

本机已有测试环境可使用`release/out/backend-test-env/Scripts/python.exe`代替python。安装包和私有备份仍写入被忽略的release/out，保留原产物，不移动、不删除；这不是Git中的重复源码。deploy.ps1会连接服务器，本轮不运行。

普通Python入口改用`python -m render_engine.jobs.run_room_animation`、`python -m render_engine.geometry.prepare_room_candidate`；后端/诊断CLI使用其正式包路径。完整安装包必需，不能上传单个兼容脚本；旧app CLI已经移除，不提供回退别名。

28份源码/预设指纹覆盖25份引擎Python（含Legacy隔离包）与3份公共预设，没有旧入口/配置副本。源码集合已变，旧40文件任务不能改签名续跑；复现Room8 V1须恢复原归档代码。数据库基线用固定SHA256及已应用迁移校验保护，不能因为移除SQL副本而编辑既有迁移；公共预设打包也有批准指纹保护。

原测试用例移动后更新导入与源码定位，保留算法/材质/UV/时序/编码/失败保护断言；旧路径兼容断言改为唯一正式位置检查。新增tests/deploy/test_canonical_layout.py验证去重、SQL/R3、依赖隔离、清单及旧任务拒绝。tests/TEST_HISTORY.md是旧测试说明的迁移记录，不作为当前命令入口。

数据、原模型、人工review、基础room.blend、历史视频、任务快照和数据库均不修改。远端当前仍可能运行旧版代码，本地去重不代表已部署；远端升级与实际运行验收另行安排。更完整的README、日志基础设施和真实数据库导入按后续任务实施。

## 本地核验结果

完整离线回归303项：301通过、2项跳过（真实PostgreSQL未启用、可选Matplotlib未安装），其中本次新增8项全部通过；补充F6/F7合成逻辑9项全部通过，不读取真实全景图或生成真实timeline。使用既有Python3.13/Pydantic2.10.6隔离环境，生产依赖不改；没有执行真实渲染、数据库、SSH或Docker。

对照迁移前备份：239个运行函数AST一致（后端start_render仅将cwd改为显式项目根）；R1/R2/R3、SQL、生产模板、历史归档和24份V1文件SHA保持不变。96份Python通过3.11语法检查；新旧包导入依赖扫描、当前文档链接、git diff检查、PowerShell语法/BOM及Shell LF检查通过。原295项相关测试继续运行；旧兼容断言按用户决定改成唯一正式路径检查，没有删除功能回归断言来回避失败。

逐文件备份及移动清单位于忽略目录`release/out/canonical-cleanup/20261111T030731Z_a5db8a55/`，含before.json、mapping.json、verification.json、final_regression.json和完整测试日志。Git尚未提交；用户审阅后提交，未合并main或创建标签。
