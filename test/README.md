# 测试规范与需求追溯

## 每次修改的要求

每次修改 `app/` 脚本以新增功能、改变行为或修复缺陷，都必须在 `test/` 新增至少一个对应测试用例；独立功能新建 `test_<功能名>.py`，已有功能可以在对应测试文件中新增用例。缺陷修复应增加能复现原问题的回归测试，不能只修改原断言让测试通过。

新增测试文件的说明或测试类说明须注明：

- 对应 `PRD_V1.1.md` 的章节、需求和验收结果。
- 对应 `architecture.md` 的模块、数据边界或架构约束。
- 被测的 app 文件、功能及输入输出。
- 测试级别：离线单元测试、API 测试、远端数据库集成测试、GPU 渲染验收。
- 执行位置、依赖、允许产生的副作用和运行命令。

示例追溯说明：`PRD 2.1 房间数据管理；architecture 3.1 PostgreSQL 房间目录；app/import_rooms.py；验证重复导入不覆盖人工结论。`

## 安全与隔离

- 离线测试使用合成数据、临时目录和替身连接，不访问远端，不修改真实场景文件。
- 不在测试中硬编码生产密码、appkey、签名 URL 或真实户型；敏感样本保留在忽略的私有目录。
- 数据库集成测试必须显式启用，使用隔离 schema/事务并清理；不得把跳过算作通过，也不得用管理员连接通过代替应用账号权限验证。
- Blender/GPU 测试只在用户指定的远端环境运行，先验证样帧，再完整出片；记录帧数、GPU、耗时、错误日志和人工画面检查结果。
- 测试数据库不可用时，还应验证原有后端/分享接口可用；上传路径变更应覆盖旧下载逻辑的兼容性。
- 迁移、账号授权、备份恢复和部署回退需分别验证，不能仅凭 SQL 语法解析或接口替身测试宣布验收通过。

## 本轮需求与现有测试

| 需求/架构 | 实现 | 测试文件 | 当前边界 |
|---|---|---|---|
| PRD 2.1、architecture 3.1：源数据核验与版本 | app/import_rooms.py | test_room_database.py | 离线校验已覆盖；真实数据库需远端执行 |
| PRD 2.1：房间/点位/文件查询 | app/room_api.py | test_room_api.py | HTTP 替身测试；不证明生产权限与文件可达 |
| PRD V6.0：分享、缓存；architecture 2.3 | app/main.py、app/s3_io.py | test_v6_share.py | 新目录上传与旧下载的兼容性还需补充回归 |
| PRD 户型核验、architecture F5/F8 边界 | app/analyze_floorplan.py、app/probe_floorplan.py | test_analyze_floorplan.py、test_probe_floorplan.py | 不等于三维裁切或渲染验收 |
| PRD 2.1：数据库部署与持久化 | app/database.py、app/db/*.sql | test_room_database.py | 迁移幂等、应用账号授权和恢复后查询还需单独补测 |

## 命令与执行边界

本地 PowerShell、项目目录、已安装相应依赖的 Python：

```powershell
python -m unittest test.test_room_database test.test_room_api test.test_analyze_floorplan test.test_probe_floorplan test.test_v6_share test.test_f7 -v
```

`ROOM_DB_INTEGRATION` 默认不启用。缺少本地依赖或 Python 版本与生产不一致时，要如实说明，不以替代环境代表生产通过。

仅在远端部署准备完成、人工确认后执行数据库测试：

```bash
docker compose exec -T -e ROOM_DB_INTEGRATION=1 app-server python3 -m unittest test.test_room_database -v
```

不要直接在生产数据上运行全目录自动发现：现有 `test_api.py` 会调用生成时序接口并写入真实 `timeline.json`。未完成隔离前应显式选择测试模块。当前打包脚本只携带数据库测试及包初始化文件，其他测试在远端运行前需确认文件已随包提供。

## 每次交付记录

说明新增测试名称、对应需求、命令、通过/失败/跳过数量、未验证项及原因。涉及 app 行为修改但缺少对应新增测试时，不标记该功能为完成。本规范目前是开发约定，尚未添加自动 CI 强制检查。
