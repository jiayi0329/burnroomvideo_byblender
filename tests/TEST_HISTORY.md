# 测试规范与需求追溯

> 本文保留前七批历史测试记录。2026-11-11原test实体已归入tests，旧命令/兼容约定不再有效；当前运行入口见[README](README.md)，本轮结果见[正式路径说明](../docs/canonical_paths.md)。

## 2026-11-10 第7批：分组入口与发布收尾

统一入口为`python -B -m tests.run_regression`，四组由tests/{backend,engine,tools,deploy}明确注册，原test用例实体与模块命令继续保留。`--list`只列模块，`--group`可重复选择但不重复执行；`--report`仅新建报告，不覆盖旧报告。新增`tests/deploy/test_migration_cleanup.py`，追溯[PRD工程要求](../docs/PRD.md)、[架构2.4](../docs/ARCHITECTURE.md)和[第7批收尾](../docs/migration_closeout.md)。覆盖离线清单/真实集成环境拒绝、报告失败统计与防覆盖、跨工作目录、模板与shell镜像、旧/新发布命令、临时安装包/私有测试产物排除、必需文件缺失拒绝及Legacy/Room任务活动状态部署保护。

旧`test_api.py`会写真实timeline，现须ROOM_TIMELINE_INTEGRATION=1，仍不进入离线清单。PostgreSQL集成仍须单独授权；离线入口拒绝继承的ROOM_DB_INTEGRATION=1和ROOM_TIMELINE_INTEGRATION=1，不静默运行真实集成。旧F6/F7私有场景回归未纳入此清单，保留原代码，不冒充通过。

本地PowerShell完整项目中使用`release/out/backend-test-env/Scripts/python.exe -B -m tests.run_regression`。生产Python/依赖不变，真实远端、Docker、数据库和GPU未运行。发布测试仅在临时合成目录执行PowerShell/tar，SSH/SCP均为替身；模拟视频日志不是新成片。详细命令见[tests/README](../tests/README.md)。

最终相关回归295项：293通过、2项跳过（未启用真实PostgreSQL、未安装可选Matplotlib）；本批新增16项全部通过。收紧Docker测试目录白名单后另复核3项部署契约，全部通过。40份引擎源码/预设、91份受保护源码/模板/历史文档及24份V1备份SHA不变，原timeline测试方法AST不变，仅增加显式开关。4份新旧PowerShell脚本语法、BOM及远端shell LF检查通过。完整报告位于忽略目录`release/out/cleanup-migration/20261110T114905Z_1e6672b7/regression_final.json`，另有`verification.json`；测试环境仍为Python3.13/Pydantic2.10.6，不替代远端原环境验收。

## 2026-11-10 第6批：诊断与手工集成工具迁移

新增`test_tools_migration.py`（16项），对应[PRD工程要求](../docs/PRD.md)、[架构工具边界](../docs/ARCHITECTURE.md)及[目录规范第6批](../docs/PROJECT_ORGANIZATION.md)。验证4份新旧模块同一性、公共函数导出及旧CLI替换兼容、12条普通CLI帮助路径、Blender帮助替身、导入无网络/连库/写入、共享核心只读且不反向依赖Backend/tools、合成对齐/高度结果与输入保护、40文件指纹变更拒绝、手工API显式开关/凭证缺失/假响应脱敏，以及完整临时安装包和缺少必需工具/核心时阻断。旧包装测试更新实际文件清单，保留原断言。

重点命令：`release/out/backend-test-env/Scripts/python.exe -B -m unittest test.test_tools_migration -v`。16项全部通过。包含前五批、诊断、API、资产、静帧、动画、GPU守卫和发布保护的完整相关回归279项：277通过、2项跳过（真实PostgreSQL集成显式禁用、可选Matplotlib缺少）。使用前述Python3.13隔离环境，生产依赖不改，仍需远端原环境复验。

