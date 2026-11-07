# 系统架构文档：火灾场景时序演变视频生成系统

> 版本：V2.0（现状架构如实化 + 版本路线图映射）
> 依据：[PRD_V1.1.md](PRD_V1.1.md)（V2.0 版本化路线图）
> 状态：已评审

---

## 1. 架构目标与硬约束

| 目标 | 说明 |
|---|---|
| 链接交付 | 输入 sceneCode → 全流程自动完成 → 浏览器打开公开链接看片（V6.0 验收） |
| 远程 GPU 渲染 | 生产环境为远程 Ubuntu 服务器（172.25.76.201，4×NVIDIA L20） |
| 可观测 | 生命周期事件 + GPU 指标全程落盘，为观测网页/大屏提供数据源 |
| 可增量演进 | V6.0-V9.0 逐版本点亮组件，不要求一次性完成 |

**硬约束**：

1. bpy 与后端**不同进程**：禁止在 FastAPI/业务代码中 import bpy，Blender 通过 `subprocess` 独立子进程调用；
2. 2026-10-30 确认调整：PostgreSQL 管理房间/点位/文件关系；运行状态仍以 JSON 为准，数据库任务状态仅查询摘要；不引入 Redis/MySQL；
3. 数据 I/O：输入资产与输出视频走 S3 SDK + MinIO（本地 data/ 为开发通道）；
4. 生产数据强制挂载服务器独立数据盘 `/data/zhaojy/burnroom-data/`。

---

## 2. 现状架构（已实现，V5 里程碑）

```
┌────────────────────────── 远程服务器 (Ubuntu, 4×L20) ──────────────────────────┐
│                                                                                │
│  docker compose (burnroom-deploy-package)                                      │
│   ┌─────────────────────────────┐        ┌──────────────────────┐             │
│   │ app-server (胖单体镜像)      │        │ minio-oss            │             │
│   │  FastAPI (8000)             │  S3    │  (9000 API/9001 控制台)│             │
│   │  OpenCV (F6)                │ ─────> │  burnroom-assets      │             │
│   │  Blender 4.2 (F8 子进程)    │        │  burnroom-outputs     │             │
│   │  GPU 采样/守护线程          │        └──────────┬───────────┘             │
│   └───────────┬─────────────────┘                   │持久化                     │
│               │ /app/data (挂载)                     ▼                           │
│   ┌───────────▼─────────────────────────────┐  /data/zhaojy/burnroom-data/minio │
│   │ /data/zhaojy/burnroom-data/app-data     │   (服务器独立数据盘)               │
│   │  {scene_code}/: 资产+timeline+output.mp4│                                   │
│   │  logs/: render.log, lifecycle.jsonl,    │                                   │
│   │         failure.log                     │                                   │
│   │  metrics/: gpu_metrics.jsonl            │                                   │
│   └─────────────────────────────────────────┘                                   │
└────────────────────────────────────────────────────────────────────────────────┘
        ▲ 本地开发: Windows + Docker Desktop (无 GPU, 软渲染兜底)
        ▲ 部署通道: build.ps1 打包 → deploy.ps1 SCP → 服务器解压 → compose up
```

### 2.1 模块清单

| 模块 | 职责 |
|---|---|
| `app/main.py` | API 层：场景下载 / `POST generate_timeline` / `POST render`（Popen 拉起 Blender + 守护线程收敛状态）/ status 查询 |
| `app/F6_detect.py` | 起火点识别（OpenCV 烧黑像素占比） |
| `app/F7_spread.py` | 蔓延时序（visibles 拓扑 BFS → timeline.json） |
| `app/F8_blender_render.py` | Blender 子进程脚本（单房间过滤/体积火焰/焦黑化/动态运镜/贴图兜底） |
| `app/s3_io.py` | MinIO 数据流转（资产拉取/产物上传/桶管理） |
| `app/observability.py` | 生命周期事件流、GPU 指标采样（nvidia-smi→jsonl）、失败追踪、状态快照 |
| `release/` | 生产 compose、prod.env 模板、build.ps1 / deploy.ps1 |

