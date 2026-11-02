# 房间几何断面诊断（只读）

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
.\.venv-diagnostics\Scripts\python.exe -m app.diagnose_room_sections --data-root .\data --inspection .\data\KK-EEz16cmU14\diagnostics\room_inspection\20261031T033807Z_79b97ce7\inspection.json --blender-report .\data\KK-EEz16cmU14\diagnostics\room_inspection\20261031T033807Z_79b97ce7\remote_import_user_output.json --alignment-dir .\data\KK-EEz16cmU14\diagnostics\alignment\20261029T032340Z_177df64f
```

requirements-diagnostics.txt 是可选绘图依赖，不改变生产镜像依赖。没有本地 Docker/服务启动。输入变化会拒绝执行，需重新核验，不能修改报告哈希绕过。

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
