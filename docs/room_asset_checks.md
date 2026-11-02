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
scp -P 7777 .\app\F8_inspect_room_import.py zhaojy@172.25.76.201:/tmp/burnroom_room_import_check.py
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