### 2.2 可观测文件规范（`/app/data/{scene_code}/`）

| 文件 | 内容 | 消费者 |
|---|---|---|
| `render.log` | Blender 原始输出 + 逐帧进度 | 人工/WinSCP |
| `logs/render.log` | 生命周期文本日志 | 人工 |
| `logs/lifecycle.jsonl` | 结构化事件流（prepare/process/verify/upload） | V7.0 观测网页 |
| `logs/failure.log` | 失败摘要 + 日志尾部 | 排障 |
| `metrics/gpu_metrics.jsonl` | GPU 利用率/显存/温度（5 秒采样） | V7.0 观测网页折线图、V6.0 温度告警 |
| `render_status.json` | 任务状态快照（running/done/failed + pid + 产物） | API/守护线程 |

### 2.3 关键机制

- **渲染异步模型**：POST 立即返回 → Popen 子进程 → 守护线程（等待退出→验证产物→上传 MinIO→收敛状态）+ GPU 采样线程；status 接口按 `/proc/{pid}` 存活兜底
- **幂等与覆盖**：运行中重复触发返回当前状态；渲染前强制删除旧 output.mp4，防误判旧片
- **GPU 策略**：compose `gpus: all`（当前暴露全部 4 卡；未来按需收敛到单卡）；容器内 nvidia-utils-535 提供 nvidia-smi；无 GPU 环境自动跳过指标采样
- **镜像构建（服务器侧已知方案）**：Docker Hub 被墙 → 基础镜像经 1panel 代理拉取打本地标签；download.blender.org 403 → 从旧镜像 `docker cp` 提取 Blender 或更换国内源
- **部署流水线**：本地 `build.ps1`（打包代码+compose+模板，剔除敏感文件）→ `deploy.ps1`（SCP 7777 → 解压）→ 服务器 `docker build -t burnroom-app:latest . && docker compose up -d --force-recreate`

---

## 3. 目标架构（PRD V9.0 对齐）

```
用户浏览器 ──> frontend (nginx, 单入口) ──/api──> backend (FastAPI)
                                                    │ 作业文件队列 (jobs/<jobId>/)
                                                    ▼
                                              engine (Blender 子进程渲染)
                                                    │
                                              MinIO (资产/产物/公开链接)
```

| 演进项 | 现状基础 | V9.0 目标 |
|---|---|---|
| 前端 | 无（Swagger + WinSCP） | Vue SPA（F1-F4 全量） |
| 任务体系 | 单场景状态文件 | jobId + 历史 + 排队（V9.0） |
| 作业协议 | 直调 subprocess | 文件队列 jobs/<jobId>/（可重放、可断点） |
| 产物交付 | 数据盘 + MinIO 桶 | **公开只读策略 + 分享链接**（V6.0 先行） |
| 观测 | jsonl 落盘 | 观测网页（V7.0 先行）+ 前端集成（V9.0） |

**演进原则**：渲染运行状态继续文件化，PostgreSQL 接管房间业务关系；Blender 子进程隔离保持不变。数据库不可用不影响旧渲染/分享接口，新房间查询返回可诊断的 503。

### 3.1 PostgreSQL 房间目录（V2.3）

新增内部 postgres 服务及八张核心表，详见 PRD 2.1 与 `docs/database.md`。户型版本绑定源数据指纹；点位归属同时保留算法结果和人工结果。文件实际留在 MinIO/工作目录，库中只记路径与关联；渲染任务通过配置 JSON 向引擎交付。本轮不自动迁移旧任务状态，不更改 F6/F7/F8。

