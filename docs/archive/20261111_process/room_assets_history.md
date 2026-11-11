# room_assets_history.md

2026-11-11合并的历史原文。来源提交：`fd3b3724a6526040f09dee8dd5eab57e64e33af3`。以下旧命令、路径、门禁和“当前状态”仅用于追溯，不作为运行指令。当前说明从[文档索引](../../README.md)进入。原文以Markdown源码保存，换行统一为LF；manifest.json记录原路径、工作副本SHA、Git blob及合并后字节范围，可提取校验。

<details>
<summary>docs/room_asset_checks.md</summary>

````markdown
# 独立房间资产：第1、2步核验

> 2026-11-02 更新：本文保留前阶段核验方法与结果。Room8 已由用户接受平层地板近似（参考 -1.35m），不再等待完整建筑语义；候选裁切及资产重载按 [当前操作说明](room_candidate.md) 执行。旧报告不改，新的工程放行不等于物理语义确认。

本轮仅检查，不裁切、不渲染、不覆盖原模型、材质、贴图、时序或历史视频。不依赖数据库或 appkey。

## 本地检查

PowerShell 项目根目录，使用本机实际 Python（若 python 启动器异常，换成完整解释器路径）：

```powershell
python -m app.inspect_room_asset --scene KK-EEz16cmU14 --room Room8 --data-root .\data --probe-dir .\data\KK-EEz16cmU14\diagnostics\floorplan\20261027T063858Z_12484e9d --alignment-dir .\data\KK-EEz16cmU14\diagnostics\alignment\20261029T032340Z_177df64f --review-file .\data\KK-EEz16cmU14\diagnostics\alignment\20261029T032340Z_177df64f\review.json
```

输出位于 data/{scene}/diagnostics/room_inspection/{时间}/inspection.json。程序拒绝源指纹变化、未确认 XY、无效房间、外部材质路径；材质/贴图缺失及不支持的 MTL 选项会标记，不静默贴图兜底。无 UV/材质/贴图的合成测试不代表真实资产验收成功。

## 核验解释

- 原始坐标单位米，当前 XY 为直接对应。原始模型包围盒约 X[-6.190736,6.181091]、Y[-4.503821,3.708122]、Z[-1.663760,2.211620]。
- 现 F8 全屋居中平移约 (+0.004822,+0.397850,-0.273930)，仅在实际导入坐标匹配原始 OBJ 时成立；新基础资产不能盲目沿用全屋居中偏移。
- 通用策略是先将房间边界逆变换回 OBJ 原始 XY，在原始坐标检查/裁切；资产可保留原坐标，或选择房间局部参考原点，同时保存前后变换。局部原点不等于相机目标，尤其不能将凹多边形包围盒中心自动当内部点。Z 暂不归零。
- 竖直交点采样记录几何最下/最上表面，是包络而非物理地板/天花板；家具、板厚、台阶及模型缺口可能影响结果。报告中的 floor_z_confirmed/ceiling_z_confirmed 保持 null，ready_for_cut=false，需断面核查后再推进。
- 该样例户型边界点只有 XY 与楼层标号，没有可确认地板/天花板 Z 的字段；标签中的 sideThickness 不用作墙体厚度。相机22号的原始 Z 约 -0.094068m，是拍摄点高度，不是地板或火源落地点；后续火源落地需基于确认后的表面处理。
- 当前 Room8 原始边界有11顶点；初次0.25m采样487点，下包络集中约 -1.35/-0.85/-1.15m，上包络集中约1.80/1.65/2.20m。存在多组高度，不能认定统一层高，不把原模型 Z 极值拿来切屋顶。
- 原始材质 chunk001_group000_sub000，map_Ka/map_Kd 指向 texture1.jpg；当前9204面、27612个面角均有 UV，原 OBJ 没有显式 vn。后续裁切需插值新增面角 UV、保留面材质并正确处理法线；基础资产必须携带实际贴图，不能只保存网格。
- 墙体策略：基础资产保留房间内侧墙、门口和顶面；共墙厚度/边界缓冲需先测量，不能固定外扩2.5m或直接删掉挡镜头的面。剖面为后续独立派生，不改基础几何；本轮不擅自确认数值墙厚。