实际网络全部使用假响应；未运行Blender/GPU/真实诊断、数据库、Docker或部署。模拟进程的出片日志不代表新视频。原算法函数AST与备份核对，原火烟/传播/裁切与R3配置、24份V1备份SHA保持不变。新增分析核心导致源码清单从39扩为40，测试确认旧签名任务拒绝续跑。手工工具不自动执行，不得将test_api或真实服务探测纳入无授权的全仓库自动发现。

## 2026-11-09 第5批：Backend目录迁移

新增`test_backend_migration.py`（18项），对应[PRD工程要求](../docs/PRD.md)、[架构2.1](../docs/ARCHITECTURE.md)及[目录规范第5批](../docs/PROJECT_ORGANIZATION.md)。验证7份新旧模块同一性/替换兼容、ASGI路由与启动无连库/迁移、12种CLI帮助路径、无bpy依赖、SQL原样复制/缺失及分叉拒绝、已应用校验与应用账号参数、错误脱敏、数据库失效时健康/旧分享可用、Legacy worker和工作目录，以及完整安装包/解压导入、缺文件阻断和重载目录。

本地使用忽略目录下的Python3.13.3隔离环境`release/out/backend-test-env`。FastAPI0.103.1、HTTPX0.27.2、MinIO7.2.13、psycopg3.2.3等与生产固定版本相同；Pydantic使用支持本地Python的2.10.6，生产requirements.txt中的2.3.0不改。因此本地结果不能代替远端Python3.11/原依赖复验。

重点命令：`release/out/backend-test-env/Scripts/python.exe -B -m unittest test.test_backend_migration test.test_room_api test.test_v6_share test.test_catalog_deployment test.test_room_database.ImportValidation -v`。50项全部通过。包含前四批的完整相关回归251项：249通过，2项跳过（真实PostgreSQL集成显式禁用、可选Matplotlib未安装）。18项新增测试全部通过；HTTP使用进程内TestClient，签名使用离线真实SDK，数据库操作使用连接替身，打包只在临时合成目录进行。

没有启动服务器、Docker或Blender，没有连接真实数据库/MinIO，也未执行部署。43个原函数仅有预期导入/寻址适配；引擎39文件SHA及24份V1备份SHA不变，SQL新旧副本字节一致。数据库集成需另行显式授权；不得运行会改写真实timeline的test_api自动发现。

## 2026-11-09 第4批：引擎/配置目录落位

新增`test_engine_migration.py`（15项）及AST源码定位辅助`engine_paths.py`，对应[PRD工程要求](../docs/PRD.md)、[架构2.2–2.3](../docs/ARCHITECTURE.md)和[目录规范第4批](../docs/PROJECT_ORGANIZATION.md)。检查13份兼容模块与实际实现同一性、旧接口替换、普通Python/Blender帮助替身、跨工作目录寻址、R3及新旧配置副本、引擎不导入Backend/tools、39文件指纹、旧app根参数兼容、源码变动/缺失及旧任务拒绝、worker/锁/输出路径，以及真实临时安装包、解压后导入、私有文件排除和打包失败保护。

命令：`python -B -m unittest test.test_engine_migration test.test_diagnostics_migration test.test_release_safety -v`。原资产/火烟/相机/时序测试改读render_engine实际源码，保留原回归断言；原函数导入继续走app兼容路径。发布测试使用临时合成代码，不在真实部署目录执行脚本。

最终相关回归205项：204通过、1项因缺少可选Matplotlib跳过；15项新增迁移测试全部通过。94个未涉及寻址/源码登记改动的原函数AST一致，R1/R2/R3预设字节不变，24份V1备份SHA一致。未运行Blender、GPU、Docker、SSH、数据库或真实视频；模拟出片日志不能当作新成片。当前是本地迁移完成，远端包安装和渲染尚未复验。旧归档版本的源码清单/运行说明保留历史含义，当前以[完整包说明](../docs/room_engine_migration.md)为准。

## 2026-11-09 第3批：Blender公共辅助