部署前 prepare_deploy.sh 拒绝 running 任务并备份当前代码/配置、镜像标签与成片；镜像由 .dockerignore 默认拒绝非源码文件。旧下载只接收场景根目录文件，不展开 catalog/history。app/check_catalog.py 使用实际应用账号只读校验权限及导入数量，配合应用账号导入验证；远端部署和恢复步骤见 docs/database.md。app 功能变更需新增追溯 PRD/架构的测试，见 test/README.md。

---

### 3.2 独立房间资产准备与诊断
2026-11-03 第三轮：room_fire_round3.json只调整背景/曝光、两盏现有补光和烟薄层散射色；火焰配置、烟柱网格/曲线、事件、相机、质量保持第二轮值。revision>=2共享已认可的分层火体和烟柱实现，避免新增revision误走旧球烟。面光配置可选volume_factor/target_offset，默认兼容旧配置；纯配置层校验倍率/偏移，Blender层实际赋值并记录位置、目标、旋转和回读体积倍率，不新增渲染入口或灯对象数量。默认第三轮，显式配置仍可复现前两轮；style_round3独立保存六图、配置、有效参数及逐图耗时，基本保护与静帧门禁不变。世界节点主要改善可见背景，室内提亮由现有面光承担，不宣称新增GI。对应PRD2.2、test/test_room_fire_round3.py、docs/room_style_round3.md；真实烟可见性/过曝程度和耗时需远端审核。

2026-11-03 第二轮静帧：沿用F8-D及两个辅助模块，不新增引擎入口。room_fire_round2.json通过art.revision=2选择新分支，第一轮JSON未改；输出按已校验revision隔离style_round1/2。保持accepted火舌几何算法与发光路径，放大名义尺寸并新增独立FlameDensityLayers/FlameBodyNoise径向主体密度，不把密度变化耦合到Emission。smoke_state/plume_mesh为纯stdlib：固定火源附近窄底、不规则卷曲扩散上体、独立浓度/成长和向上纹理平移；R2不调用球体烟分支。深色Principled散射叠加无发光VolumeAbsorption，面光/点光显式设置并回读Blender4.2的volume_factor，以降低烟雾被照成浅灰的风险，实际仍需看图。

effective_settings包含回读材质密度层、吸收比、噪声保底、光照系数及生成尺寸；sample_manifest每图回读灯功率/体积系数、密度/发光包络、烟柱变换与世界Z包围盒，并记录耗时。请求系数与逐帧实际值分开；不声称静帧已验证运动连续性。体积对象仍每点2个、总26个，采样/分辨率不增，但覆盖范围增大会增加逐像素体积工作量，耗时须实测。13点BFS、展示几何、基础资产保护和仅静帧门禁保持。操作见docs/room_style_round2.md，新增测试test/test_room_fire_round2.py追溯PRD2.2/本节；禁止以替身节点测试冒充Blender远端验收。

2026-11-03 第一轮风格优化：F8-D保留既有资产只读加载及展示截断方式，不改基础房间/点位归属；CLI只允许inspect/samples，删除当前入口的动画执行分支。room_fire_round1.json按art/events/quality分组，room_fire_config.py仅stdlib，生成固定种子的曲线火舌闭合网格；F8_room_fire_style.py仅供Blender内部导入，负责独立密度/发光节点、四层颜色、向上噪声、多舌合并对象、独立持续烟与实际设置回读。多舌体积用ACCURATE交界模式及显式深度预算，避免重叠内表面沿用FAST假定；烟为单一闭合球体。保留13点子图BFS，禁止改1.5秒间隔和32/42排除策略。配置及Blender属性读回失败会在出图前中止；每张图记录运行态镜头/灯光/密度与发光控制值和耗时。style_round1独立输出请求配置、生效设置、6图、指纹和派生blend；不覆盖旧display_versions、不进入数据库或旧视频入口。远端API/视觉/耗时仍需按docs/room_style_round1.md验收，离线替身测试不能代表成片通过。