## 远端 Blender 导入核验（只读诊断）

本地脚本及报告通过 /tmp 上传，暂时避开 app-data 下用户写权限问题。脚本仍在本地维护；无需重建/重启后端。以下把“实际检查目录”替换为本地输出的完整目录：

本地 PowerShell：

```text
scp -P 7777 .\tools\diagnostics\blender\F8_inspect_room_import.py zhaojy@172.25.76.201:/tmp/burnroom_room_import_check.py
scp -P 7777 .\data\KK-EEz16cmU14\diagnostics\room_inspection\实际检查目录\inspection.json zhaojy@172.25.76.201:/tmp/burnroom_room_inspection.json
```

远程 SSH，部署目录：

```bash
cd ~/burnroom-prod/burnroom-deploy-package
docker compose cp /tmp/burnroom_room_import_check.py app-server:/tmp/burnroom_room_import_check.py
docker compose cp /tmp/burnroom_room_inspection.json app-server:/tmp/burnroom_room_inspection.json
docker compose exec -T app-server blender --background --factory-startup --python-exit-code 1 --python /tmp/burnroom_room_import_check.py -- --report /tmp/burnroom_room_inspection.json
```

factory-startup 只作用于这个新 Blender 进程。脚本只导入原始 OBJ，读取 UV/材质/图片；不调用 render、不写 blend、不改源资产。检查原模型/MTL/贴图/点位/时序与本地指纹相符，比对导入后的世界坐标和抽样 UV，并验证历史文件前后哈希一致。浮点几何比较容差2e-5m，UV比较容差2e-5；采样比较不能替代后续完整裁切资产重新加载检查。

输出 diagnostics/room_blender_inspection/{时间}/blender_import.json，并打印 [room-import-check]。预期 status=passed、所有 checks=true，同时显示实际 Blender 版本。即使通过也只证明导入阶段，ready_for_cut 仍为 false；地板/天花板和墙厚未确认前不进入第3步。

## 后续门禁

第3步裁切前须完成：远端导入比对、地板/天花板断面核查、墙厚/边界处理确认。第4步必须先独立保存 room.blend/room.glb 及来源/变换/核验清单，并重新加载验证；第5步再派生剖面，第6步接入火灾效果。原完整模型与历史视频全程保留。

````

</details>

<details>
<summary>docs/room_section_diagnostics.md</summary>

````markdown
# 房间几何断面诊断（只读）

> 2026-11-09 路径整理：实现位于tools/diagnostics，推荐入口为 `python -m tools.diagnostics.diagnose_room_sections`；旧 `python -m app.diagnose_room_sections` 保留兼容。算法、参数、输出目录和物理语义门禁不变。本轮仅迁移，不需重新生成既有诊断图。

> 2026-11-02 更新：本诊断工具仍保持只读，不改历史结论。Room8 后续采用用户接受的平层地板近似（参考 -1.35m），不再将真实物理地板/吊顶/墙厚完全确认作为候选裁切前置条件；后续操作见 [独立候选资产](room_candidate.md)。

对应 PRD 2.2、architecture 3.2。此工具仅生成独立诊断图片/报告，不修改 F8、不裁切/保存网格、不调用视频渲染、不连接 PostgreSQL。

## 输入与坐标

- 已有 inspection.json：已核验多边形、原始 OBJ 坐标下边界、487个高度样本及源文件哈希。
- 远端 Blender 导入报告：检查必须通过，场景/房间/OBJ SHA256 和 inspection SHA256 均匹配；接受原 JSON 或带 result 字段的旁证包装。
- alignment_report.json 与 review.json：复核来源及二维坐标转换一致。
- 原始 OBJ/MTL/贴图、points、timeline 及已有 output.mp4：读取并记录哈希，结束再次校验；绝不覆盖。

