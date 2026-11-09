# app 脚本索引

保留现有API和app兼容路径；已迁移工具的实际位置见下表。F8文件必须在远端Blender内执行，不能用普通Python直接运行，也不能由后端import。

| 标记 | 文件 | 职责及输入输出 | 当前是否运行 |
|---|---|---|---|
| F8-A 前置检查 | F8_inspect_room_import.py | 读 inspection.json，核对原始完整模型导入坐标/UV/材质/贴图，写独立 blender_import.json；不裁切、不出图 | 已通过，输入未变无需重跑 |
| F8-B 资产生成 | F8_prepare_room_asset.py | 读 candidate.json 和源资产，保存房间 blend/GLB，重载基础 blend 核验，派生三视图和剖面副本 | 已生成，无需重跑 |
| F8-C 旧视频入口 | F8_blender_render.py | 旧 timeline.json → 火焰/烟雾/运镜 → 根目录 output.mp4；旧 API 仍调用它，可能删除旧视频 | 本次不运行；尚未接入新房间资产 |
| **F8-D 第三轮静帧基线** | **F8_room_demo.py** | 只读既有 room.blend；inspect 三视图、samples 主火中近景/总览六图；当前禁用short及动画 | **保留静帧回退；A阶段动画使用F8-E** |
| **F8-E 动画任务** | **F8_room_animation.py** | Blender内部worker，独立总览/近景相机，复用第三轮样式按绝对时间输出帧/检查图 | **启动器默认camera_check，先出3.5秒一张图；不能直接执行worker** |

| 相关普通 Python 工具 | 职责 | 当前关系 |
|---|---|---|
| room_source_io.py | 只读 OBJ/MTL、数值/索引、路径约束、XY逆变换和字节SHA256 | stdlib公共模块；inspect_room_asset保留原函数名导出 |
| room_source_inputs.py | 输入/贴图指纹、人工XY结论、Blender导入证据绑定 | 候选和断面共用；diagnose_room_sections保留load_inputs/REQUIRED_CHECKS导出 |
| probe_floorplan.py | 探测并留存户型 API 结果 | 上游数据来源 |
| analyze_floorplan.py | 户型/点位 XY 对齐与归属候选，生成 overlay | 上游核验 |
| inspect_room_asset.py | 材质/UV/坐标和高度采样核验 | 上游 inspection |
| diagnose_room_sections.py | 只读断面诊断的旧路径兼容入口 | 实现迁至 tools/diagnostics/diagnose_room_sections.py；旧-m命令仍可用 |
| room_section_geometry.py / room_section_plots.py | 断面几何/绘图的旧导入兼容入口 | 实现迁至 tools/diagnostics/；与新模块共享同一对象及函数 |
| prepare_room_candidate.py | 用已核验多边形实际裁切，写独立 candidate.json，记录显式近似策略 | 本地已完成 |
| room_clip_geometry.py | 凹多边形面级裁切及 UV 插值算法 | 被 candidate 工具调用，无 bpy |
| room_demo_plan.py | 展示连接分量分析、房间内部子图 BFS 和渐变时序 | F8-D 使用，无 bpy；小块默认不删除 |
| room_fire_round1.json / room_fire_round2.json / room_fire_round3.json / room_fire_config.py | 分轮艺术/事件/质量参数、校验、固定种子的曲线火舌及卷曲烟柱网格 | stdlib，无 bpy；默认第三轮，旧轮次可显式选择 |
| F8_room_fire_style.py | F8-D/E共用Blender辅助，节点/火烟/灯光/设置回读 | **没有独立运行入口，不是新的渲染任务入口** |
| run_room_animation.py | A阶段普通Python启动器，进程锁/单帧核对/子进程/编码/失败保留；report-job只读旧报告 | **当前先camera_check，overview默认；不调用旧API** |
| room_animation_job.py | 冻结配置、版本任务、绝对时间状态、PNG/MP4契约、耗时统计和审核绑定 | stdlib，无bpy或数据库 |

本次链路：已核验户型 → prepare_room_candidate.py → candidate.json → **F8-B** → room.blend / room.glb / 三视图 → 人工验收 → 后续火灾效果阶段。

2026-11-07 第一批解耦：候选入口直接读取 room_source_inputs，不再通过断面/高度诊断入口加载输入。公共函数保持既有解析/校验行为；未修改高度计算、裁切算法或F8动画/样式。当前出片完成度见 [PROJECT_STATUS](../docs/PROJECT_STATUS.md)。

2026-11-09 第二批：三个断面实现迁入tools/diagnostics，app保留兼容模块。新入口为 `python -m tools.diagnostics.diagnose_room_sections`；旧 `python -m app.diagnose_room_sections` 继续可用。必须连同tools一起安装，不能只上传兼容文件覆盖旧容器脚本。工具只写独立diagnostics，不参与Room8正式渲染。

完整操作：[候选资产与检查图](../docs/room_candidate.md)。F8-B 保存的基础房间与 section_preview.blend 分开；三视图使用展示去顶副本。地板参考高度是演示工程近似，扫描平台/家具未自动重建。
