# app 脚本索引

保留现有文件名与 API 路径，仅标注职责，不做目录重构。F8 文件必须在远端 Blender 内执行，不能用普通 Python 直接运行，也不能由后端 import。

| 标记 | 文件 | 职责及输入输出 | 当前是否运行 |
|---|---|---|---|
| F8-A 前置检查 | F8_inspect_room_import.py | 读 inspection.json，核对原始完整模型导入坐标/UV/材质/贴图，写独立 blender_import.json；不裁切、不出图 | 已通过，输入未变无需重跑 |
| **F8-B 当前检查图** | **F8_prepare_room_asset.py** | 读 candidate.json 和源资产，保存房间 blend/GLB，重载基础 blend 核验，派生三视图和剖面副本 | **本次只运行它** |
| F8-C 旧视频入口 | F8_blender_render.py | 旧 timeline.json → 火焰/烟雾/运镜 → 根目录 output.mp4；旧 API 仍调用它，可能删除旧视频 | 本次不运行；尚未接入新房间资产 |

| 相关普通 Python 工具 | 职责 | 当前关系 |
|---|---|---|
| probe_floorplan.py | 探测并留存户型 API 结果 | 上游数据来源 |
| analyze_floorplan.py | 户型/点位 XY 对齐与归属候选，生成 overlay | 上游核验 |
| inspect_room_asset.py | 材质/UV/坐标和高度采样核验 | 上游 inspection |
| diagnose_room_sections.py | 只读断面诊断入口 | 历史证据，不再阻塞工程近似试裁切 |
| room_section_geometry.py / room_section_plots.py | 断面几何与 PNG 绘制辅助 | 被诊断入口调用 |
| prepare_room_candidate.py | 用已核验多边形实际裁切，写独立 candidate.json，记录显式近似策略 | 本地已完成 |
| room_clip_geometry.py | 凹多边形面级裁切及 UV 插值算法 | 被 candidate 工具调用，无 bpy |

本次链路：已核验户型 → prepare_room_candidate.py → candidate.json → **F8-B** → room.blend / room.glb / 三视图 → 人工验收 → 后续火灾效果阶段。

完整操作：[候选资产与检查图](../docs/room_candidate.md)。F8-B 保存的基础房间与 section_preview.blend 分开；三视图使用展示去顶副本。地板参考高度是演示工程近似，扫描平台/家具未自动重建。