本次远端通过结果来自用户贴回的终端输出，已在私有 data/ 保存 remote_import_user_output.json，并明确标注来源和远端原报告位置。尚未下载远端原 JSON，不把旁证文件伪装成原文件。用户可通过 WinSCP 下载原 blender_import.json，替换 --blender-report 参数；匹配检查不变。

采用已验证的原始 OBJ 世界坐标，不再次归一化或调整 Z。房间由输入中的 room_id 选择，不写死 Room8。所有输出位于 data/{scene}/diagnostics/room_sections/{UTC时间_UUID}/，不依赖真实数据入库或 appkey。

## 本地 PowerShell 操作

已生成的图片直接打开 index.html 即可，无需安装依赖或部署。需要重新计算时，在项目目录创建独立 Python 环境（python 启动器不可用时换成本机实际解释器路径）：

```powershell
python -m venv .venv-diagnostics
.\.venv-diagnostics\Scripts\python.exe -m pip install -r requirements-diagnostics.txt
.\.venv-diagnostics\Scripts\python.exe -m tools.diagnostics.diagnose_room_sections --data-root .\data --inspection .\data\KK-EEz16cmU14\diagnostics\room_inspection\20261031T033807Z_79b97ce7\inspection.json --blender-report .\data\KK-EEz16cmU14\diagnostics\room_inspection\20261031T033807Z_79b97ce7\remote_import_user_output.json --alignment-dir .\data\KK-EEz16cmU14\diagnostics\alignment\20261029T032340Z_177df64f
```

requirements-diagnostics.txt 是可选绘图依赖，不改变生产镜像依赖。没有本地 Docker/服务启动。输入变化会拒绝执行，需重新核验，不能修改报告哈希绕过。

新版发布包同时携带app兼容文件和tools/diagnostics的Python源码，镜像构建只放行该工具组，不包含其他tools数据。旧服务器容器在更新前仍使用原脚本，不会因本地迁移自动变化；如以后部署本批代码，应整体打包，不能只SCP一个app兼容文件。本文命令在项目根执行；未安装可选绘图库的容器仍不能生成PNG。

## 输出和读图

| 文件 | 内容 |
|---|---|
| index.html | 中文说明及图片入口；只链接同目录文件，不联网 |
| 01_sampling_plan.png | 原始 XY、多边形、相机、内部/起火点断面和近墙采样位置 |
| 02_height_envelopes.png | 每个采样点的上下几何包络；顶部红叉是缺少第二个表面，不表示模型被删 |
| 03_surface_continuity.png | 同5cm高度箱、四邻域连通区域，C编号对应 report.json |
| section_*.png | 单独竖直断面，标记原点、方向和原始Z；绿色背景仅代表目标房间区间 |
| 04_sections_overview_*.png | 每页6个断面的汇总；近墙红线为户型边界，正方向朝房间内 |
| 05_boundary_offsets.png | 每边多个高度/沿边位置的最近平行表面偏差；黑叉为未命中，不能直接当门洞 |
| report.json | 交线、原始面ID、采样点、空间区域、方法阈值、墙面偏差/间距及未确认问题 |
| findings.md | 可读统计摘要；高度/墙厚/缓冲保持候选状态 |
| failure.json | 发生生成错误时标记失败；不能把残留图片当已验收结果 |

蓝色为下包络候选，橙色为上包络候选，灰色为近竖直面，紫色为内部水平面候选（可能家具/平台），黄色为斜面，浅灰为其他水平面。颜色基于几何方向及附近高度样本，不是识别后的物理标签；断面交线来自原始三角面，不对源网格执行切割。

内部断面使用样本 X/Y 的20%、50%、80%位置，另过起火拍摄点；靠墙断面选每段长度≥0.3m边的中点。短边仍在报告中标明，不强行估计。Room8当前共18断面、25张PNG。图中全部Z为原始值，不假设地板为0。

report.json 的 face_id 为原始 OBJ 面记录从0开始的编号，不保证等于 Blender 导入合并或重排后的 polygon 编号。

## 高度和墙体方法限制

487点原网格用于上下包络和四邻域分区；相邻跳变>15cm、断面台阶和分区高度用于找可疑区域。面积是采样点数×网格间距平方的估计，不是精确实体面积。包络间距不是已确认层高；家具遮挡、模型缺口或屋面/梁会产生歧义。

