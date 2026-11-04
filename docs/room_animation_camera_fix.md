# Room8 动画相机回归修复：先检查一张3.5秒总览

2026-11-04；对应PRD2.3 / architecture3.3。火焰/烟雾/灯光配置、数据库、基础资产和历史任务不改。本轮先camera_check，不执行short/final，不重构架构或修改GPU后端。

## 原因与证据

F8-D的camera(scene,...)会更新并返回当前scene.camera。F8-E原先连续调用两次，把同一对象分别存为overview和closeup；近景调用覆写了对象/data/跟踪目标，导致选择overview仍为PERSP/30mm。旧render_manifest中48个视频帧全部实际PERSP，标签却是overview；ortho_scale虽然有值，在透视模式下不控制构图。旧报告未记录对象名称，不能据此伪造实际对象名。

修复仅在动画调用端新建独立Room8_Overview、Room8_Closeup22及各自data/target，保留F8-D单机位循环的静帧接口。TRACK_TO保留；解绑派生场景继承的marker相机绑定，每次seek后显式选机位，渲染后回读，编码前核对实际相机。任务camera_mode显式为overview/closeup，默认overview；近景需明确选择。

总览类型ORTHO，位置/目标继续用第三轮公式：房间XY中心(cx,cy)、包围跨度span、地板floor；position=(cx+0.5span,cy-0.65span,floor+0.95span)，target=(cx,cy,floor+0.3)，基础ortho_scale=1.3span。利用实际画幅view_frame投影，检查已核验房间范围/展示墙高与13点峰值火焰包围盒；只在需要时扩大尺度以留4%边距，不移动模型/机位/目标。记录原尺度与实际尺度差异，不将覆盖检查等同于墙体遮挡或全部烟尾可见。

## 保留的旧短片实测

| 项目 | 用户提供报告中的实测 |
|---|---:|
| 视频 | 4秒，48帧，960×540，12fps |
| 48帧纯渲染 | 991.655秒 |
| 均值 / 中位数 | 20.659 / 19.023秒每帧 |
| P90 / 最大 | 29.261 / 33.604秒每帧 |
| 9次额外检查图 | 355.505秒 |
| 编码 / ffprobe | 0.729 / 0.108秒 |
| 整任务总耗时 | 1352.362秒，约22分32秒 |
| 渲染器 | llvmpipe / SOFTWARE，设备利用率峰值0% |

这些是错误近景下的软件渲染实测，不能当作整体总览或L20 GPU测试，旧全片推算也不能直接复用。报告和原视频继续保留；本轮不顺带调整GPU驱动/EGL/OpenGL配置。只读命令`python3 run_room_animation.py --report-job <旧任务目录>`无需Blender/GPU锁，不创建或修改旧任务。

## 本地PowerShell：上传9个文件

```powershell
cd D:\burnroomvideo_byblender
$cameraFiles = @(
    '.\app\run_room_animation.py'
    '.\app\room_animation_job.py'
    '.\app\F8_room_animation.py'
    '.\app\F8_room_demo.py'
    '.\app\F8_room_fire_style.py'
    '.\app\room_fire_config.py'
    '.\app\room_demo_plan.py'
    '.\app\F8_prepare_room_asset.py'
    '.\app\room_fire_round3.json'
)
scp -P 7777 $cameraFiles zhaojy@172.25.76.201:/tmp/
```

## 远程SSH：独立代码目录，不覆盖旧任务依赖

逐行执行，报错先停：

```bash
cd ~/burnroom-prod/burnroom-deploy-package
docker compose exec -T app-server mkdir -p /tmp/room_animation_camera_fix
docker compose cp /tmp/run_room_animation.py app-server:/tmp/room_animation_camera_fix/run_room_animation.py
docker compose cp /tmp/room_animation_job.py app-server:/tmp/room_animation_camera_fix/room_animation_job.py
docker compose cp /tmp/F8_room_animation.py app-server:/tmp/room_animation_camera_fix/F8_room_animation.py
docker compose cp /tmp/F8_room_demo.py app-server:/tmp/room_animation_camera_fix/F8_room_demo.py
docker compose cp /tmp/F8_room_fire_style.py app-server:/tmp/room_animation_camera_fix/F8_room_fire_style.py
docker compose cp /tmp/room_fire_config.py app-server:/tmp/room_animation_camera_fix/room_fire_config.py
docker compose cp /tmp/room_demo_plan.py app-server:/tmp/room_animation_camera_fix/room_demo_plan.py
docker compose cp /tmp/F8_prepare_room_asset.py app-server:/tmp/room_animation_camera_fix/F8_prepare_room_asset.py
docker compose cp /tmp/room_fire_round3.json app-server:/tmp/room_animation_camera_fix/room_fire_round3.json
```