当前既有资产展示修正入口为 F8-D app/F8_room_demo.py，复用 F8-B 的 UV 保留网格构建和仅 Z 展示截断；读取并核对 room.blend/GLB/既有检查产物指纹，不重做 XY 裁切。输出为该资产同级独立 display_versions/{UTC_UUID}。app/room_demo_plan.py 提供无 bpy 的合并位置连接分量、显式隐藏列表、内部点诱导子图 BFS 和多级强度曲线；分量小不等于无用。灰色排查用有限射线命中/背面和材质节点证据，默认不替换源贴图；原模型无新封盖面。inspect 输出修正版视图，samples/short 在展示接受后写独立 room_timeline.json 和预览产物；--points 显式指定并校验源点位指纹，旧时序/视频不写。火源位置可在展示表面上做可见性贴合，参考地板及原点位坐标保持并记录。详见 docs/room_display.md 与两份新增测试。

**2026-11-02 当前实施策略**：Room8 使用显式接受的平层近似（主导下包络参考 `floor_z=-1.35m`），不再等待物理地板/顶部/墙厚精确语义。旧诊断和人工核验只读保留。新候选的 ready_for_cut 表示工程演示允许试裁切，physical_semantics_verified 始终为 false；火灾效果接入仍须独立资产重载检查及人工画面验收，不伪造旧报告通过。

脚本标记：F8-A 原模型导入检查，F8-B 独立房间与三视图（当前入口），F8-C 旧完整视频（未接入新资产）。索引见 app/README.md，不改文件名和旧 API 绑定。F8-B 将选定点位保存为 Empty，重载后核对原始相机 XYZ、归属、独立火源参考 Z 和坐标来源元数据；manifest 记录来源文件指纹和裁切多边形/缓冲/面数。基础 blend 重载通过与人工画面验收分开；GLB 当前只做自包含结构检查，不声称已完成 GLB 重载验收。

app/room_clip_geometry.py 使用凹多边形耳切分解与逐三角面半平面裁切，保留 XYZ 和逐角 UV 的线性插值及源材质/面编号；零外扩，无全局高度截断，允许开放切口，不声称水密或完整墙厚。app/prepare_room_candidate.py 复用已绑定指纹的核验输入，不连接数据库，输出独立 rooms/{room}/{UTC_UUID}/candidate.json，记录近似依据、坐标映射、内点与门口边界点；原始点位的镜头 Z 不作为火源高度。

Blender 专用 app/F8_prepare_room_asset.py 沿用已验证的 OBJ 导入轴向读取材质，重建候选网格、打包贴图、另加演示地板，保存 room.blend 后重新打开，对几何/UV/材质索引/变换和贴图检查，再导出自包含 room.glb。blend 保留原始 XYZ；GLB 标准 Y-up 映射记入 manifest。基础房间不去顶；派生展示几何在人工展示高度剖切，保存 section_preview.blend 和三张 PNG，manifest/validation 保留 visual_review_required=true、ready_for_fire_effects=false。输出不使用旧 output.mp4 或 render_status.json；失败输出 failure.json，保留现场，不覆盖重跑。远端执行与验收见 docs/room_candidate.md。

以下保留前阶段诊断设计；其“仅诊断、等待完整物理语义”的阶段限制不再阻止上述候选资产流程：


原始 OBJ/MTL/贴图保持只读；户型坐标经逆变换进入原始 OBJ XY 后检查房间几何。高度先作射线交点上下包络采样，不将其自动解释为物理地板/天花板。诊断目录与正式 rooms/{room}/{version} 资产目录分离，矩阵与逆矩阵随资产保存；本轮只输出 diagnostics，不产生裁切产物。

app/inspect_room_asset.py 是无 bpy/数据库依赖的离线检查；app/F8_inspect_room_import.py 与 F8 一样仅由 Blender 自带 Python 独立子进程执行，业务模块不 import 它。远端检查采用与现有 F8 相同的 OBJ 导入轴向，比对世界坐标、面数、UV、材质、图片和输入文件哈希。核验、裁切、独立保存/重新加载、展示剖面、火灾效果按顺序推进，基础模型和剖面派生分开。

