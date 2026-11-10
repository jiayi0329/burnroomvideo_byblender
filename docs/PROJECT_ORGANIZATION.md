# 项目职责目录与渐进迁移规范

更新：2026-11-09。**第1–5批已完成本地整理；其余工具与测试/部署目录仍为计划。** app旧入口、test、release继续保留，不创建前端骨架或删除Legacy源码。架构依据见[ARCHITECTURE](ARCHITECTURE.md)。

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

## 2. 目标结构（已落地部分见映射表）

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
  analysis/                    # 烧损图像/起火点分析，独立于传播算法
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

目标依赖方向：Frontend 通过 API 访问 Backend；Backend 通过文件契约和普通 Python 启动器调用 Render Engine；tools 可以使用引擎纯函数，Render Engine 不反向导入 tools 或 Backend。普通 Python 端不能导入 render_engine/blender 中的 bpy 模块。数据库 CLI 与引擎都需要的读取/变换逻辑归纯函数层，不再放在带业务编排的导入 CLI 内。

## 3. 当前文件到目标位置

| 当前文件/文件组 | 用途与职责 | 目标位置与前提 |
| --- | --- | --- |
| app/main.py、app/room_api.py | API兼容模块，ASGI入口保留 | 实现已迁backend/api；保留Legacy/catalog，不是新版jobs API |
| app/database.py、app/db/001_rooms.sql | 连接/迁移兼容模块与SQL副本 | 实现已迁backend/adapters/postgres，SQL原样复制至backend/db/migrations；新旧副本不一致则拒绝 |
| app/import_rooms.py、app/check_catalog.py | 导入/只读核验兼容CLI | 实现已迁backend/cli；依然延迟连库，build_plan被inspect间接复用 |
| app/s3_io.py | MinIO兼容模块 | 实现已迁backend/adapters/minio；原key/签名不变，新版登记另行开发 |
| app/observability.py | Legacy日志/状态/GPU监控兼容模块 | 实现已迁backend/services；未与新版引擎监控合并 |
| app/F6_detect.py | 烧损图像与起火点分析；旧 main 及测试调用 | render_engine/analysis/；保持评分语义，不顺便修改起火点选择 |
| app/F7_spread.py | 旧传播；旧 main 及测试调用 | render_engine/propagation/；保留旧 BFS 语义，不与房间 BFS 混写 |
| app/run_room_animation.py、app/room_animation_job.py | 兼容入口；启动/锁/编码/状态/续跑实现 | 已迁入render_engine/jobs；安装根寻址及完整源码指纹已适配 |
| app/F8_room_animation.py（E）、F8_room_demo.py（D）、F8_prepare_room_asset.py（B） | Blender兼容入口 | 实现已迁入render_engine/blender；保留原函数接口与CLI |
| app/F8_room_helpers.py、F8_room_fire_style.py | Blender公共辅助兼容模块 | 实现已迁入render_engine/blender；不被普通Python业务端导入 |
| app/room_fire_config.py | 配置校验、火舌/烟柱几何兼容模块 | 实现已迁入render_engine/effects；算法不变 |
| app/room_demo_plan.py | 展示分量/BFS兼容模块 | 整体迁入render_engine/propagation，暂不继续拆算法 |
| app/prepare_room_candidate.py、room_clip_geometry.py、room_source_io.py、room_source_inputs.py | 候选/几何/输入兼容模块 | 实现已迁入render_engine/geometry，不反向导入app/Backend/tools |
| app/analyze_floorplan.py | 对齐分析，也被导入/候选/诊断复用 | 纯解析与变换进入 render_engine/geometry/；报告CLI再放 tools/diagnostics/ |
| app/inspect_room_asset.py | 历史坐标/高度检查，保留公共读取函数名导出 | 解析已在app内提取；后续诊断外壳迁入tools，仍须核对build_plan等依赖 |
| app/diagnose_room_sections.py | 旧CLI/导入兼容，保留load_inputs/REQUIRED_CHECKS接口 | 已迁至tools/diagnostics/diagnose_room_sections.py；app指向同一模块 |
| app/room_section_geometry.py、app/room_section_plots.py | 旧导入兼容，保留断面/绘图函数 | 实现已迁至tools/diagnostics/；Matplotlib仍只在绘图时导入 |
| app/F8_inspect_room_import.py（F8-A） | 已完成的 Blender 导入检查依据 | tools/diagnostics/blender/；保留追溯脚本与两个测试的静态检查 |
| app/probe_floorplan.py | 上游 API 探测，相关测试仍在 | tools/diagnostics/；仅移动代码，不提交真实返回包或 appkey |
| app/F8_blender_render.py（F8-C） | 旧 main 绑定的 Legacy worker | 保留原入口；之后可迁至独立 legacy 区并保留兼容启动路径 |
| configs/render/room_fire_round1/2/3.json、旧app副本 | 默认预设与兼容副本 | 第4批原样复制，默认寻址已迁移；打包拒绝新旧副本不一致 |
| test/*.py、test/__init__.py | 当前单元/替身/部分集成测试 | 后续逐组迁至 tests/，保留现有模块命令直至引用更新 |
| test_4dkankan.py | 根目录手工 API 检查脚本 | tools/integration/ 候选；先核对网络副作用/凭证来源，不直接纳入离线发现 |
| release/scripts/*、release/*.yml、release/prod.env.example、Dockerfile、docker-compose.yml | 当前部署与开发配置 | deploy/ 目录本身最后迁移；代码每次跨目录移动时，原位置打包规则必须同步适配，不能留到最后 |
| requirements*.txt、.gitignore、.dockerignore | 构建与依赖边界 | 根目录先保留；诊断绘图库继续与生产依赖分开 |
| docs/room_*.md、docs/database.md | 操作依据与部分历史实验 | 建索引标明适用版本；核对引用后再逐篇归档，不能全量移走 |
| PRD_V1.1.md、architecture.md | 原始累积文档 | 原样快照在 archive；根文件保留兼容链接，新有效规范在 docs/ |
| data/**、release/out/** | 私有资产/诊断/任务/备份/安装包 | 继续忽略；服务器/本地目录不因代码迁移而改名 |

## 4. 必须先拆的依赖

整理前链条：`prepare_room_candidate → diagnose_room_sections.load_inputs → inspect_room_asset → import_rooms → analyze_floorplan`；其中数据库连接是延迟执行，并非引擎必须连库。2026-11-07第1批已将候选入口改为 `prepare_room_candidate → room_source_inputs → room_source_io`，不再导入诊断或后端工具；原 inspect/diagnose 函数名继续兼容导出。断面工具组现只复用app公共输入与analyze_floorplan几何函数；inspect上游检查仍依赖import_rooms/analyze_floorplan，不能据此批量移动这些上游工具。

整理前动画链条：`F8_room_animation → F8_room_demo / F8_prepare_room_asset / F8_room_fire_style`。第3批改为B/D/E直接依赖`F8_room_helpers`，E不再导入D/B入口；D/B旧函数名继续导出。辅助函数实现不变，普通Python业务端不能导入这些bpy模块。

测试既有普通导入，也有 AST 提取和按文件路径读取。候选、断面、导入、静帧、动画及 GPU 测试都要随实际引用回归，不能只替换 import 字符串。

### 打包与双执行环境也是迁移依赖

| 现有约束与证据 | 迁移必须满足的条件 |
| --- | --- |
| build.ps1/.dockerignore已包含tools诊断源码及新版引擎/命名预设 | 打包只复制20份命名引擎Python及3份预设；缺失或配置分叉即失败，安装包/解压导入需测试 |
| Dockerfile启动app.main:app，reload监控app及backend | 保留兼容入口；仅增加新源码监控，不改服务、端口、挂载或生产依赖 |
| 新Blender入口和兼容脚本从自身位置加入安装根，使用包导入 | 普通Python/Blender的导入与帮助替身均检查；不能再单文件上传/tmp |
| render_engine.paths统一列出39份源码/预设，静帧和动画共用 | 覆盖包初始化、路径模块、兼容脚本及新旧配置；缺失/改动拒绝，不给旧任务改签名 |
| run_room_animation.py:151 由 points 路径推导共享锁根，worker会核对同一锁 | 目录整理不得把点位移到另一层缓存而造成多个锁根；本阶段保持数据路径不变，未来改动须显式设计共享锁位置 |

以上是迁移约束；已落地范围按下表标明。新增目录的产物仍只写入私有data/，不能混入源码安装包。

## 5. 已确认的七批迁移

| 批次 | 范围 | 当前状态/回归重点 |
| --- | --- | --- |
| 1 | app内提取OBJ/MTL、坐标与指纹公共函数 | 已完成；输入保护及旧接口 |
| 2 | 三个断面工具迁入tools/diagnostics | 已完成；兼容入口、CLI与安装包 |
| 3 | app内提取B/D/E共用Blender辅助 | 本地实现；UV/材质/坐标、相机、源码指纹、旧接口与打包；未远端渲染 |
| 4 | 新版Room8引擎及配置迁入render_engine/configs | 本地实现；13个app兼容模块、默认R3、worker、打包/镜像上下文与完整指纹已适配；未远端部署/渲染 |
| 5 | Backend API、数据库工具和MinIO适配分组整理 | 本地实现；7份兼容模块、原样SQL、完整打包与API回归；未导入数据或远端部署 |
| 6 | 其余诊断/集成工具逐组迁移 | 待执行；核对引用与历史依据，不直接删除Z轴工具 |
| 7 | 测试/部署目录收尾及稳定性审阅 | 待执行；旧发布入口兼容，全量相关回归后审阅main合并 |

每批结束均回看diff、调用链与对应测试。新源码使用新任务；复现V1从原基线归档恢复，不能把旧任务改签名后续跑。跨目录迁移时立即更新部署引用，不能等第7批才修打包。

每批分独立提交，说明改变的路径、兼容入口、实际测试和回退提交。不把高度算法、Hybrid、网页或数据库导入混入迁移。

## 6. 文档与产物边界

当前新文档是有效入口；原文档和过期配置过程作为历史材料。Git 当前已忽略 /data/ 与 release/out/，但不代表任意目录下的 PNG/BLEND/GLB 都自动忽略。真实产物一律进入上述私有目录；不为此全局忽略所有 PNG，避免屏蔽以后合法的合成测试图。

下一次提交前看 diff 与新增文件清单，只提交源码/测试/公共配置/脱敏文档。文件移动需用户审阅处置清单后实施，本次没有任何待自动删除的文件。

## 7. 本次工程审阅结论

2026-11-07：目录职责划分可作为目标规范；修正了 F6 分类和“部署最后迁移”的歧义，补齐打包、双执行环境、源码指纹与共享锁约束。**目标结构可保留，当前尚不具备直接批量移动文件的条件。**

第1批已在app内提取room_source_io与room_source_inputs，保留旧函数名，新增两份测试。2026-11-09第2批将diagnose_room_sections、room_section_geometry、room_section_plots实现迁至tools/diagnostics；app保留共享模块对象的兼容入口，打包和镜像上下文只增加这组Python源码。既有高度、裁切与F8动画算法不动；安装包内容/解压导入、旧CLI和相关离线回归分别检查。服务器尚未部署本次迁移。

第4批已按用户授权迁移13个新版实现，保留全部app兼容入口；旧F8-C和Backend未移动。默认预设及完整源码清单按安装根寻址，打包/镜像上下文同批适配。205项相关离线回归中204通过、1项可选绘图库测试跳过；实际GPU未重渲染。剩余第5–7批仍逐批实施，不因本批完成而批量移动其他代码。

第5批已迁移7个Backend实现，保留app入口和原SQL副本；15份后端Python及1份SQL纳入打包，SQL内容不变，增加缺失/副本不一致阻断。ASGI入口仍app.main:app，仅增加backend热重载路径。251项相关回归249通过、2项跳过，真实数据库/远端部署未执行。Room8引擎及其源码指纹完全不改。剩余第6–7批继续分批审核，不删除Z轴工具或混入新网页功能。