新增`test_blender_room_helpers.py`，对应[PRD当前MVP](../docs/PRD.md)、[架构2.2–2.3](../docs/ARCHITECTURE.md)与[目录规范第3批](../docs/PROJECT_ORGANIZATION.md)。12项离线测试验证实际helper的逐角UV/材质/原始Z、世界坐标、展示截断、凹房间机位、最近射线命中、旧接口同一性、业务导入隔离、改名脚本同目录加载，以及静帧/动画源码指纹、缺失/变动拒绝与旧任务快照不变。B资产及相机原AST测试改为读取实际公共函数，原断言保留；安装包测试增加helper包含检查。

命令：`python -B -m unittest test.test_blender_room_helpers test.test_prepare_room_asset test.test_room_animation_camera test.test_room_animation test.test_release_safety -v`。仅使用合成Blender对象、临时资产和模拟进程；打包在临时合成目录执行PowerShell/tar。不运行Blender、GPU、Docker、真实SSH或数据库。新helper函数与迁移前AST对照一致，R3/样式/传播/裁切实现及24份V1资产备份SHA未改；普通后端不得导入此bpy模块。远端Blender导入与画面尚未复测。

本批相关回归共190项：189通过，1项因缺少可选Matplotlib跳过；其中12项新增公共辅助测试全部通过。覆盖前两批、资产、静帧、R1/R2/R3、动画/相机/final/GPU守卫及临时安装包；模拟日志中的出片信息不代表实际重新渲染。

## 2026-11-09 断面诊断工具迁移

新增 `test_diagnostics_migration.py`，对应 [目录规范](../docs/PROJECT_ORGANIZATION.md) 的工具组迁移和 [架构](../docs/ARCHITECTURE.md) 的诊断/运行边界，兼容原PRD2.2、architecture3.2。12项离线测试覆盖新旧模块同一性、旧函数替换兼容、两条CLI帮助/缺参、延迟绘图依赖、候选导入隔离、HTML索引、诊断成功/失败保留，以及临时安装包内容与解压后导入、工具缺失时打包中止、镜像上下文白名单与BOM。

命令：`python -B -m unittest test.test_diagnostics_migration test.test_release_safety -v`。仅在临时合成目录执行PowerShell/tar及普通Python；绘图流程使用显式替身，不代表实际PNG出图。原有Matplotlib图片测试继续保留，缺依赖时记录跳过。没有运行Docker、真实SSH、数据库或Blender。

本次相关回归共178项：177通过，1项因缺少Matplotlib跳过。12项新增迁移测试与5项发布安全测试均通过；三个迁移文件除新导入路径外与旧实现文本一致，八份冻结运行源码及R3未改变。服务器部署和真实PNG/GPU验收没有在本轮执行。

## 2026-11-07 公共读取与输入校验解耦

新增 `test_room_source_io.py`、`test_room_source_inputs.py`，追溯当前 [架构的几何/文件边界](../docs/ARCHITECTURE.md) 与 [目录规范第1批](../docs/PROJECT_ORGANIZATION.md)，兼容原 PRD 2.2 / architecture 3.2。22项离线单元测试覆盖数值/索引、原始Z/逐角UV/材质、XY逆变换、路径越界、读取不改源文件、字节SHA、人工review/导入证据/材质指纹拒绝，以及 inspect/diagnose旧接口和候选独立导入。只用临时合成资产，不运行数据库、网络或Blender。

本地 PowerShell：`python -B -m unittest test.test_room_source_io test.test_room_source_inputs -v`。断面PNG测试仍需可选Matplotlib；缺少时如实记录跳过。F8八份冻结源码保持原样，动画回归使用替身，不代表新的GPU或视觉验收。

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

2026-11-04 相机回归修复：新增test_room_animation_camera.py（11项），追溯PRD2.3/architecture3.3。用真实F8-D camera函数及合成Blender对象复现同一对象被近景覆写，验证F8-E独立object/data/target、切换类型、错误模式阻断、总览投影仅扩尺度、camera_check只出43帧号/3.5秒一张、近景明确选项且不串用总览帧、编码前实际类型检查、原R3样帧/同资产SHA绑定、旧耗时只读提取、report-job无渲染路径、一帧流程无编码/短片审批。原test_room_animation.py仅补充合成帧的实际相机信息供新编码守卫验证。相关回归共109项通过；没有运行本地Blender/远端新出图。真实对比图/包围覆盖/镜头透视仍须docs/room_animation_camera_fix.md所述远端单帧与人工验收，之后才重跑短片。

