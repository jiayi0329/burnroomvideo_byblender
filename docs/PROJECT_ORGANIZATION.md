# 项目职责目录与渐进迁移规范

更新：2026-11-07。**以下为目标目录和处置计划，本轮不创建应用骨架、不批量移动或删除源码。** 当前可执行路径仍为 app/、test/、release/。架构依据见 [ARCHITECTURE](ARCHITECTURE.md)。

## 1. 两个分类维度

Frontend/Backend/Render Engine 是职责；运行代码、测试配置、诊断、历史资料、生成产物是用途。同一份几何函数可以被运行与诊断同时使用，不能因为文件名带 diagnose 就认定可删除。

| 用途 | 处理原则 |
| --- | --- |
| 正式运行 | 保留；迁移须保留入口、导入与部署兼容 |
| 测试/公共配置 | 与被测模块一同维护；R1/R2 仍用于回归，R3 冻结 |
| 辅助诊断 | 先拆正式链路依赖，再迁移 tools/diagnostics |
| 历史资料 | 原样归档并标明日期；过期指令不继续执行 |
| 可再生产物 | 放私有 data/ 或 release/out/，不提交模型/视频/真实诊断 |
| 待确认删除 | 只有引用、测试、文档、部署与历史依据均核对后再审阅 |
| Legacy | 旧系统仍有调用，不能与新版互相替换或直接删除 |

## 2. 目标结构（尚未迁移）

```text
frontend/
  src/{pages,components,api,types}/
backend/
  api/{rooms,jobs,assets}/
  services/                    # 参数/任务/交付编排
  repositories/                # 关系目录抽象
  adapters/{files,postgres,minio}/
  cli/                         # 显式导入/核验
  db/migrations/
render_engine/
  geometry/                    # OBJ/UV、多边形裁切、未来高度候选
  propagation/                 # 点位拓扑与房间 BFS
  effects/                     # 纯参数/几何生成
  blender/                     # bpy 专用入口及节点/镜头辅助
  jobs/                        # 普通 Python launcher、状态、编码、GPU监控
tools/
  diagnostics/                 # 非正式流程检查、断面图与API探测
  integration/                 # 需明确环境的手工集成检查
tests/{backend,engine,tools,deploy}/
configs/{render,schemas}/       # 公共预设；数据契约模式待落地
docs/                          # 当前需求、架构、状态、运行手册
  archive/                     # 不可当成当前操作指南
deploy/                        # Docker、Compose、发布脚本、模板
app/                           # 过渡保留，含新版及Legacy入口
test/                          # 当前测试，暂不改成 tests/
release/                       # 当前发布入口，暂不改成 deploy/
```

`configs/schemas/` 为以后实现请求校验的目标位置，本轮 Markdown 示例不等于已实现 JSON Schema。职责拆分不承诺同时拆镜像、服务或引入任务队列。

## 3. 当前文件到目标位置