app/diagnose_room_sections.py 绑定通过的导入报告与本地检查 SHA256，使用 app/room_section_geometry.py 做三角面/平面求交、网格采样连通性和逐边平行表面探测。app/room_section_plots.py 用可选 Matplotlib Agg 输出诊断 PNG 和本地索引，不调用 Blender 渲染。requirements-diagnostics.txt 与生产 requirements.txt 分离，现有 F8/数据库接口不依赖该绘图库。诊断前后校验源文件和历史视频指纹，输出目录独立；报告保留未确认参数及门禁，不自动修正坐标、墙边或高度。

### 3.3 A阶段独立动画任务（2026-11-04）

2026-11-05最新对比验证：同一镜像通过显式NVIDIA runtime及环境变量、不传--gpus时能加载图形库。采用该路径，生产模板不再声明gpus；GPU覆盖文件声明gpus: !reset []，避免旧生产基础文件的gpus: all经Compose合并继续生效。保留NVIDIA_VISIBLE_DEVICES=all及graphics能力；DeviceRequests应为空。配置合并语法由远端config --quiet检查，不以文本测试代替实际Compose校验。无需更新镜像、驱动或Docker daemon；真实EEVEE上下文仍由正式帧守卫确认。

2026-11-05：宿主机图形库就绪后仍未注入，检查发现app-server实际Runtime=runc，已注册nvidia运行时及Toolkit1.20.0。生产/覆盖compose显式指定app-server.runtime: nvidia，保持graphics能力及gpus请求，避免依赖全局默认运行时；不修改Docker daemon或其他容器。容器重建后核验Runtime、EGL/GLX可加载和vendor JSON，真实GPU仍由正式首帧守卫判断。

**NVIDIA图形能力修正**：release/docker-compose.prod.yml显式请求compute,utility,graphics；临时远端修复使用release/docker-compose.gpu.yml叠加现有生产compose，只重建app-server容器、不重建镜像，保留所有既有生产env/卷。NVIDIA驱动库由容器运行时从宿主机挂载，不在容器内另装显卡驱动。require_nvidia_graphics写入所有final任务契约；第一帧后、发布PNG前校验gpu.platform实际renderer/vendor/device_type，拒绝软件/未知/非NVIDIA；保存attempts/<attempt>/renderer.json及manifest.renderer供失败排查。正式编码前再次核验worker_timing中的实际渲染器；全部帧复用的续跑读取同任务既有renderer证据，无证据则拒绝。旧CPU任务与新GPU任务分目录，不续跑代码/契约不同的旧任务；火烟/灯光/机位参数不变。test_room_gpu_rendering.py验证驱动配置、真实worker守卫分支与软件拒绝，不等于实机GPU验证。

**正式出片策略更新（2026-11-04，用户明确授权，优先于下述旧短片门禁）**：`--stage final --preset final --camera-mode overview --direct-final` 直接生成24秒、1280×720、24fps、576帧；不要求新短片审核文件、GPU性能排查或耗时预估。授权模式写入配置快照与manifest并纳入续跑一致性检查；未指定直接出片选项时仍保留原审核路径。第三轮风格指纹、13点BFS和独立总览相机不变；本模式只渲染576个总览视频帧，不追加近景样帧。启动排他锁和已有任务检查、温度保护、逐帧记录、输入指纹保护、失败保留及续跑保持生效。编码后先由ffprobe核对576帧/720p/24fps/24秒，再完整解码通过才发布fire_final.mp4和video_receipt.json；耗时报告仅记录实测。完成状态awaiting_visual_review表示技术交付完成、待人工播放查看，不会再自动启动任务。新增test_room_animation_final.py对应这些行为；远端操作见docs/room_animation_final.md。