墙边默认在±0.6m范围探测（可用 --wall-search 调整为0.05..1m），这只是搜索范围，不是裁切外扩。沿边约0.25m取站点，在由几何包络和相机高度选出的4个Z平面检查近竖直面：法线与边界法线偏差≤15°；交点3mm以内合并。记录最近表面偏差及2..50cm间距的平行面候选；不证明两面之间是实心墙。

候选外侧缓冲按最近/配对外表面偏移P95加2cm、向上取5mm整，且至少一半探测命中才报告；不会应用。P95不覆盖全部异常，报告另存最大外偏。逐边标记命中不足75%、偏差P90超过10cm和候选缓冲侵入相邻有效房间。大偏差可能是边界误差、门洞、缺失墙或命中了其他结构，不据此自动移动边界或扩大裁切。

## 当前核验状态

几何分区和交点高度、坐标、文件未变可确认；物理地板、顶部语义、墙体厚度及正式裁切缓冲尚未确认。工具始终输出 ready_for_cut=false，不提供自动放行参数。人工明确分区地板/顶部及逐边墙体策略，并绑定本次输入后，再实现独立的批准记录与裁切步骤。完整基础房间资产和后续展示剖面分开，原模型/视频继续保留。

````

</details>

<details>
<summary>docs/room_candidate.md</summary>

````markdown
# 单房间候选资产：当前演示近似策略

2026-11-09第4批：B实现已迁入render_engine/blender，旧app入口需完整引擎包。以后重新生成资产时，先按[迁移说明](room_engine_migration.md)安装并设置`engine_root`；不能再单独上传B/helper。本轮不执行资产生成。

**本次只运行 F8-B：app/F8_prepare_room_asset.py。** F8-A（F8_inspect_room_import.py）是已完成的原模型导入检查；F8-C（F8_blender_render.py）是旧完整视频入口，本轮不运行。各脚本头部已有标记，完整索引见 [app/README.md](../render_engine/README.md)。

2026-11-02 用户确认：Room8 采用平层地板近似，参考地板 -1.35m（主导下包络候选）。不再等待地板、平台、吊顶、墙厚的真实建筑语义确认。旧诊断及 review.json 不改，历史 ready_for_cut=false 不作回填；新 candidate 单独记录工程放行依据，physical_semantics_verified=false。该策略优先于 room_asset_checks.md / room_section_diagnostics.md 的旧物理确认门槛。

裁切用已核验的 11 顶点多边形及其逆变换，严格零外扩。跨边三角面插值 UV，保留原材质和原始 XYZ，不按对象包围盒保留整个全屋。它是开放边界候选，不保证墙厚完整、水密或没有任何纹理中拍到的邻房内容。地板为独立演示对象；扫描模型中更高的平台/家具仍保留，若检查图显示遮挡，再调整展示副本，不能假称已完成平台识别。

## 第一阶段：本地 PowerShell

在 D:\burnroomvideo_byblender，使用可用的 Python（本机 launcher 失效时使用实际 Python313 路径）：

```powershell
& 'C:\Users\86182\AppData\Local\Programs\Python\Python313\python.exe' -m unittest test.test_room_candidate -v
& 'C:\Users\86182\AppData\Local\Programs\Python\Python313\python.exe' -m app.prepare_room_candidate --data-root data --inspection data/KK-EEz16cmU14/diagnostics/room_inspection/20261031T033807Z_79b97ce7/inspection.json --blender-report data/KK-EEz16cmU14/diagnostics/room_inspection/20261031T033807Z_79b97ce7/remote_import_user_output.json --alignment-dir data/KK-EEz16cmU14/diagnostics/alignment/20261029T032340Z_177df64f --floor-z -1.35 --accept-flat-floor
```

此命令只生成候选 JSON，不启动 Blender。证据文件是用户提供终端输出的本地记录，provenance 保留这一来源，不将它冒称远端原始报告。可替换为已下载的原始 blender_import.json，但必须对应当前 inspection 指纹。