| 当前文件/文件组 | 用途与职责 | 目标位置与前提 |
| --- | --- | --- |
| app/main.py | Legacy API 与编排，仍使用 | 先保留；未来 Backend 的 Legacy 兼容路由，不能整体当新版 jobs API |
| app/room_api.py | 内部数据库目录查询 | backend/api/；现有整数 room_id 与新业务 ID 需明确转换 |
| app/database.py、app/db/001_rooms.sql | 数据库连接及显式迁移 | backend/adapters/postgres/、backend/db/migrations/；已应用迁移文件不得改写 |
| app/import_rooms.py、app/check_catalog.py | 导入/只读核验 CLI | backend/cli/；前者依赖 analyze_floorplan，仍被 inspect 间接复用 |
| app/s3_io.py | Legacy MinIO 适配 | backend/adapters/minio/；保留旧 key 兼容，新增版本 key 另写适配 |
| app/observability.py | Legacy 文件状态与GPU监控 | 先保留；未来按旧编排与引擎监控边界提取公共部分 |
| app/F6_detect.py、app/F7_spread.py | 烧损分析、旧传播；旧 main 及测试调用 | render_engine/propagation/；保留旧 BFS 语义，不与房间 BFS 混写 |
| app/run_room_animation.py | 新版普通 Python 启动、锁、编码、报告 | render_engine/jobs/；CLI、worker路径、八文件指纹清单同步迁移 |
| app/room_animation_job.py | 冻结契约/状态/续跑/审核/统计 | render_engine/jobs/；无 bpy，保持文件边界 |
| app/F8_room_animation.py（F8-E） | Blender 动画 worker | render_engine/blender/；必须先处理对 D/B/样式模块的导入 |
| app/F8_room_demo.py（F8-D） | 展示/静帧入口，动画仍复用辅助函数 | render_engine/blender/；**不是可删除的旧预览实验** |
| app/F8_room_fire_style.py | D/E 共用的 bpy 材质/灯光辅助 | render_engine/blender/；不是单独任务入口 |
| app/room_fire_config.py | 纯配置校验、火舌/烟柱几何 | render_engine/effects/；R3 指纹和测试保持 |
| app/room_demo_plan.py | 展示分量与房间 BFS 的纯函数 | 先保持单文件；后按 geometry/propagation 提取，避免顺便改算法 |
| app/prepare_room_candidate.py、app/room_clip_geometry.py | 候选裁切入口与纯几何 | render_engine/geometry/；候选入口依赖 diagnose.load_inputs，不能先移走该模块 |
| app/F8_prepare_room_asset.py（F8-B） | 资产导出、重载、展示截断辅助 | render_engine/blender/；D/E 依赖其 below/make_mesh 等函数，须先提取公共辅助 |
| app/analyze_floorplan.py | 对齐分析，也被导入/候选/诊断复用 | 纯解析与变换进入 render_engine/geometry/；报告CLI再放 tools/diagnostics/ |
| app/inspect_room_asset.py | 历史坐标/高度检查，含被复用的 OBJ/MTL 读取 | 先将只读解析工具提取到 geometry/，诊断外壳才移 tools/diagnostics/ |
| app/diagnose_room_sections.py | 历史断面入口；load_inputs 仍被候选使用 | 先拆输入指纹校验与诊断绘图职责，再迁移外壳 |
| app/room_section_geometry.py、app/room_section_plots.py | 断面计算/可选 Matplotlib 绘图 | tools/diagnostics/；一起检查 diagnose 与 test_room_sections 的引用 |
| app/F8_inspect_room_import.py（F8-A） | 已完成的 Blender 导入检查依据 | tools/diagnostics/blender/；保留追溯脚本与两个测试的静态检查 |
| app/probe_floorplan.py | 上游 API 探测，相关测试仍在 | tools/diagnostics/；仅移动代码，不提交真实返回包或 appkey |
| app/F8_blender_render.py（F8-C） | 旧 main 绑定的 Legacy worker | 保留原入口；之后可迁至独立 legacy 区并保留兼容启动路径 |
| app/room_fire_round1/2/3.json | 公共预设；旧轮次用于回归 | configs/render/；迁移要改默认寻址和打包，不改 R3 内容 |
| test/*.py、test/__init__.py | 当前单元/替身/部分集成测试 | 后续逐组迁至 tests/，保留现有模块命令直至引用更新 |
| test_4dkankan.py | 根目录手工 API 检查脚本 | tools/integration/ 候选；先核对网络副作用/凭证来源，不直接纳入离线发现 |
| release/scripts/*、release/*.yml、release/prod.env.example、Dockerfile、docker-compose.yml | 当前部署与开发配置 | deploy/；最后迁移，保留旧脚本过渡入口并核对 BOM/换行 |
| requirements*.txt、.gitignore、.dockerignore | 构建与依赖边界 | 根目录先保留；诊断绘图库继续与生产依赖分开 |
| docs/room_*.md、docs/database.md | 操作依据与部分历史实验 | 建索引标明适用版本；核对引用后再逐篇归档，不能全量移走 |
| PRD_V1.1.md、architecture.md | 原始累积文档 | 原样快照在 archive；根文件保留兼容链接，新有效规范在 docs/ |
| data/**、release/out/** | 私有资产/诊断/任务/备份/安装包 | 继续忽略；服务器/本地目录不因代码迁移而改名 |

## 4. 必须先拆的依赖

实际链条：`prepare_room_candidate → diagnose_room_sections.load_inputs → inspect_room_asset → import_rooms → analyze_floorplan`；其中数据库连接是延迟执行，不能据此说引擎已经必须连库。但这条文件依赖链让“先移动全部诊断工具”不安全。

动画链条：`F8_room_animation → F8_room_demo / F8_prepare_room_asset / F8_room_fire_style`。D/B 的复用函数先提取为 Blender 内部辅助，保持旧入口包装；普通 Python 业务端不能为了复用而导入这些 bpy 模块。

测试既有普通导入，也有 AST 提取和按文件路径读取。候选、断面、导入、静帧、动画及 GPU 测试都要随实际引用回归，不能只替换 import 字符串。

## 5. 三批后续迁移（均待审阅）

1. **纯函数与诊断解耦**：保留 CLI、原算法和旧路径，提取只读输入/OBJ解析；回归候选、户型、断面与数据库预览。所有成果仍可由原命令调用。
2. **新版引擎内部整理**：保留旧 F8-C，迁移 D/E/B 共用函数、纯样式和 job helpers；同步配置寻址、源码指纹、AST测试与 SCP 清单。旧任务不能因新源码直接续跑，冻结 V1 仍从归档还原。
3. **目录落位与稳定合并**：逐组迁移 backend、tools、tests、configs，最后部署脚本；检查镜像 COPY、包内路径、BOM和普通 Python/bpy隔离。审查后再决定 main 合并与标签，用户执行 Git 写操作。

每批分独立提交，说明改变的路径、兼容入口、实际测试和回退提交。不把高度算法、Hybrid、网页或数据库导入混入迁移。

## 6. 文档与产物边界

当前新文档是有效入口；原文档和过期配置过程作为历史材料。Git 当前已忽略 /data/ 与 release/out/，但不代表任意目录下的 PNG/BLEND/GLB 都自动忽略。真实产物一律进入上述私有目录；不为此全局忽略所有 PNG，避免屏蔽以后合法的合成测试图。

下一次提交前看 diff 与新增文件清单，只提交源码/测试/公共配置/脱敏文档。文件移动需用户审阅处置清单后实施，本次没有任何待自动删除的文件。