相机回归修复：F8-D camera()为当前相机修改器，F8-E不能把它两次返回值当成两个相机。现在通过independent_camera先清空scene.camera再调用原helper，创建独立对象、data、TRACK_TO target；派生场景marker camera解绑，原资产不保存。activate_camera在每次绝对时间seek后选机位并检查独立性/类型，渲染后记录实际相机，编码前核对有效帧相机；camera_mode显式进入快照、manifest、审批绑定。总览位置/目标沿用R3，fit_overview利用实际view_frame画幅/投影检查房间及峰值火焰覆盖，只增大尺度不动模型/位置/目标；两机位不再相互覆盖。

新增camera_check stage，CLI默认该档：一张3.5秒动画总览，不进入编码或短片审批模板。camera_reference绑定原R3样帧/配置/基础资产SHA，源文件纳入只读guards，比较图和并排HTML在独立新任务输出，位姿/类型偏离原参考报错；正交尺度若为覆盖检查放大则明确记录并等待人工构图验收。旧错误任务的video/timing_manifest保留，不续跑旧错误帧；historical_summary和--report-job只读提取，标出标签overview/实际PERSP不符，不把旧CPU近景耗时视为总览或L20性能。用户报告显示llvmpipe/SOFTWARE，本轮不更改GPU后端。新增test_room_animation_camera.py追溯PRD2.3，含真实旧camera helper的别名复现与修复回归、投影余量、参考指纹、一帧无编码流程及报告只读；离线测试不代表远端新构图已通过。当前操作以docs/room_animation_camera_fix.md为准。

run_room_animation.py（普通Python，无bpy/DB）→Linux内核排他锁/已有进程检查→F8_room_animation.py（Blender专用F8-E）→PNG→独立FFmpeg编码/ffprobe核验→等待人工审核。room_animation_job.py为纯stdlib文件契约、冻结指纹、绝对时间状态、输出约束/统计/推算与审批门禁；不引入后端任务队列或数据库。复用F8-D的mesh_faces/camera/closest_hit与F8-B的below/make_mesh，当前展示截断不变；复用现有F8_room_fire_style的configure_render/lighting/add_fire，只给既有流动节点增加稳定名称EffectFlow，无艺术参数改动。F8-D静帧执行分支不改。

任务根为基础资产版本的上一级Room8/render_jobs，独立UTC_UUID。配置快照及输入/脚本哈希绑定工作；检查原资产/历史视频/原timeline不变。Blender逐帧scene.frame_set后，用绝对时间公式重新赋值火焰包络/闪烁/变换、烟成长/密度、点光及4D噪声W/坐标，避免依赖前一帧/模拟缓存。沿用第三轮总览和近景机位，短片固定总览，近景仅用于验收；不实现Hybrid或火烟墙面遮罩。GPU粒度保守为所有可见卡串行，锁描述符继承到worker；旧API与外部非协作任务不能被此锁控制，启动前探测并要求本阶段不同时手动开任务。监控可用时85/90°C告警/终止，数据不可用保留原因。

frame_NNNNNN.png只在校验后从本次attempt暂存目录转入frames，每完成一项原子更新manifest。续跑校验固定快照、代码、输入和PNG哈希；异常文件不删除不替换。每次attempt有独立blender.log/encode.log/failure日志和计时；根status/timing_report为最新尝试视图，历史尝试保留。确认48视频帧及9额外渲染/2复制参考图齐全后，FFmpeg以-n写本次暂存MP4，ffprobe确认4秒48帧H.264/RGB转换yuv420p/faststart，再发布本任务视频及回执。失败保留所有已产出文件，不覆盖历史任务。