2026-11-04 A阶段：新增`test_room_animation.py`，追溯PRD2.3/architecture3.3，覆盖三个新增动画文件及EffectFlow稳定节点名。24项临时资产/进程/编码/Blender/Linux锁替身测试，验证48帧与9额外检查渲染、24秒288/576帧生命周期、冻结配置/指纹、13点排除策略、目录隔离、可复用帧与损坏拒绝、失败保留、H.264/ffprobe契约、逐帧统计与推算标签、具名人工审核/质量preset与实际证据绑定、无审批不创建正式目录、任务锁/已有GPU进程检查、温度终止、任意顺序跳帧一致、可选真实渲染器信息与软件渲染识别、启动器成功止于审核及失败报告。命令：`python -m unittest test.test_room_animation -v`；加原静帧/资产/户型回归共98项通过。本地没有运行Blender/ffmpeg/Linux锁实机，不访问数据库或远程数据；GPU、真实视频连续性/耗时及正式出片门禁需按docs/room_animation.md在远端验收。模拟进程返回的秒数不是远端性能数据。

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

2026-11-05后续GPU路径修正：test_room_gpu_rendering.py新增1项（本模块共8项），生产模板删除gpus，覆盖文件!reset清除旧gpus请求，同时保留NVIDIA runtime与设备/graphics环境变量。替代上一轮测试要求保留gpus: all的中间策略；依据远端同镜像不带--gpus时图形库加载成功。仅作配置文本回归，Compose的!reset支持和实际合并必须在远端config --quiet及inspect验证。

2026-11-05：test_room_gpu_rendering.py新增1项，检查生产模板/覆盖文件都显式设置runtime: nvidia且仅作用app-server，保留gpus: all。只读配置检查，不运行Docker。宿主机缺库已由管理员补齐，当前调整对应容器实际Runtime=runc的远端证据；真实图形库注入仍待服务器验证。

GPU修复后相关回归共120项通过（前次114项加6项GPU守卫测试）；未运行真实Blender/GPU或远端任务，实际L20上下文须在正式任务首帧后确认。

GPU修复新增 `test_room_gpu_rendering.py`（6项），追溯PRD2.3/architecture3.3：NVIDIA上下文通过，软件/未知/非NVIDIA拒绝；执行真实worker AST守卫并验证失败前留证、发布帧前阻断；final强制GPU且旧CPU契约无法续跑；生产与覆盖配置仅请求所需图形能力。正式流程进程替身补充合成NVIDIA证据，避免测试默许CPU。命令：`python -m unittest test.test_room_gpu_rendering test.test_room_animation_final test.test_room_animation_camera test.test_room_animation -v`。未在本地运行Docker/Blender/GPU，不安装驱动。

本次直接正式出片相关回归：114项通过（包含静帧、火烟、相机、动画、资产和户型测试）；新增直接出片测试5项。真实576帧视频及远端耗时尚未运行，由用户按正式命令执行后验收。

2026-11-04 直接正式出片：新增 `test_room_animation_final.py`（5项），对应PRD 2.3 / architecture 3.3。验证显式直接出片授权、冻结风格、24秒720p24fps576个纯总览帧、错误模式拒绝、续跑授权一致、保留冲突检查、不调用短片审核/耗时预估、完整解码通过才发布、解码失败保留帧和编码产物。原编码替身适配新增解码步骤；不运行真实Blender/ffmpeg。命令：`python -m unittest test.test_room_animation_final test.test_room_animation_camera test.test_room_animation -v`。模拟耗时与视频字节不是服务器实测或真实成片。

说明新增测试名称、对应需求、命令、通过/失败/跳过数量、未验证项及原因。涉及 app 行为修改但缺少对应新增测试时，不标记该功能为完成。本规范目前是开发约定，尚未添加自动 CI 强制检查。