控制台会给出独立版本路径。不同房间可复用该工具，需换相应 inspection、导入证据和参考高度；不会自动将 Room8 的高度应用到其他房间。

完整代码包已独立安装后，只另行上传候选数据（把<版本目录>换成此次输出的UTC_UUID，不原样粘贴占位符）。代码使用`engine_root`中的完整引擎，不单独传兼容脚本：

```powershell
scp -P 7777 .\data\KK-EEz16cmU14\rooms\Room8\<版本目录>\candidate.json zhaojy@172.25.76.201:/tmp/burnroom_room_candidate.json
```

本轮临时测试无需重建镜像，也无需在远端编辑代码。原始 OBJ/MTL/贴图及 points/timeline 必须与本地指纹一致；若远端历史视频与候选记录不同，会拒绝并要求核对，不能靠删除视频绕过。

## 第二阶段：远程 SSH

在远端现有部署目录执行，先逐行输入：

```bash
cd ~/burnroom-prod/burnroom-deploy-package
run_id=$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')
room_run="/app/data/KK-EEz16cmU14/rooms/Room8/$run_id"
docker compose exec -T app-server mkdir -p "$room_run"
docker compose cp /tmp/burnroom_room_candidate.json "app-server:$room_run/candidate.json"
docker compose exec -T app-server blender --background --factory-startup --python-exit-code 1 --python "$engine_root/render_engine/blender/F8_prepare_room_asset.py" -- --candidate "$room_run/candidate.json" --data-root /app/data --display-height 2.4
printf 'Result directory: %s/asset\n' "$room_run"
```

这次只生成静态检查图，不生成动画或视频，不访问数据库，不调用旧渲染 API。容器用户创建目录可避免 SSH 用户写 root 属主目录的权限问题；不要 chmod 整个数据盘。若 mkdir/复制失败，停止后续命令先处理错误。变量与执行命令需在同一个 SSH 会话中运行。

默认人工剖切 Z=-1.35+2.4=1.05m，只用于展示去顶，不是测量层高。内部镜头在参考地板以上 1.6m，XY 通过多边形内部离边界较远的采样选择，朝向起火点；TRACK_TO 保持。三视图用来暴露遮挡问题，仍需人工检查穿墙/遮挡，不承诺静态算法已验证视线畅通。

若失败，查看 asset/failure.json 和控制台 Traceback；不要在同一 asset 目录强行重跑。再次执行时新建 run_id，保留失败现场。

## 第三阶段：WinSCP 检查及结果回传

WinSCP 打开远端：`/data/zhaojy/burnroom-data/app-data/KK-EEz16cmU14/rooms/Room8/<run_id>/asset/`，下载到本地 data 下相应独立目录。

| 文件 | 用途/预期 |
|---|---|
| room.blend | 保留原始 XYZ、UV/材质、打包贴图的基础候选；未为看清内部删除顶部和墙体 |
| room.glb | 网页候选资产，图片/缓冲内嵌；标准 Y-up，坐标映射见 manifest |
| validation.json | status=passed，重载快照一致、贴图打包可用、GLB 自包含；point_count=14（13 内部+1 门口），重载点位位置/归属/参考地板及坐标来源元数据一致；不等于人工视觉通过 |
| top.png、oblique.png、interior.png | 俯视、斜视、内部视角；均使用派生剖面几何 |
| section_preview.blend | 带展示去顶、镜头和照明的副本；不能替代 room.blend |
| manifest.json | 来源指纹、近似策略、坐标映射、点位、视角及产物指纹；source_and_history_unchanged=true |
| failure.json | 仅失败时出现；存在时该版本不可接入效果 |

人工检查：客厅范围没有明显混入卧室/厨房；UV 和贴图没有错位；镜头内部可见、不过墙；演示地板/扫描平台不遮挡主要起火区域；基础资产顶部墙体仍保留。Room8 应有 13 个内部点、32 号独立门口点、42 号不纳入；22 号为内部起火点。