报告覆盖启动/加载/初始化、逐帧/阶段统计、额外检查、编码/验证、GPU显存利用率和本次总耗时；续跑复用帧的原始计时与本次墙钟时间区分。全片24秒，依据3+20+1生命周期；正式720p24fps576帧的耗时只做启发式估算，直到远端全片实测前不得声称达标。短片结束仅awaiting_visual_review，审批文件需明确允许preset，所有人工核验项为true，并校验绑定配置/输入/代码/机位、报告/视频和帧证据。没有从short自动跳final的分支。详见PRD2.3、docs/room_animation.md、test/test_room_animation.py；本地替身测试不是Linux锁/Blender/FFmpeg实机或视觉验收。

## 4. 版本路线图与架构组件映射

| 版本 | 架构动作 | 涉及模块 |
|---|---|---|
| **V6.0** 链接交付 | MinIO 公开策略+分享链接接口；流水线编排接口；下载缓存去重；`--quality` 参数；GPU 温度告警 | main.py / s3_io.py / observability.py / F8 |
| **V7.0** 渲染攻坚+观测 | 观测网页（读 jsonl）；房间级评分分档数据层；F8 物理拟真/材质语义；断点续渲（PNG 序列）；自动验收指标 | 新：静态观测页 + 验收模块；F6/F8 升级 |
| **V8.0** 全屋+运镜+容错 | 门窗通风口检测（网格开口分析）；智能运镜算法；手动起火点接口；公告板降级预案；水印 | F7/F8/main.py |
| **V9.0** 产品化 | 前端 SPA + job 文件队列 + jobId 体系；Epic 1 多室算法 | 新：frontend/ + 队列模块 |

---

## 5. 架构决策记录（ADR 汇总）

| # | 决策 | 理由 |
|---|---|---|
| 1 | **单体胖容器**（FastAPI+OpenCV+Blender 同容器） | MVP 交付最快；服务器单机部署场景下拆容器收益低；V9.0 前端化时再评估 engine 独立 |
| 2 | 任务状态以文件为真相源（JSON/挂载盘） | 无数据库依赖、崩溃可恢复、WinSCP 可直查 |
| 3 | Blender 经 subprocess 子进程调用 | bpy 与后端 Python 强绑定，进程隔离唯一可靠方案 |
| 4 | GPU 直通 + 软渲染兜底 | 服务器 4×L20 用 `gpus: all`；无 GPU 环境自动降级不报错 |
| 5 | 数据盘挂载 + MinIO 双通道 | 本地文件满足渲染 I/O；MinIO 满足交付与无状态约束 |
| 6 | 可观测性三文件规范（lifecycle/gpu/failure） | 为 V7.0 观测网页与未来大屏预留结构化数据源 |
| 7 | 部署流水线 build.ps1/deploy.ps1 | 国内网络环境下手动 SCP 最可控；敏感文件只留服务器 |

---

## 6. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 端口未放行（9000/9001）导致公开链接不可访问 | **高** | V6.0 前置：找管理员放行；兜底走 SSH 隧道 |
| 体积特效渲染性能/超时 | 中 | V8.0 公告板降级预案；`--quality preview` 快速验证 |
| GPU 过热宕机（历史事件） | 中 | V6.0 温度告警守护（metrics 已具备） |
| Docker Hub/Blender 下载被墙 | 中 | 1panel 代理拉取 + 旧镜像提取 Blender（已形成标准方案，见 2.3） |
| 户型数据缺失（无 room 字段） | 中 | V7.0 先验证 getSceneViewUserFile；缺失时评分分档+拓扑聚类自建房间 |
| 渲染中断丢失进度 | 中 | V7.0 断点续渲（PNG 帧序列） |

---

## 7. 演进路径（Backlog 预留）

| 演进项 | 架构预留 |
|---|---|
| FDS MCP 代理（Epic 2） | engine 层新增数据输入通道，timeline.json 可被物理模拟结果替换 |
| 公网 Web（Epic 3） | frontend 独立部署，MinIO 公开链接机制直接复用 |
| 云 GPU 迁移 | engine 子进程协议不变，容器整体可迁 |
| 多任务并发 | 状态机文件化天然支持 N 任务并行（V9.0 队列化后解锁） |
