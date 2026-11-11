# 独立房间资产与展示检查

更新：2026-11-11。合并原坐标/高度、断面、候选裁切和展示资料。Room8基础资产已在远端生成并技术检查通过，本轮不重新裁切、出图或渲染；详细原文见[资产历史](../archive/20261111_process/room_assets_history.md)。

## 当前工程决策

- Room8使用已人工核验的11顶点多边形，零外扩；22号在客厅、32号为门口边界、42号在户型外，Room11无效。
- 原始OBJ与Blender世界坐标一致，不再额外移动原始Z。
- floor_z=-1.35m是主导下包络候选的平层工程近似，不是已证明的真实建筑地板；不把物理地板、平台、吊顶、墙厚完全确认作为本案例出片前置。
- 历史review/inspection中的结论不回填；新candidate明确工程近似和physical_semantics_verified=false。
- 基础room.blend保留房间范围内原几何、UV、材质、贴图和坐标。展示去顶/低墙另存派生版本，不能永久改基础模型。
- 只验证了Room8；通用房间ID参数不等于其他房间已经验收，不能自动沿用-1.35m。

## 当前链路与文件

```text
probe_floorplan → 户型探测包
floorplan_alignment + analyze_floorplan → 对齐报告/overlay → 人工review
room_source_inputs → 输入与证据指纹核对
prepare_room_candidate + room_clip_geometry → candidate.json
F8_prepare_room_asset → room.blend / room.glb → 重载技术验证 / 三视图
F8_room_demo → 独立展示副本 / R3静帧
安全动画启动器 → 独立视频任务
```

| 文件 | 含义 |
| --- | --- |
| alignment_report.json / overlay.html / point_rooms.csv | 算法对齐和点位归属候选；图不是人工审核本身 |
| review.json | 绑定报告指纹的人工结论，保留核验人/时间/说明 |
| inspection.json / blender_import.json | 只读模型采样与Blender导入证据，不是完整建筑语义认证 |
| candidate.json | 面级裁切几何、逐角UV/材质、点位、输入指纹和近似策略 |
| room.blend | 基础独立资产，原始XYZ；已重载验证 |
| room.glb | 自包含网页候选模型，导出坐标(x,y,z)→(x,z,-y)；不是已完成浏览器验收 |
| manifest.json / validation.json | 来源、产物指纹和技术验证；passed不等于视觉通过 |
| top.png / oblique.png / interior.png | 派生俯视、斜视、内部检查图 |
| section_preview.blend / display.blend | 展示副本，不能代替基础room.blend |

基础Room8裁切后6,835个源三角面，独立演示地板9面；13个内部点，32号门口单列，42号不纳入。点位Empty保留源XYZ与归属，火源参考高度另记。GLB技术检查包含结构、自包含与贴图；未做浏览器交互或完整GLB重导入验收。

## 工具与执行环境

| 环境 | 工具/操作 |
| --- | --- |
| 本地PowerShell，普通Python | render_engine.geometry.prepare_room_candidate，读取已有核验与证据，生成唯一候选版本 |
| 普通Python，只读诊断 | tools.diagnostics下的analyze_floorplan、inspect_room_asset、diagnose_room_sections；不得冒充自动语义判定 |
| 远端Blender | tools/diagnostics/blender/F8_inspect_room_import.py，仅导入检查；源输入不变无需重复 |
| 远端Blender | render_engine/blender/F8_prepare_room_asset.py，资产生成、保存、重载、导出、三视图 |
| 远端Blender | render_engine/blender/F8_room_demo.py --mode inspect，加载既有资产做展示检查 |
| WinSCP | 传输明确版本候选/下载产物，不远端编辑源码，不更改文本换行 |

本地先看帮助，替换证据路径后才生成候选：

```powershell
python -m render_engine.geometry.prepare_room_candidate --help
python -m render_engine.geometry.prepare_room_candidate --data-root data --inspection "替换为inspection.json路径" --blender-report "替换为blender_import.json路径" --alignment-dir "替换为已核验目录" --floor-z -1.35 --accept-flat-floor
```

引号中的替换文字为占位说明，不直接粘贴执行。不同房间须提供对应核验文件、导入证据和显式参考高度。候选生成不运行Blender、不写数据库，终端会给出新的candidate路径。

以后需要生成新资产时，先按[完整包说明](animation.md#完整代码包与执行位置)取得code_root。将候选放入数据盘新的唯一版本目录；原始模型/MTL/贴图/points及历史文件须匹配候选指纹。远程SSH、同一Compose会话中的资产入口为：

```bash
docker compose exec -T app-server blender --background --factory-startup --python-exit-code 1 --python "$code_root/render_engine/blender/F8_prepare_room_asset.py" -- --candidate "$candidate" --data-root /app/data --display-height 2.4
```

candidate必须先指向已上传并核验的实际路径。本命令生成资产和检查图，不是动画；失败版本保留，重新尝试创建新版本，不覆盖原asset目录。display-height=2.4是去顶展示相对高度，不是实测层高；F8-D的wall-height=1.1是另一阶段低墙展示参数。

## 人工检查重点

房间范围、贴图/UV、材质、室内可见性、点位对应、火源漂浮/遮挡以及是否明显混入邻房。灰面可能来自原材质、法线、光照或可见背面，不能直接判为贴图损坏；裁切为开放边界，不自动封盖。孤立分量默认保留，只对明确核验无用的ID在展示副本隐藏。

高度/断面诊断仍保留源工具及487点历史依据，但不作为Room8再次等待建筑精确恢复的门槛。未烧房间的灾前重建、家具语义、墙厚与真实楼板仍未解决；不因工程近似标记而宣称已完成。
