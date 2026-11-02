# 既有 Room8：最小展示修正与火灾预览

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