基础 blend 内 Point_<编号> 是点位 Empty 标记，不会在 PNG 中画出球体；保存原始相机 XYZ、内部/门口归属及单独的火源参考高度。GLB 导出 extras 保留这些自定义属性。重载检查读取基础 blend 验证这些点位；当前 GLB 仅做文件结构、自包含和贴图存在检查，未做 GLB 重新导入或浏览器视觉验收。

确认图像通过后再进入效果阶段：只在内部子图重新计算蔓延时间，32 号边界策略单列、不向其他房间传播；火源以参考地板定位，先火焰、再烟雾/灯光；独立目录生成样帧、短片、完整视频。20 分钟为性能目标，须按实测准备/逐帧/编码耗时判断。当前代码没有接入旧 F8、没有生成完整视频。

````

</details>

<details>
<summary>docs/room_display.md</summary>

````markdown
# 既有 Room8：最小展示修正与火灾预览

> 第4批后当前app文件均需完整引擎包，不能执行下文平铺上传命令。安装边界见[迁移说明](room_engine_migration.md)；本文为历史记录。

2026-11-09：下方为历史命令，不能作为当前版本上传清单；当前依赖及静帧操作见[第三轮说明](room_style_round3.md)，其中包含共用模块`F8_room_helpers.py`。

> 2026-11-03：本文为上一阶段操作记录。当前第一轮风格优化禁用short和动画，火灾样帧改为中近景/总览六图，请使用 [新操作说明](room_style_round1.md)。不要执行下面旧short命令；新入口会拒绝该模式。

使用 **F8-D：app/F8_room_demo.py**，不再运行 F8-B 资产生成或旧 F8-C 视频 API。不重新对齐户型或裁切房间平面，不连接数据库。已通过的 room.blend/room.glb 和历史视频保留。

## 本次改动与边界

- 只在展示副本将墙顶截至参考地板以上 1.1m（默认 Z=-0.25m），内部镜头抬至参考地板以上 4.5m 向下看；保留 TRACK_TO，不再使用原低机位贴墙视角。
- 三盏大面积柔光与 +0.8 档曝光；双面展示材质使用源材质的副本，保留 UV 和贴图；不把灰色直接当作贴图丢失，不重建灾前材质。
- repair_report.json 记录原机位与新机位的 35 条射线命中、背景/表面/背面信息，以及图片节点、Base Color 链接、退化 UV 面和材质默认颜色。射线只查显式展示几何/演示地板，避免命中隐藏的基础全高模型。不是完整像素语义分类。
- 本工具不生成新的封盖面，因此灰色不能直接归因于新增 cap；可能是背景、演示地板默认材质、原始贴图内容/节点、退化 UV、背面或受光问题，需结合报告判断。
- 通过 1e-5m 量化的重合位置识别连接分量（处理逐角 UV 顶点分离）。小分量先保留，只列出位置/尺寸；需要确认确属无用后才传 --drop-component ID，仅隐藏展示副本，基础模型不动。高处几何也可能因展示截断不再显示，这不等于语义删除。
- 已有同指纹 Room8 候选本地分析得 3 个连接分量；其中一个小分量约 0.23×0.21×0.25m、40 个三角面，尚不能确认物理用途，默认不删除。分量编号以远端本次 repair_report 为准。

## 1. 本地 PowerShell：上传三个脚本

在 D:\burnroomvideo_byblender：

```powershell
scp -P 7777 .\app\F8_room_demo.py .\app\F8_prepare_room_asset.py .\app\room_demo_plan.py zhaojy@172.25.76.201:/tmp/
```

仅上传代码，不重新上传或生成候选资产，不重建镜像。三个文件名必须保持上述原名，因为 F8-D 会复用同目录辅助模块。

## 2. 远程 SSH：生成展示修正版

同一 SSH 会话逐行执行，任何一行报错先停止：

