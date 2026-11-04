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
| PRD V6.0：分享、缓存；architecture 2.3 | app/main.py、app/s3_io.py | test_v6_share.py、test_catalog_deployment.py | 根目录下载与 catalog/history 隔离；远端对象访问仍需验收 |
| PRD 户型核验、architecture F5/F8 边界 | app/analyze_floorplan.py、app/probe_floorplan.py | test_analyze_floorplan.py、test_probe_floorplan.py | 不等于三维裁切或渲染验收 |
| PRD 2.1：数据库部署与持久化 | app/database.py、app/db/*.sql | test_room_database.py | 迁移幂等、应用账号授权和恢复后查询还需单独补测 |
| PRD 2.1、architecture 3.1：应用账号核验 | app/check_catalog.py | test_catalog_deployment.py | 离线连接替身测试；远端用实际应用账号执行 check_catalog 与导入 |
| PRD 2.1、architecture 2.3：部署保护 | .dockerignore、release/scripts/ | test_release_safety.py | 临时目录真实打包、模拟外部命令失败；不启动 Docker，不连接 SSH；远端备份/回退待实测 |

## 命令与执行边界

2026-11-03第三轮：新增`test_room_fire_round3.py`，对应PRD2.2/architecture3.2；6项核对火焰参数/火舌网格、烟柱几何/成长、BFS/机位/质量均不变；曝光/背景及薄层颜色小幅提升；离线执行lighting函数确认逐灯体积倍率和烟柱高度目标真正应用/记录；第三轮仍走分层火体/吸收烟柱分支；实际设置回读曝光；无效倍率/目标/版本拒绝。相关回归共74项通过。命令：`python -m unittest test.test_room_fire_round3 test.test_room_fire_round2 test.test_room_fire_config test.test_room_fire_style test.test_room_demo test.test_room_demo_plan -v`。全为离线替身及合成几何，不渲染/不写数据库；六张真实图片/耗时需按docs/room_style_round3.md远端验收。

2026-11-03第二轮：新增`test_room_fire_round2.py`，对应PRD2.2/architecture3.2；8项覆盖主/次火尺寸比例且风格/事件/质量不变、表面照明保持但体积照亮受控、卷曲烟柱闭合/不规则/窄底宽顶、独立成长/升高/消退及固定烟底、主体密度不耦合发光、深色非发光散射和额外吸收连线、无效参数拒绝、分轮独立目录和静帧门禁。复用原节点替身，无Blender/数据库/资产写入。命令：`python -m unittest test.test_room_fire_round2 test.test_room_fire_config test.test_room_fire_style test.test_room_demo test.test_room_demo_plan -v`。与房间资产/户型相关回归共68项离线通过；远端六张图片、API兼容和耗时仍按docs/room_style_round2.md验收，不宣称已出新图。

2026-11-03第一轮：`test_room_fire_config.py`追溯PRD2.2/architecture3.2，覆盖art/events/quality分组、已确认灯光、禁止改BFS排除策略、火弱烟留、固定种子和主/次火舌数量、闭合有向网格边；`test_room_fire_style.py`覆盖设置显式赋值/回读、缺失与截断拒绝、short在任何资产I/O前拒绝。原`test_room_demo.py`增加独立发光/密度与四层色/深灰非发光烟的节点替身断言，并验证只有静帧渲染调用。命令：`python -m unittest test.test_room_fire_config test.test_room_fire_style test.test_room_demo test.test_room_demo_plan -v`。不运行Blender/数据库，不写真实数据；Blender4.2 API、六张样帧实际色彩及耗时须远端按docs/room_style_round1.md确认。

`test_room_demo_plan.py`、`test_room_demo.py` 追溯 PRD 2.2 / architecture 3.2 的既有 Room8 展示修正与火灾预览。覆盖 UV 缝处位置连接、孤块默认保留/显式隐藏、内部子图禁止经外部桥接、多级渐变，以及离线节点替身验证橙红发光/动态噪声密度/非发光深色烟和派生输出隔离。命令：`python -m unittest test.test_room_demo_plan test.test_room_demo -v`。不启动 Blender，不将节点替身测试等同于 Blender API 或画面验收；真实三视图、火灾样帧/短片和耗时按 docs/room_display.md 在远端确认。

`test_prepare_room_asset.py` 对应 PRD 2.2、architecture 3.2：离线执行 F8-B 的辅助函数，验证源点位不变、内部与门口关联互斥、重载点位位置/归属核对、相机高度与火源参考高度分离、剖面副本 UV 插值、凹房间内部镜头候选以及 F8-A/B/C 头部标记。使用 AST 提取函数与合成对象替身，不导入 bpy；不能作为 Blender 运行、GLB 或图片视觉验收。命令：`python -m unittest test.test_prepare_room_asset -v`。

`test_room_candidate.py` 对应 PRD 2.2（2026-11-02 近似策略）、architecture 3.2：合成数据验证凹多边形裁切排除凹口、UV/Z 线性插值、竖直边界面保留/重复面面积、细小边、显式近似接受、指纹变更拒绝、版本隔离及原始文件不变。对 Blender 新脚本仅静态检查保存→重新加载→检查图的顺序，不代表 Blender 运行通过。运行 `python -m unittest test.test_room_candidate -v`。实际 Blender 重载、GLB 和三视图需远端按 docs/room_candidate.md 验收。

房间资产裁切前核验对应 PRD 2.2、architecture 3.2：`test_inspect_room_asset.py` 使用合成 OBJ/MTL/UV 验证坐标逆变换、竖直交点、候选高度、输入不变和通用房间参数。对 Blender 专用诊断仅作静态禁止裁切/渲染/覆盖保存检查；实际导入坐标和材质需在远端 Blender 验证，不能用静态测试代替。运行 `python -m unittest test.test_inspect_room_asset -v`。

`test_room_sections.py` 对应相同章节，覆盖平面/三角面求交、共面/不相交、凹房间区间、正反向边界法线、同高度连通与跳变、墙面搜索范围、邻房侵入及“候选间距不自动等于墙厚”。合成资产端到端生成 PNG/报告并校验源文件哈希，要求安装 requirements-diagnostics.txt；未安装时图片测试跳过，不能计作通过。运行 `python -m unittest test.test_room_sections -v`。不调用 bpy、Docker、远程服务或数据库。

本地 PowerShell、项目目录、已安装相应依赖的 Python：

```powershell
python -m unittest test.test_room_database test.test_room_api test.test_analyze_floorplan test.test_probe_floorplan test.test_v6_share test.test_f7 test.test_catalog_deployment test.test_release_safety -v
```

`ROOM_DB_INTEGRATION` 默认不启用。缺少本地依赖或 Python 版本与生产不一致时，要如实说明，不以替代环境代表生产通过。

仅在远端部署准备完成、人工确认后执行数据库测试：

```bash
docker compose exec -T -e ROOM_DB_INTEGRATION=1 app-server python3 -m unittest test.test_room_database -v
```

不要直接在生产数据上运行全目录自动发现：现有 `test_api.py` 会调用生成时序接口并写入真实 `timeline.json`。未完成隔离前应显式选择测试模块。当前打包脚本携带全部测试，但仍需按上述名单选择；Windows 打包子进程测试在 Linux 上会跳过。

## 每次交付记录

说明新增测试名称、对应需求、命令、通过/失败/跳过数量、未验证项及原因。涉及 app 行为修改但缺少对应新增测试时，不标记该功能为完成。本规范目前是开发约定，尚未添加自动 CI 强制检查。
