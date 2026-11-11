# Burnroom：单房间火灾演示系统

更新：2026-11-11。当前分支chore/room8-v1-baseline；源码已结束兼容期，只保留backend、render_engine、tools、deploy、tests等正式路径，没有app/release源码或test旧包。Room8 V1已阶段性出片，暂不重渲染；目录去重仅本地验收，远端新版本尚待复验，未据此合并main。

输入灾后扫描、户型及全景相机点位，输出独立房间资产和程序化火灾视频。它是演示/复盘辅助，不是CFD、真实起火原因认定或已完成的灾前重建。

## 先看这里

| 想了解什么 | 文档 |
| --- | --- |
| 产品范围与验收 | [PRD](docs/PRD.md) |
| 当前链路和目标系统 | [Architecture](docs/ARCHITECTURE.md) |
| 进度/下一步/未验收项 | [项目状态](docs/PROJECT_STATUS.md) |
| Room8 V1产物、版本和实测 | [发布基线](docs/RELEASES.md) |
| ID/版本/文件/数据库/MinIO关系 | [数据规范](docs/DATA_ASSET_SPEC.md) |
| 房间资产 / R3样式 / 动画运行 | [资产](docs/rendering/room_assets.md) · [R3](docs/rendering/style.md) · [动画](docs/rendering/animation.md) |
| 真实数据库导入 | [PostgreSQL计划](docs/database.md) |
| 老师要求的按钮/API/任务执行日志 | [日志契约，尚待实现](docs/OBSERVABILITY.md) |
| 后续开发必须遵守的约束 | [AGENTS](AGENTS.md) · [CLAUDE](CLAUDE.md) |
| 旧实验与迁移过程 | [主题归档](docs/archive/20261111_process/README.md) |

## 当前能力与限制

- Room8：独立裁切/UV材质贴图保留、13内部点BFS、R3火烟、独立overview、NVIDIA GPU动画、MP4与回执已远端跑通。正式视频24秒/1280×720/24fps/576帧；当次约6分钟，证据和限制见发布基线。
- XY人工核验为6条房间记录、22个点位，不是6个有效渲染房间；22客厅、32门口、42户型外、Room11无效。仅Room8有完整资产/视频验收。
- PostgreSQL服务/八表/CLI/API已有，真实数据导入未完成；Legacy MinIO链路已有，新版Room8资产/视频未完整登记。
- 前端、新版Room8任务API、完整操作监控、权限及东莞公网展示尚未实施；不创建空目录冒充完成。
- floor_z=-1.35m是平层工程近似；火焰生命周期偏短、后段烟为主，Hybrid、复杂积顶、火烟按墙裁切及灾前重建仍待解决。V1保留，不为文档整理重渲染。

## 分类标准和实际调用链

按职责分：Backend提供接口/数据编排，Engine处理几何/传播/效果/视频，Tools核验输入，Tests验证功能，Deploy打包/部署，Configs保存公共预设，Docs说明规则。按用途再区分正式实现、Legacy、诊断、测试、当前规范、历史资料和私有产物。是否保留依据引用/测试/证据，不按名字随意删文件。

```text
Legacy HTTP：backend.api.main → legacy F6/F7/F8-C → 场景根output.mp4 → 旧MinIO分享
房间资产：核验/review → geometry面级裁切 → candidate → Blender F8-B → 基础blend/GLB与检查图
Room8视频：jobs安全启动器 → Blender F8-E + R3/内部BFS → PNG → 编码/解码验证 → 独立任务MP4
```

F8-A是原OBJ导入检查，B是独立资产，C是旧视频，D是静帧，E是动画worker。业务Python不得import bpy；只在Blender进程运行专用脚本，任务从jobs启动器创建。旧POST /api/render会处理场景根旧视频，不能替代Room8入口。

源码指纹现在是25份引擎Python和3份公共预设，共28份；没有旧兼容脚本/配置副本。旧40文件或V1原任务不能用新代码改签续跑。R1/R2/R3是三个不同版本，仍各保留一份，默认R3。

## 常用操作与执行位置

本地PowerShell、完整项目、已安装依赖的Python：