```bash
cd ~/burnroom-prod/burnroom-deploy-package
docker compose cp /tmp/F8_room_demo.py app-server:/tmp/F8_room_demo.py
docker compose cp /tmp/F8_prepare_room_asset.py app-server:/tmp/F8_prepare_room_asset.py
docker compose cp /tmp/room_demo_plan.py app-server:/tmp/room_demo_plan.py
asset=$(docker compose exec -T app-server python3 -c 'from pathlib import Path; items=list(Path("/app/data/KK-EEz16cmU14/rooms/Room8").glob("*/asset/manifest.json")); assert items,"No completed base asset found"; print(max(items,key=lambda p:p.stat().st_mtime).parent)')
printf 'Base asset: %s\n' "$asset"
docker compose exec -T app-server blender --background --factory-startup --python-exit-code 1 --python /tmp/F8_room_demo.py -- --asset "$asset" --mode inspect
```

自动选择最近有完整 manifest 的基础资产；打印的 Base asset 应是已验收技术检查的那个版本。脚本还会校验其产物指纹，拒绝文件不一致的版本。输出：

```text
[room-demo] mode=inspect output=/app/data/.../display_versions/<UTC_UUID> base_unchanged=true
```

每次运行都创建独立版本，失败现场留下 failure.json，不覆盖前次结果。

## 3. WinSCP：查看修正版

将输出路径开头 `/app/data/` 换成宿主机 `/data/zhaojy/burnroom-data/app-data/`，下载新版本中的 top.png、oblique.png、interior.png、repair_report.json。

检查墙体不挡主要空间、原始贴图更清楚；内部图现在是位于房间上方的向下展示视角，不再模拟人眼高度。仍需人工检查，不能仅凭脚本退出成功认定视觉通过。

基础 room.blend/glb 不改；新 display.blend 内包含隐藏的基础几何与可见展示副本。可疑小块不确定就保留。确认为无用的 ID 可在新一次 inspect 命令后追加 `--drop-component 2`（仅示例；必须使用报告中已核对的 ID）。随后 samples/short 要带同样的隐藏参数。

## 4. 展示图通过后：火灾样帧

同一 SSH 会话，沿用 asset 变量：

```bash
docker compose exec -T app-server blender --background --factory-startup --python-exit-code 1 --python /tmp/F8_room_demo.py -- --asset "$asset" --mode samples --accept-display --points /app/data/KK-EEz16cmU14/points.json
```

生成修正版三视图，以及 fire_1s.png、fire_3.5s.png、fire_6s.png。单独 room_timeline.json：基于完整点位的内部子图重算 BFS，13 个内点都可达；22 号 t=0，第二层 t=1.5s，第三层 t=3s。32 门口和42外部点不参加。本轮 1.5s 层间节奏是演示压缩，不是物理蔓延预测。

火焰：锥形体积、4D 噪声密度、径向和高度衰减，显式橙红 Emission Color，峰值大幅低于旧80；不使用旧发光球。烟雾：深色球状噪声体积、白色吸收颜色、随时间上升/缩放。强度有 0→25%→60%→100%→60%→20%→0，3秒渐入，Bezier 自动夹紧防负值；辅助点光峰值100W，无太阳灯。原参考地板仍 -1.35m；扫描平台可能高于它，为避免小火被原扫描面埋住，火源贴在该点可见展示表面上方，逐点 reference_floor_z / display_fire_base_z 写入报告，不宣称该面是物理地板。

## 5. 样帧通过后：4秒短片

```bash
docker compose exec -T app-server blender --background --factory-startup --python-exit-code 1 --python /tmp/F8_room_demo.py -- --asset "$asset" --mode short --accept-display --points /app/data/KK-EEz16cmU14/points.json --duration 4
```

默认 640×360、12fps、48帧，输出独立 fire_short.mp4；可设置 duration≤8，禁止用本入口提交完整313帧视频。4秒只检验起火及早期蔓延，不覆盖完整余烬阶段；6秒样帧可检查更后期。基础资产和旧 output.mp4/timeline.json 不写。

本地命令仅验证纯算法/节点连接，不能证明远端画面或性能；本轮未在本地运行 Blender/Docker。若远端 Traceback，请保留控制台与 failure.json，先修错误，不反复重跑长片。20分钟仍是后续完整视频的实测优化目标。

````

</details>