原/tmp/room_animation_A、静帧代码和历史任务数据均不覆盖。无需重建镜像或重启服务。

同一个SSH会话完整复制：

```bash
asset=$(
docker compose exec -T app-server python3 - <<'PY'
from pathlib import Path
root = Path('/app/data/KK-EEz16cmU14/rooms/Room8')
items = list(root.glob('*/asset/manifest.json'))
assert items, 'No completed base asset found'
print(max(items, key=lambda p: p.stat().st_mtime).parent)
PY
)
printf 'Base asset: %s\n' "$asset"
```

确认是第三轮使用的基础资产。原先已确认wall-height/drop-component若有变化须沿用同样值；默认1.1m/不删除分量。

## 远程SSH：只输出一个动画总览帧

```bash
docker compose exec -T app-server python3 \
  /tmp/room_animation_camera_fix/run_room_animation.py \
  --asset "$asset" \
  --points /app/data/KK-EEz16cmU14/points.json \
  --config /tmp/room_animation_camera_fix/room_fire_round3.json \
  --stage camera_check \
  --camera-mode overview \
  --preset test
```

自动查找该资产版本旁style_round3下最新、指纹及基础房间验证通过的样帧目录。需要sample_manifest.json、requested_config.json、repair_report.json和原overview_3.5s.png。找不到时出图前停止，提供`--reference-samples /app/data/.../style_round3/<版本>/sample_manifest.json`显式指定；不要为绕过检查修改原报告。该参数路径为占位，须用真实路径。

这次只渲染3.5秒/帧43的一张960×540图，不生成MP4或short审批模板，不自动转短片。预期打印：

```text
[room-animation] camera_check=/app/data/.../render_jobs/<新任务>/keyframes/overview_3.5s.png ... status=awaiting_visual_review
```

## WinSCP：下载新任务整个目录

容器/app/data映射宿主机/data/zhaojy/burnroom-data/app-data。新目录仍在KK-EEz16cmU14/rooms/Room8/render_jobs/<新任务>，不使用旧错误任务的--resume。

下载整个新任务，保持相对目录结构：

- keyframes/overview_3.5s.png：动画入口新总览。
- reference_overview_3.5s.png：原第三轮参考图的校验后副本，原文件不改。
- camera_comparison.html：本地浏览器打开，左右并排看原图与修复图。
- camera_comparison.json：位姿/目标/类型对照，正交尺度是否为包围覆盖放大。
- config_snapshot.json：animation.camera_mode=overview、stage=camera_check。
- effective_settings.json、render_manifest.json：实际对象/data/type/位置/世界旋转/TRACK_TO目标/轴向/正交尺度及覆盖范围；请求与实际不符即失败。
- timing_report.json：本次单帧耗时，不代表旧48帧基准；旧报告继续保留。

检查整个Room8轮廓、主要火点和蔓延范围均在画幅内，内部无遮挡，机位与原overview基本一致；如果只扩大正交尺度，应在JSON中明确体现。实际图片须远端生成，离线测试不能代替画面验收。图通过后再单独运行新总览short，不能直接全片；当前不自动执行短片或正式视频。

## 本地测试

新增test_room_animation_camera.py共11项；含真实旧camera helper的同对象覆写复现、独立相机回归、投影余量、显式模式、单帧无编码、参考绑定及历史报告只读。原动画测试补充有效相机字段。相关回归109项通过；不运行本地Blender或远端服务，不触碰数据库或真实资产。原F8-D及room_fire_round3.json未修改。