```powershell
python -B -m tests.run_regression --list
python -B -m tests.run_regression
python -B -m tests.run_regression --group engine
python -m render_engine.jobs.run_room_animation --help
python -m backend.cli.import_rooms --help
.\deploy\scripts\build.ps1
```

本机已有隔离解释器可用`release/out/backend-test-env/Scripts/python.exe`代替python。最近代码回归303项：301通过、2项跳过；另9项F6/F7合成逻辑通过。本轮只改文档、核对清单/链接/指纹，不宣称重新执行代码或远端验收。默认回归不运行真实timeline写入、真实数据库或手工API，跳过不算通过。

WinSCP负责上传明确版本安装包/核验输入、下载产物；不在远端编辑代码。远程SSH进入已有Compose目录，按当前指南执行原环境核验、资产/渲染或数据库操作。deploy.ps1会连接SSH/SCP、备份并解压；构建/重建、导入和渲染须分别安排，本页不自动执行。禁止本地启动Docker/服务器。

## 私有数据和产物（不在Git文件清单中）

| 位置/文件 | 代表什么 |
| --- | --- |
| data/<scene>/；服务器app-data；容器/app/data | 实际扫描、核验、房间资产和任务；三者通过SHA/版本核对，不凭mtime认定正式版本 |
| mesh.obj / MTL / 贴图 / points.json / 全景图 | 原始完整模型、材质、相机姿态和拓扑 |
| diagnostics/<类型>/<版本> | 户型探测、alignment_report、overlay、review、导入/高度/断面证据 |
| rooms/<room>/<asset_version>/candidate.json、asset/ | 裁切候选及基础room.blend/room.glb、manifest/validation、检查图 |
| style_round*/<版本>/ | 各轮独立样帧、effective_settings、sample_manifest和展示副本 |
| render_jobs/<run_id>/ | 配置快照、room_timeline、帧、状态、尝试日志、视频和回执 |
| config_snapshot / render_manifest / timing_report / video_receipt | 任务冻结输入、实际帧/相机/产物、耗时及视频技术检查，不能混用 |
| PostgreSQL数据盘 | 场景/房间/点位/人工关系/文件/任务摘要；SQL文件不是实际数据 |
| MinIO数据盘 | 已上传对象，磁盘文件存在不等于已上传/已登记；签名不让内网地址自动公网可达 |
| release/out/ | 被忽略的安装包、测试环境/报告、迁移前备份和V1归档；不是保留两套正式源码 |

每个manifest须结合所在目录判断含义；JSON运行状态不是人工验收。原模型、review、基础房间和旧视频不覆盖；恢复先到独立目录，不修改历史SHA。

## 下一步

文档审阅提交后，先实现公共请求/操作/CLI日志，再做远端原环境验收和真实数据库导入（6房间、22点及人工关联），之后建设Room8/R3网页闭环和新版MinIO登记。日志规则已写AGENTS，具体组件、前端上报与监控仍待实现。第二房间、生命周期/Hybrid、权限与东莞展示各自排期。

main合并、标签、部署和真实数据写入不自动执行。当前源码提交号不冒充V1原远端checkout；完整交付与缺失附件以RELEASES为准。

## 完整文件清单

下面逐项列出本次整理后可提交的文件（含待提交文档），不包含Git内部目录、被忽略数据/缓存和本地工具环境。后续新增/删除文件应同步本表；归档原文只供追溯。目录README只维护专项边界，不重复本总表。

清单共 **148** 个文件。

<details>
<summary>根目录（10份）</summary>

| 文件路径 | 用途 | 属性/运行环境 |
| --- | --- | --- |
| [.dockerignore](.dockerignore) | Docker构建白名单，排除私有数据和凭证；不等于Git忽略规则 | 配置/规则 |
| [.gitattributes](.gitattributes) | Git文本换行规则，保证远端Shell为LF | 配置/规则 |
| [.gitignore](.gitignore) | 不提交私有data、安装包、备份、凭证及缓存 | 配置/规则 |
| [AGENTS.md](AGENTS.md) | 接续开发工具读取的规则，固定新API/CLI/前端/后台操作日志与测试要求 | 文档/约束 |
| [CLAUDE.md](CLAUDE.md) | 进程隔离、数据保护、远端环境、编码、打包和Git硬约束 | 文档/约束 |
| [Dockerfile](Dockerfile) | 应用镜像依赖与backend.api.main:app启动命令；本地不运行Docker | 配置/规则 |
| [README.md](README.md) | 项目入口、分类标准、全部文件用途及当前运行边界；本清单在此统一维护 | 文档/约束 |
| [docker-compose.yml](docker-compose.yml) | 根开发服务配置；生产使用deploy模板，当前不拆服务 | 配置/规则 |
| [requirements-diagnostics.txt](requirements-diagnostics.txt) | 可选Matplotlib诊断绘图依赖，与生产镜像分离 | 配置/规则 |
| [requirements.txt](requirements.txt) | 生产Python固定依赖，本文档整理不调整版本 | 配置/规则 |

</details>

<details>
<summary>backend：后端实现（17份）</summary>

| 文件路径 | 用途 | 属性/运行环境 |
| --- | --- | --- |
| [backend/README.md](backend/README.md) | 后端接口/数据能力、当前入口及尚未登记Room8的边界 | 文档/约束 |
| [backend/__init__.py](backend/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [backend/adapters/__init__.py](backend/adapters/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [backend/adapters/minio/__init__.py](backend/adapters/minio/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [backend/adapters/minio/s3_io.py](backend/adapters/minio/s3_io.py) | MinIO下载/上传、产物检查、7天预签名及可选桶策略 | 普通Python |
| [backend/adapters/postgres/__init__.py](backend/adapters/postgres/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [backend/adapters/postgres/database.py](backend/adapters/postgres/database.py) | PostgreSQL延迟连接、显式迁移/应用账号授权，不随服务启动执行 | 普通Python |
| [backend/api/__init__.py](backend/api/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [backend/api/main.py](backend/api/main.py) | FastAPI主实现：健康、场景获取、Legacy时间线/渲染/状态/分享和流水线 | 普通Python |
| [backend/api/room_api.py](backend/api/room_api.py) | /api/catalog房间、点位、资产查询及签名；数据库整数ID语义 | 普通Python |
| [backend/cli/__init__.py](backend/cli/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [backend/cli/check_catalog.py](backend/cli/check_catalog.py) | 应用账号权限与已导入场景目录的只读核验 | 普通Python |
| [backend/cli/import_rooms.py](backend/cli/import_rooms.py) | 核验输入构造关系计划；默认preview，--apply写库，上传另行明确 | 普通Python |
| [backend/database/migrations/001_rooms.sql](backend/database/migrations/001_rooms.sql) | scenes等八张业务表的唯一初始迁移；文件名/内容保持不变 | 数据库迁移 |
| [backend/paths.py](backend/paths.py) | 安装根、Legacy worker和SQL定位；不可变迁移指纹校验 | 普通Python |
| [backend/services/__init__.py](backend/services/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [backend/services/observability.py](backend/services/observability.py) | 已有Legacy生命周期/失败/状态/GPU监控；不是完整请求追踪 | 普通Python |

</details>

<details>
<summary>render_engine：渲染引擎（26份）</summary>

| 文件路径 | 用途 | 属性/运行环境 |
| --- | --- | --- |
| [render_engine/README.md](render_engine/README.md) | 引擎分层、B/D/E/Legacy职责和完整包/指纹要求 | 文档/约束 |
| [render_engine/__init__.py](render_engine/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [render_engine/blender/F8_prepare_room_asset.py](render_engine/blender/F8_prepare_room_asset.py) | F8-B：保存/重载独立基础blend、验证点位/材质、导出GLB及三视图 | 仅Blender |
| [render_engine/blender/F8_room_animation.py](render_engine/blender/F8_room_animation.py) | F8-E：安全启动器创建任务后执行的绝对时间动画worker | 仅Blender |
| [render_engine/blender/F8_room_demo.py](render_engine/blender/F8_room_demo.py) | F8-D：既有资产展示检查和R3六张静帧；不提供动画入口 | 仅Blender |
| [render_engine/blender/F8_room_fire_style.py](render_engine/blender/F8_room_fire_style.py) | Bpy火烟节点、灯光、渲染设置与实际参数回读；非任务入口 | 仅Blender |
| [render_engine/blender/F8_room_helpers.py](render_engine/blender/F8_room_helpers.py) | B/D/E共用网格/逐角UV、展示截断、镜头及射线辅助；非任务入口 | 仅Blender |
| [render_engine/blender/__init__.py](render_engine/blender/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [render_engine/effects/__init__.py](render_engine/effects/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [render_engine/effects/room_fire_config.py](render_engine/effects/room_fire_config.py) | art/events/quality校验、固定种子火舌/烟柱网格与时间曲线 | 普通Python |
| [render_engine/geometry/__init__.py](render_engine/geometry/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [render_engine/geometry/floorplan_alignment.py](render_engine/geometry/floorplan_alignment.py) | 18个共用只读户型解析、坐标变换、点归属和对齐分析函数 | 普通Python |
| [render_engine/geometry/prepare_room_candidate.py](render_engine/geometry/prepare_room_candidate.py) | 组织核验与实际裁切，写独立candidate.json及工程近似依据 | 普通Python |
| [render_engine/geometry/room_clip_geometry.py](render_engine/geometry/room_clip_geometry.py) | 凹多边形面级裁切，插值保留原Z、逐角UV与材质 | 普通Python |
| [render_engine/geometry/room_source_inputs.py](render_engine/geometry/room_source_inputs.py) | 模型/贴图/人工review/导入证据的输入绑定及指纹核验 | 普通Python |
| [render_engine/geometry/room_source_io.py](render_engine/geometry/room_source_io.py) | 只读OBJ/MTL、顶点/面/逐角UV/材质、坐标逆变换、路径和SHA | 普通Python |
| [render_engine/jobs/__init__.py](render_engine/jobs/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [render_engine/jobs/room_animation_job.py](render_engine/jobs/room_animation_job.py) | 配置快照/来源保护、续跑、绝对状态、帧/视频验证、耗时与审批契约 | 普通Python |
| [render_engine/jobs/run_room_animation.py](render_engine/jobs/run_room_animation.py) | 普通Python任务启动器：预检/锁/冲突、Blender、GPU、编码和失败保留 | 普通Python |
| [render_engine/legacy/F6_detect.py](render_engine/legacy/F6_detect.py) | 原F6烧损图像评分与起火点识别，旧HTTP仍使用 | 普通Python |
| [render_engine/legacy/F7_spread.py](render_engine/legacy/F7_spread.py) | 原F7拓扑BFS与旧timeline，不与Room8内部BFS混写 | 普通Python |
| [render_engine/legacy/F8_blender_render.py](render_engine/legacy/F8_blender_render.py) | F8-C旧全场景worker，操作场景根output.mp4；不能替代Room8新入口 | 仅Blender |
| [render_engine/legacy/__init__.py](render_engine/legacy/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [render_engine/paths.py](render_engine/paths.py) | 安装根、R3/worker定位及28份正式源码/预设指纹清单 | 普通Python |
| [render_engine/propagation/__init__.py](render_engine/propagation/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [render_engine/propagation/room_demo_plan.py](render_engine/propagation/room_demo_plan.py) | 展示连接分量、房间内部诱导子图BFS及渐变包络，无Hybrid | 普通Python |

</details>

<details>
<summary>configs：公共预设（4份）</summary>

| 文件路径 | 用途 | 属性/运行环境 |
| --- | --- | --- |
| [configs/render/README.md](configs/render/README.md) | 三份公共预设的用途、当前默认与批准指纹约束 | 文档/约束 |
| [configs/render/room_fire_round1.json](configs/render/room_fire_round1.json) | 第一轮风格配置，历史对比/回归，非默认 | 配置/规则 |
| [configs/render/room_fire_round2.json](configs/render/room_fire_round2.json) | 第二轮尺寸/厚度/烟柱配置，历史回归，非默认 | 配置/规则 |
| [configs/render/room_fire_round3.json](configs/render/room_fire_round3.json) | 当前R3批准艺术基线，默认；内容冻结 | 配置/规则 |

</details>

<details>
<summary>tools：诊断与手工集成（13份）</summary>

| 文件路径 | 用途 | 属性/运行环境 |
| --- | --- | --- |
| [tools/README.md](tools/README.md) | 诊断/手工联网入口和历史依据，不重复根文件总表 | 文档/约束 |
| [tools/__init__.py](tools/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [tools/diagnostics/__init__.py](tools/diagnostics/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [tools/diagnostics/analyze_floorplan.py](tools/diagnostics/analyze_floorplan.py) | 调用只读核心，输出alignment_report、CSV和overlay.html | 普通Python |
| [tools/diagnostics/blender/F8_inspect_room_import.py](tools/diagnostics/blender/F8_inspect_room_import.py) | F8-A：原OBJ导入坐标/UV/材质/贴图检查，不裁切/渲染 | 仅Blender |
| [tools/diagnostics/blender/__init__.py](tools/diagnostics/blender/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [tools/diagnostics/diagnose_room_sections.py](tools/diagnostics/diagnose_room_sections.py) | 组织采样断面、连续性/墙面证据、图和人工检查报告 | 普通Python |
| [tools/diagnostics/inspect_room_asset.py](tools/diagnostics/inspect_room_asset.py) | 材质/UV/坐标及竖直高度采样核验，保留历史物理问题 | 普通Python |
| [tools/diagnostics/probe_floorplan.py](tools/diagnostics/probe_floorplan.py) | 上游户型API探测/脱敏、受限下载与包检查；联网须显式运行 | 普通Python |
| [tools/diagnostics/room_section_geometry.py](tools/diagnostics/room_section_geometry.py) | 断面求交、上下表面连续性、边界及墙面偏差分析纯函数 | 普通Python |
| [tools/diagnostics/room_section_plots.py](tools/diagnostics/room_section_plots.py) | 可选Matplotlib断面/采样平面图与HTML索引 | 普通Python |
| [tools/integration/__init__.py](tools/integration/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [tools/integration/probe_scene_api.py](tools/integration/probe_scene_api.py) | 手工场景API连接检查，--allow-network才请求；只输出脱敏状态/数量 | 普通Python |

</details>

<details>
<summary>tests：测试（45份）</summary>

| 文件路径 | 用途 | 属性/运行环境 |
| --- | --- | --- |
| [tests/README.md](tests/README.md) | 当前分组回归命令、测试约定、依赖和真实集成开关 | 文档/约束 |
| [tests/__init__.py](tests/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [tests/backend/__init__.py](tests/backend/__init__.py) | 登记该职责组的离线模块清单，供tests/suites.py汇总 | 包/测试组登记 |
| [tests/backend/test_backend_migration.py](tests/backend/test_backend_migration.py) | 后端正式路径、启动隔离、SQL/账号/旧worker、完整包与API保持 | 离线测试/替身 |
| [tests/backend/test_catalog_deployment.py](tests/backend/test_catalog_deployment.py) | 目录与旧下载隔离、应用账号、部署及旧功能可用性 | 离线测试/替身 |
| [tests/backend/test_room_api.py](tests/backend/test_room_api.py) | catalog房间/点位/资产接口、分页和错误处理 | 离线测试/替身 |
| [tests/backend/test_room_database.py](tests/backend/test_room_database.py) | 合成导入/人工结论保护及显式真实PostgreSQL事务集成 | 离线测试/替身 |
| [tests/backend/test_v6_share.py](tests/backend/test_v6_share.py) | 预签名/已有产物、旧分享API、缓存及GPU温度保护 | 离线测试/替身 |
| [tests/deploy/__init__.py](tests/deploy/__init__.py) | 登记该职责组的离线模块清单，供tests/suites.py汇总 | 包/测试组登记 |
| [tests/deploy/test_canonical_layout.py](tests/deploy/test_canonical_layout.py) | 唯一正式路径、SQL/R3、28文件指纹及旧40文件任务拒绝 | 离线测试/替身 |
| [tests/deploy/test_migration_cleanup.py](tests/deploy/test_migration_cleanup.py) | 离线注册/报告及部署状态保护、必需模板/入口和产物隔离 | 离线测试/替身 |
| [tests/deploy/test_release_safety.py](tests/deploy/test_release_safety.py) | 临时PowerShell/tar打包、秘密排除、外部命令失败阻断 | 离线测试/替身 |
| [tests/engine/__init__.py](tests/engine/__init__.py) | 登记该职责组的离线模块清单，供tests/suites.py汇总 | 包/测试组登记 |
| [tests/engine/test_blender_room_helpers.py](tests/engine/test_blender_room_helpers.py) | 合成Blender辅助，UV/材质/坐标/镜头及源码保护 | 离线测试/替身 |
| [tests/engine/test_engine_migration.py](tests/engine/test_engine_migration.py) | 正式引擎CLI/导入、完整源码清单、安装包及旧任务拒绝 | 离线测试/替身 |
| [tests/engine/test_prepare_room_asset.py](tests/engine/test_prepare_room_asset.py) | 基础保存/重载、点位对应、剖面及检查图逻辑 | 离线测试/替身 |
| [tests/engine/test_room_animation.py](tests/engine/test_room_animation.py) | 任务隔离/锁、绝对时间、帧/编码/报告/续跑与失败保留 | 离线测试/替身 |
| [tests/engine/test_room_animation_camera.py](tests/engine/test_room_animation_camera.py) | overview/closeup独立相机、构图、有效机位证据及只读旧报告 | 离线测试/替身 |
| [tests/engine/test_room_animation_final.py](tests/engine/test_room_animation_final.py) | 直接正式出片门禁、576帧/总览/冻结风格及完整解码保护 | 离线测试/替身 |
| [tests/engine/test_room_candidate.py](tests/engine/test_room_candidate.py) | 凹多边形裁切、UV/Z、工程近似、版本隔离与源文件保护 | 离线测试/替身 |
| [tests/engine/test_room_demo.py](tests/engine/test_room_demo.py) | 静帧展示与材质节点替身，不等于真实渲染效果验收 | 离线测试/替身 |
| [tests/engine/test_room_demo_plan.py](tests/engine/test_room_demo_plan.py) | 展示连接分量、内部子图BFS和渐变包络 | 离线测试/替身 |
| [tests/engine/test_room_fire_config.py](tests/engine/test_room_fire_config.py) | 配置、四色/密度分离、火舌几何和事件排除策略 | 离线测试/替身 |
| [tests/engine/test_room_fire_round2.py](tests/engine/test_room_fire_round2.py) | 第二轮火体尺寸/厚度、烟柱/吸收/成长及回归 | 离线测试/替身 |
| [tests/engine/test_room_fire_round3.py](tests/engine/test_room_fire_round3.py) | 第三轮曝光/光照/烟可读性回读及风格冻结 | 离线测试/替身 |
| [tests/engine/test_room_fire_style.py](tests/engine/test_room_fire_style.py) | 实际设置回读、缺失/截断拒绝和静帧门禁 | 离线测试/替身 |
| [tests/engine/test_room_gpu_rendering.py](tests/engine/test_room_gpu_rendering.py) | NVIDIA证据/软件渲染拒绝、final GPU门禁及生产模板；非实机性能测试 | 离线测试/替身 |
| [tests/engine/test_room_source_inputs.py](tests/engine/test_room_source_inputs.py) | review/贴图/导入证据与输入指纹、路径隔离 | 离线测试/替身 |
| [tests/engine/test_room_source_io.py](tests/engine/test_room_source_io.py) | 合成OBJ/MTL、逐角UV/材质、数值/索引与原始Z | 离线测试/替身 |
| [tests/engine_paths.py](tests/engine_paths.py) | AST回归定位实际引擎/后端/诊断源码，不再使用旧app路径 | 离线测试/替身 |
| [tests/integration/__init__.py](tests/integration/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [tests/integration/test_api.py](tests/integration/test_api.py) | 真实timeline API集成，会写真实文件；须ROOM_TIMELINE_INTEGRATION=1 | 显式真实集成 |
| [tests/legacy/__init__.py](tests/legacy/__init__.py) | Python包初始化/职责边界；不自动启动服务、连库或渲染 | 包/测试组登记 |
| [tests/legacy/test_f6.py](tests/legacy/test_f6.py) | 旧F6合成图像/边界及私有全景场景回归；未纳入默认全模块执行 | 含私有数据回归 |
| [tests/legacy/test_f7.py](tests/legacy/test_f7.py) | 旧F7合成BFS及私有points回归；未纳入默认全模块执行 | 含私有数据回归 |
| [tests/run_regression.py](tests/run_regression.py) | 显式离线回归入口、分组/列表/报告、真实集成环境拒绝及非零失败码 | 离线测试/替身 |
| [tests/suites.py](tests/suites.py) | 四组测试模块与必需入口清单，去重；不自动发现全仓库 | 离线测试/替身 |
| [tests/tool_paths.py](tests/tool_paths.py) | 临时发布测试使用的10份诊断源码白名单 | 离线测试/替身 |
| [tests/tools/__init__.py](tests/tools/__init__.py) | 登记该职责组的离线模块清单，供tests/suites.py汇总 | 包/测试组登记 |
| [tests/tools/test_analyze_floorplan.py](tests/tools/test_analyze_floorplan.py) | 房间多边形、坐标候选、边界/外部/重叠归属 | 离线测试/替身 |
| [tests/tools/test_diagnostics_migration.py](tests/tools/test_diagnostics_migration.py) | 诊断正式CLI、惰性依赖、报告失败保留及包导入 | 离线测试/替身 |
| [tests/tools/test_inspect_room_asset.py](tests/tools/test_inspect_room_asset.py) | 材质/UV/竖直交点与高度采样，Blender检查静态约束 | 离线测试/替身 |
| [tests/tools/test_probe_floorplan.py](tests/tools/test_probe_floorplan.py) | 假API/脱敏/下载地址和大小限制/压缩包与错误分类 | 离线测试/替身 |
| [tests/tools/test_room_sections.py](tests/tools/test_room_sections.py) | 断面/连续性/墙面证据，含可选Matplotlib端到端绘图 | 离线测试/替身 |
| [tests/tools/test_tools_migration.py](tests/tools/test_tools_migration.py) | 共享核心、正式工具导入、手工API允许开关/脱敏和完整包 | 离线测试/替身 |

</details>

<details>
<summary>deploy：发布工具与模板（7份）</summary>

| 文件路径 | 用途 | 属性/运行环境 |
| --- | --- | --- |
| [deploy/README.md](deploy/README.md) | 本地/SSH/WinSCP职责、唯一发布路径、保护与回退边界 | 文档/约束 |
| [deploy/docker-compose.gpu.yml](deploy/docker-compose.gpu.yml) | 只针对app-server的GPU覆盖，清除旧gpus请求并请求图形能力 | 配置/规则 |
| [deploy/docker-compose.prod.yml](deploy/docker-compose.prod.yml) | 生产应用/MinIO/PostgreSQL服务、NVIDIA环境及持久化挂载 | 配置/规则 |
| [deploy/prod.env.example](deploy/prod.env.example) | 无真实凭证的生产变量模板；不能覆盖远端已用密码 | 普通Python |
| [deploy/scripts/build.ps1](deploy/scripts/build.ps1) | 本地PowerShell白名单打包与SQL/预设指纹保护，输出release/out | 发布工具 |
| [deploy/scripts/deploy.ps1](deploy/scripts/deploy.ps1) | 本地SSH/SCP上传、远端备份检查与解压；不是自动获准执行 | 发布工具 |
| [deploy/scripts/prepare_deploy.sh](deploy/scripts/prepare_deploy.sh) | 远端Legacy/Room8活动状态阻断、配置/镜像/数据备份，不启动渲染 | 发布工具 |

</details>

<details>
<summary>docs：当前规范与指南（12份）</summary>

| 文件路径 | 用途 | 属性/运行环境 |
| --- | --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 当前三条链路、组件/数据/进程边界与尚未实现的目标架构 | 文档/约束 |
| [docs/DATA_ASSET_SPEC.md](docs/DATA_ASSET_SPEC.md) | 场景/房间/版本/任务ID、存储位置、指纹、上传登记及恢复规则 | 文档/约束 |
| [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md) | 待实现的按钮/API/CLI/任务关联日志、时间线、耗时、脱敏和监控验收 | 文档/约束 |
| [docs/PRD.md](docs/PRD.md) | 产品目标、MVP、验收及日志/真实导入/网页的实施优先级 | 文档/约束 |
| [docs/PROJECT_ORGANIZATION.md](docs/PROJECT_ORGANIZATION.md) | 职责/用途分类和依赖方向；逐文件表只在根README维护 | 文档/约束 |
| [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) | 已完成/部分完成/待实施、限制及后续门禁，不追加每轮代码流水账 | 文档/约束 |
| [docs/README.md](docs/README.md) | 当前需求、架构、状态、指南与归档的阅读索引 | 文档/约束 |
| [docs/RELEASES.md](docs/RELEASES.md) | Room8 V1固定资产/任务/配置/视频/性能/缺失项；原运行路径保持历史含义 | 文档/约束 |
| [docs/database.md](docs/database.md) | PostgreSQL当前路径、真实导入前备份/预览/人工关系/幂等与恢复计划 | 文档/约束 |
| [docs/rendering/animation.md](docs/rendering/animation.md) | 完整代码包、overview动画、GPU证据、逐帧观察、视频验收及续跑 | 文档/约束 |
| [docs/rendering/room_assets.md](docs/rendering/room_assets.md) | 核验→面级裁切→基础blend/GLB→展示检查及平层近似边界 | 文档/约束 |
| [docs/rendering/style.md](docs/rendering/style.md) | 独立可读的当前R3参数/效果/六样帧指南；不需要先读R1/R2 | 文档/约束 |

</details>

<details>
<summary>docs/archive：历史资料（14份）</summary>

| 文件路径 | 用途 | 属性/运行环境 |
| --- | --- | --- |
| [docs/archive/20261107_pre_baseline/CLAUDE.md](docs/archive/20261107_pre_baseline/CLAUDE.md) | 原始开发约束快照，当前约束见根CLAUDE | 历史资料 |
| [docs/archive/20261107_pre_baseline/PRD_V1.1.md](docs/archive/20261107_pre_baseline/PRD_V1.1.md) | 整理前原始需求快照，非当前任务 | 历史资料 |
| [docs/archive/20261107_pre_baseline/README.md](docs/archive/20261107_pre_baseline/README.md) | 原始开发/部署说明快照，旧冷启动命令不执行 | 历史资料 |
| [docs/archive/20261107_pre_baseline/README_ARCHIVE.md](docs/archive/20261107_pre_baseline/README_ARCHIVE.md) | 2026-11-07原始快照边界，保留旧链接语义 | 历史资料 |
| [docs/archive/20261107_pre_baseline/architecture.md](docs/archive/20261107_pre_baseline/architecture.md) | 整理前原始架构快照，非当前架构 | 历史资料 |
| [docs/archive/20261107_pre_baseline/manifest.json](docs/archive/20261107_pre_baseline/manifest.json) | 整理前原始文档来源/逐文件SHA，不改写 | 历史资料 |
| [docs/archive/20261111_process/README.md](docs/archive/20261111_process/README.md) | 合并来源、当前替代指南和历史内容读取方式 | 历史资料 |
| [docs/archive/20261111_process/animation_history.md](docs/archive/20261111_process/animation_history.md) | 原动画/相机/正式出片/GPU四份过程合并，旧命令仅追溯 | 历史资料 |
| [docs/archive/20261111_process/database_history.md](docs/archive/20261111_process/database_history.md) | 旧数据库部署、权限、导入操作原文，现行入口见docs/database.md | 历史资料 |
| [docs/archive/20261111_process/engineering_history.md](docs/archive/20261111_process/engineering_history.md) | 七批/去重和旧状态/架构/目录规范六份原文合并 | 历史资料 |
| [docs/archive/20261111_process/manifest.json](docs/archive/20261111_process/manifest.json) | 19份来源路径/提交/Git blob/原SHA和规范化范围，六份合并文档SHA | 历史资料 |
| [docs/archive/20261111_process/render_style_history.md](docs/archive/20261111_process/render_style_history.md) | R1/R2/R3三份原始风格记录合并，不作为当前调参指令 | 历史资料 |
| [docs/archive/20261111_process/room_assets_history.md](docs/archive/20261111_process/room_assets_history.md) | 原导入/高度断面/候选/展示四份过程合并 | 历史资料 |
| [docs/archive/20261111_process/testing_history.md](docs/archive/20261111_process/testing_history.md) | 原测试追溯和各批测试记录，不作为当前包路径说明 | 历史资料 |

</details>
