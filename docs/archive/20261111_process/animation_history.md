# animation_history.md

2026-11-11合并的历史原文。来源提交：`fd3b3724a6526040f09dee8dd5eab57e64e33af3`。以下旧命令、路径、门禁和“当前状态”仅用于追溯，不作为运行指令。当前说明从[文档索引](../../README.md)进入。原文以Markdown源码保存，换行统一为LF；manifest.json记录原路径、工作副本SHA、Git blob及合并后字节范围，可提取校验。

<details>
<summary>docs/room_animation.md</summary>

````markdown
# A阶段：冻结第三轮风格的Room8短片与性能验收

> 第4批后下文平铺SCP/CP及/tmp脚本路径仅适用于归档版本，不能拿当前app兼容文件直接执行。新版必须按[完整代码包说明](room_engine_migration.md)安装；本轮不复跑短片。

2026-11-09兼容更新：下方上传/复制清单已包含`F8_room_helpers.py`，须与worker同目录。历史短片步骤不作为当前清理任务指令；本轮不运行渲染，也不以新源码续跑旧任务。

首轮短片发现相机对象复用错误，已修复。当前先按[动画相机单帧核对](room_animation_camera_fix.md)操作；本页原短片步骤暂停，构图通过后再用short。默认stage现为camera_check，任务显式记录camera_mode。

2026-11-04；PRD2.3 / architecture3.3。当前仅执行short，不执行final。原F8-D静帧入口和room_fire_round3.json不变；新F8-E经普通Python启动器调用Blender，不访问数据库或旧API。

## 输出与时间契约

任务目录为`/app/data/KK-EEz16cmU14/rooms/Room8/render_jobs/<UTC_UUID>/`，位于Room8根下，不在原asset目录内：

| 文件/目录 | 含义 |
|---|---|
| config_snapshot.json | 冻结第三轮原配置、动画preset、时序及全部输入/代码指纹 |
| render_manifest.json | 每帧帧号/秒数/机位/阶段/耗时/图片SHA/实际材质灯光及技术状态 |
| timing_report.json | 本次准备/启动/加载/初始化/渲染/编码/ffprobe/总耗时、阶段统计和完整视频推算 |
| frames/frame_000001.png…000048.png | 4秒视频的48张总览图，t=(frame-1)/12，末帧为3.9167秒 |
| keyframes/ | 原1/3.5/6秒六张比较图，以及5.5/6.5/10/16/23秒后期总览检查 |
| fire_short.mp4 / video_receipt.json | 4秒48帧H.264、yuv420p、faststart；视频尺寸/帧率/时长/帧数/文件大小与哈希回执 |
| effective_settings.json / room_timeline.json | 回读第三轮场景/效果/照明及独立13点BFS，不覆盖场景原timeline |
| gpu_metrics.jsonl | 可获取时每约5秒记录全部可见GPU温度/利用率/显存；缺失时保存原因 |
| status.json | created→preparing→rendering→encoding→awaiting_visual_review；失败为failed/interrupted |
| attempts/<attempt>/ | 每次运行的launch.json、blender.log、encode.log、worker_timing.json、timing_report.json；失败保留failure.json/log |
| approval_template.json | 短片完成后生成，默认approved=false，所有人工检查false；不自动执行正式渲染 |

1秒与3.5秒的总览直接复制视频帧，不再渲染；另做9次检查渲染。因此短片有48帧，整个任务共57次实际出图、59份PNG（含2复制），报告分别统计主视频和额外检查，不把整个任务总时长冒充仅48帧耗时。

火焰最后激活3秒、每点火焰8秒结束，故全房间火焰11秒结束；烟每点20秒归零，末批23秒结束。完整视频建议24秒（结束后1秒缓冲）：测试档960×540/12fps/288帧，正式候选1280×720/24fps/576帧。主镜头固定使用已验收第三轮总览；近景不剪入当前短片，仅用来对照。编码libx264/CRF20/medium/2CPU线程；更高质量不在本轮强制。正式preset只改变FPS/尺寸，不修改艺术参数、采样或体积步数。

## 安全与限制

- 启动器检查第三轮规范化JSON指纹、独立资产验证、候选/点位/脚本指纹和13点归属；32/42不进入传播。不改原始OBJ/MTL/贴图、核验、基础blend/GLB、场景原timeline、旧视频或数据库。
- `/app/data/.room_animation_gpu.lock`为Linux内核排他锁，贯穿本任务Blender及编码，锁描述符继承到Blender；异常退出不通过删除锁文件“解锁”。Eevee不是CUDA渲染器，不假装用CUDA_VISIBLE_DEVICES绑定单卡；本版保守串行占用全部可见GPU的调度名额。
- 启动前拒绝已有容器Blender或可检测到的GPU计算/图形进程。pmon/指标不可用会明确记录限制；此锁不能原子阻止不遵循它的其他用户/旧API任务，因此本轮不要同时启动旧API、手动Blender或其他GPU渲染。约85°C告警，90°C终止本任务，保留帧。
- 绝对时间公式设置所有火/烟/光及噪声参数，无CFD模拟缓存；任意帧可独立求状态。不同GPU的PNG字节级一致性不在承诺范围。没有新增几何边界遮罩，点位归属正确不等于火烟体积绝不穿墙；这必须在短片及检查图里人工验收。
- 运行时不覆盖已有帧/视频；新帧先写本次暂存目录并验证PNG尺寸/尾标记后发布并登记SHA。失败保留现场，续跑只复用已登记、指纹一致的有效帧。损坏或未登记文件不静默覆盖，保留并报错，此时使用新任务排查。
- 完成后只进入awaiting_visual_review，技术通过不代表视觉通过。没有short自动调用final的代码路径。

## ① 本地PowerShell：上传9个文件

完整复制：

```powershell
cd D:\burnroomvideo_byblender
$animationFiles = @(
    '.\app\run_room_animation.py'
    '.\app\room_animation_job.py'
    '.\app\F8_room_animation.py'
    '.\app\F8_room_demo.py'
    '.\app\F8_room_fire_style.py'
    '.\app\room_fire_config.py'
    '.\app\room_demo_plan.py'
    '.\app\F8_prepare_room_asset.py'
    '.\app\F8_room_helpers.py'
    '.\app\room_fire_round3.json'
)
scp -P 7777 $animationFiles zhaojy@172.25.76.201:/tmp/
```

无需build/deploy或重启服务。容器内使用独立`/tmp/room_animation_A`代码目录，保留原静帧运行文件。

## ② 远程SSH：准备隔离运行目录

逐行执行，任意命令失败先停：

```bash
cd ~/burnroom-prod/burnroom-deploy-package
docker compose exec -T app-server mkdir -p /tmp/room_animation_A
docker compose cp /tmp/run_room_animation.py app-server:/tmp/room_animation_A/run_room_animation.py
docker compose cp /tmp/room_animation_job.py app-server:/tmp/room_animation_A/room_animation_job.py
docker compose cp /tmp/F8_room_animation.py app-server:/tmp/room_animation_A/F8_room_animation.py
docker compose cp /tmp/F8_room_demo.py app-server:/tmp/room_animation_A/F8_room_demo.py
docker compose cp /tmp/F8_room_fire_style.py app-server:/tmp/room_animation_A/F8_room_fire_style.py
docker compose cp /tmp/room_fire_config.py app-server:/tmp/room_animation_A/room_fire_config.py
docker compose cp /tmp/room_demo_plan.py app-server:/tmp/room_animation_A/room_demo_plan.py
docker compose cp /tmp/F8_prepare_room_asset.py app-server:/tmp/room_animation_A/F8_prepare_room_asset.py
docker compose cp /tmp/F8_room_helpers.py app-server:/tmp/room_animation_A/F8_room_helpers.py
docker compose cp /tmp/room_fire_round3.json app-server:/tmp/room_animation_A/room_fire_round3.json
docker compose exec -T app-server python3 /tmp/room_animation_A/run_room_animation.py --help
```

最后应显示帮助和short/final参数，不启动渲染。容器重建后/tmp代码会消失，须重传同版本；数据盘任务与日志仍保留。短片审批后不要修改/覆盖这一目录的代码，否则正式门禁会拒绝旧审批。

## ③ 同一个远程SSH会话：确认基础资产

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

确认与第三轮使用同一asset版本，若不是先手工设为该版本的容器内绝对路径。与第三轮相同的展示wall-height/drop-component参数必须沿用，默认wall-height=1.1、不删除孤立块。

## ④ 同一个远程SSH会话：只启动4秒短片

```bash
docker compose exec -T app-server python3 \
  /tmp/room_animation_A/run_room_animation.py \
  --asset "$asset" \
  --points /app/data/KK-EEz16cmU14/points.json \
  --config /tmp/room_animation_A/room_fire_round3.json \
  --stage short \
  --preset test
```

不要直接执行F8_room_animation.py；worker需要启动器继承的GPU锁。启动时会打印job绝对路径。终端保持连接到完成；如SSH断开，不要立刻重启，先看状态及进程，内核锁/进程检查会防止重复启动。

预期末行：

```text
[room-animation] done video=/app/data/.../Room8/render_jobs/<run_id>/fire_short.mp4 frames=48 total_seconds=<实测值> status=awaiting_visual_review
```

Blender逐帧进度在`<job>/attempts/<attempt>/blender.log`；可以在另一个SSH会话只读查看（将路径换成首行打印值）：

```bash
tail -n 30 /data/zhaojy/burnroom-data/app-data/KK-EEz16cmU14/rooms/Room8/render_jobs/<run_id>/attempts/<attempt>/blender.log
```

上式的`<run_id>`/`<attempt>`为占位，不可原样执行。也可直接用WinSCP查看日志和status.json，不需开启第二个渲染。

## ⑤ WinSCP：下载审核

容器`/app/data/`映射宿主机`/data/zhaojy/burnroom-data/app-data/`。进入`KK-EEz16cmU14/rooms/Room8/render_jobs/<run_id>/`，下载fire_short.mp4、keyframes整个文件夹、config_snapshot.json、render_manifest.json、timing_report.json、video_receipt.json、status.json；有异常再附attempts日志和gpu_metrics.jsonl。

检查主火22的成长、13点次级点依次激活、火舌/烟上升连续性、材质与灯光无跳变、相机无遮挡穿模、火烟没有明显穿地/穿墙/越界，且与第三轮六图风格吻合。4秒片段不覆盖6秒浓烟和火弱后阶段，必须同时看5.5/6/6.5/10/16/23秒图；这些离散图仍不能证明后期运动连续性，如有可疑跳变再单独补后期短序列，不直接开全片。

报告中的video_frames为48帧性能基准，extra_keyframes为9次额外出图；启动/资产/初始化分项在blender字段，第一帧包含GPU/着色器首次预热，逐帧render_seconds包含PNG压缩写出，状态更新及I/O开销单列。total_seconds_this_attempt包含额外检查和编码，不是纯4秒片段渲染时间。GPU显存为设备总量，不冒充精确进程显存。可选gpu.renderer字段从实际渲染上下文记录厂商/渲染器/设备类型，若识别到SOFTWARE/llvmpipe等则标记疑似软件渲染，不能因为有nvidia-smi就宣称Eevee实际使用了L20；读取失败如实记原因，不改变当前渲染后端。[Blender GPU平台接口](https://docs.blender.org/api/4.1/gpu.platform.html)。P90用最近秩算法；续跑帧保留原始耗时，本次墙钟总时长不含上次失败耗时，各attempt保留原记录。

完整耗时在full_video_estimate中标为extrapolated_not_measured：结合总览阶段均值、P90、后期单帧和像素比例给测试/正式候选估算，非置信区间；缺少阶段与样本少均需谨慎，短片编码时间仅为占位，不保证20分钟。下阶段按报告选择正式档，不为赶时间自动降低火烟可见性。

## 失败与续跑（只在原任务确已停止后）

失败时先下载status与attempts日志。修复外部问题（如磁盘/容器资源）且代码/输入/配置完全未变，可以将④的同一命令加`--resume /app/data/.../Room8/render_jobs/<run_id>`；此为占位路径，替换后使用。已登记有效帧跳过，编码失败可复用帧；每次创建新attempt保留先前日志。若改了代码/配置/输入、出现损坏或未登记图片，使用新任务；不要删别人的锁/帧，不通过改snapshot/manifest“绕过”核验。成功待审核任务不接受resume。

## 正式出片门禁（本轮不执行）

人工审核后复制approval_template.json为独立approved.json，填写approved=true、复核人、带时区reviewed_at、七项checks全部true、approved_final_presets明确填写test和/或final，并写性能预算/疑点处理说明；保持source_job/binding/evidence原值。模板不会自动填true，也不会自动渲染。正式入口要求显式stage=final及approval路径，且重新校验短片报告/视频/实际帧证据和相同配置/资产/代码/镜头；画质未获准会拒绝。当前不提供直接执行正式渲染的步骤，短片报告人工通过后再按选定preset安排。

## 本地验证边界

`python -m unittest test.test_room_animation -v`新增24项，连同静帧/房间/户型回归98项通过。仅临时合成数据及进程、Linux锁、Blender和编码替身，不运行本地Docker/Blender/ffmpeg，不连接远端或数据库。真实Linux继承锁、Eevee/FFmpeg兼容、连续性和性能尚待远端执行。本地测试中打印的临时视频和耗时为模拟数据，不能汇报为GPU实测成果。

````

</details>

<details>
<summary>docs/room_animation_camera_fix.md</summary>

````markdown
# Room8 动画相机回归修复：先检查一张3.5秒总览

> 第4批后下文平铺上传/运行命令属于历史版本。当前app文件是兼容入口，必须按[完整代码包说明](room_engine_migration.md)安装；本轮不重新出图。

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

## 本地PowerShell：上传10个文件

2026-11-09：清单补入共用Blender模块；本页保留相机修复操作依据，不代表本轮要重新出图。新源码对应新任务，不更改旧任务签名续跑。

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
    '.\app\F8_room_helpers.py'
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
docker compose cp /tmp/F8_room_helpers.py app-server:/tmp/room_animation_camera_fix/F8_room_helpers.py
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

````

</details>

<details>
<summary>docs/room_animation_final.md</summary>

````markdown
# Room8 直接正式出片（2026-11-04）

2026-11-09第4批：必须先按[完整代码包说明](room_engine_migration.md)安装并在当前SSH会话设置`engine_root`。不再上传平铺脚本；下方路径已适配包结构。V1已出片，本轮不执行渲染，新源码不能续跑旧任务；复现V1应恢复归档代码。

**GPU修正优先**：生产容器原先只有Mesa图形库，必须先按room_gpu_fix.md应用NVIDIA graphics能力并重新创建app-server。下文旧步骤中的“无需重启”仅适用于驱动挂载已修复的容器。新版final会强制校验实际NVIDIA上下文；首次修复须使用新任务，不续跑旧CPU任务。

本次用户明确授权替代旧短片前置门禁。只运行一次24秒、1280×720、24fps、576帧总览正式任务；不追加短片或近景样帧，不预估耗时。第三轮配置冻结。无数据库/几何/旧API操作，无镜像重建或容器重启。

## 1. 本地 PowerShell

```powershell
cd D:\burnroomvideo_byblender
.\release\scripts\build.ps1
```

将生成的包通过WinSCP上传并按迁移说明解压到独立目录，获得`engine_root`；不要直接覆盖现有部署，不使用本地Docker。本轮仅维护说明，不执行这些步骤。

## 2. 远程 SSH：装入运行脚本并选取已有资产

```bash
cd ~/burnroom-prod/burnroom-deploy-package
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

asset应指向既有`Room8/<版本>/asset`；入口会再次核对资产/候选点位/第三轮配置指纹，不重新生成资产。

## 3. 远程 SSH：后台启动正式视频

```bash
launch_log="$HOME/burnroom-prod/room8-final-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
nohup docker compose exec -T app-server python3 -u \
  "$engine_root/app/run_room_animation.py" \
  --asset "$asset" \
  --points /app/data/KK-EEz16cmU14/points.json \
  --config "$engine_root/configs/render/room_fire_round3.json" \
  --stage final --preset final --camera-mode overview --direct-final \
  > "$launch_log" 2>&1 < /dev/null &
printf 'Launch log: %s\n' "$launch_log"
tail -n 20 "$launch_log"
```

只启动一次。nohup让SSH断开后任务继续；Shell显示后台PID不代表渲染成功。稍后再次tail查看启动日志，应出现`[room-animation] job=/app/data/.../render_jobs/<run_id> ... stage=final`。若已有Blender/GPU任务或输入不符，会直接拒绝并记录原因，不自动停止其他任务。

## 4. WinSCP 检查与下载

远端实际目录：`/data/zhaojy/burnroom-data/app-data/KK-EEz16cmU14/rooms/Room8/render_jobs/<run_id>/`。

- `status.json`：preparing/rendering/encoding，成功为awaiting_visual_review（技术完成，待人工播放）。
- `attempts/<attempt>/blender.log`：逐帧日志；encode.log/decode.log：编码/完整解码日志；失败另保留failure.json/failure.log。
- `frames/`：576张逐帧PNG，失败不删除。
- `config_snapshot.json`：精确输入、代码指纹、第三轮配置、相机模式及直接出片授权。
- `render_manifest.json`：逐帧有效相机、指纹、耗时及technical_complete=true。
- `timing_report.json`：实测逐帧均值/中位数/P90/最大值、阶段及本次总耗时，无正式预估。
- `fire_final.mp4`、`video_receipt.json`：只有ffprobe检查及完整解码通过后发布；receipt应为576帧、1280×720、24fps、24秒、full_decode_passed=true，并含大小/SHA。

下载视频及上述JSON/日志，实际播放到结尾确认。技术核验不等于人工认可动画画面。

## 5. 远程 SSH：失败或中断后续跑

先确认旧任务已停止。保持同一批代码、配置和资产；将下面两处值替换为启动日志中的实际路径，不换成别的任务。无需删除帧或锁文件。

```bash
asset='/app/data/KK-EEz16cmU14/rooms/Room8/实际资产版本/asset'
job='/app/data/KK-EEz16cmU14/rooms/Room8/render_jobs/实际run_id'
launch_log="$HOME/burnroom-prod/room8-final-resume-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
nohup docker compose exec -T app-server python3 -u \
  "$engine_root/app/run_room_animation.py" \
  --asset "$asset" --points /app/data/KK-EEz16cmU14/points.json \
  --config "$engine_root/configs/render/room_fire_round3.json" \
  --stage final --preset final --camera-mode overview --direct-final \
  --resume "$job" > "$launch_log" 2>&1 < /dev/null &
printf 'Resume log: %s\n' "$launch_log"
```

续跑核对已有帧的相机、时刻、尺寸和SHA，只补缺帧。损坏或未登记文件保留并报错，不静默覆盖。容器重建会清除/tmp脚本，需先重新上传相同版本；本流程不主动重建容器。

````

</details>

<details>
<summary>docs/room_gpu_fix.md</summary>

````markdown
# Room8 NVIDIA EEVEE 修复（2026-11-04）

> 第4批后下文9/10文件平铺上传步骤已失效，当前须用[完整代码包](room_engine_migration.md)。本页保留GPU修复依据，本轮不重建容器或修改GPU环境。

**2026-11-05当前生效策略（替代下文保留gpus: all的中间方案）**：远端临时容器使用同一burnroom-app:latest镜像、runtime=nvidia、NVIDIA_VISIBLE_DEVICES=all及compute,utility,graphics，但不传--gpus时，EGL/GLX均加载成功且有10_nvidia.json；原应用Runtime=nvidia但带gpus: all仍未挂载图形库。应用改用已验证的runtime+环境变量路径：生产模板删除gpus，覆盖文件用gpus: !reset []清除远端基础compose继承的GPU DeviceRequests。只删除覆盖文件中的gpus行无法清除基础文件的值。先远端config --quiet验证Compose支持该合并语法，失败时不要重建；重建后必须Runtime=nvidia、DeviceRequests为null或空列表，且ctypes加载两个库为OK。容器重建后恢复/tmp/room8_gpu_code；正式首帧继续核验实际NVIDIA renderer，不因库加载成功就宣称EEVEE已使用GPU。不修改宿主机Docker全局配置或其他容器。

2026-11-05补充：宿主机已安装580.178.04图形库，但容器依然无库。只读检查显示Docker已注册nvidia运行时、默认及app-server实际运行时为runc，Toolkit/CLI均为1.20.0。因此生产模板与GPU覆盖文件均增加app-server.runtime: nvidia，显式走NVIDIA runtime；不修改Docker全局默认运行时、不重启Docker守护进程、不改其他容器。gpus: all及compute,utility,graphics保留。此次是有依据的下一步修复，仍须重建后检查实际Runtime=nvidia、库可加载及NVIDIA EGL JSON；不能仅凭运行时名称宣布EEVEE已使用GPU。

现有远端证据：4张L20可枚举，但NVIDIA_DRIVER_CAPABILITIES未设置，EGL vendor只有50_mesa.json，无libEGL_nvidia/libGLX_nvidia。NVIDIA Toolkit默认utility/compute不足以提供EEVEE所需graphics能力。配置修复不保证宿主机图形驱动本身完整，必须观察实际上下文。

只将release/docker-compose.gpu.yml上传为远端部署目录的docker-compose.gpu.yml，叠加现有compose。不要用本地生产模板整体替换远端compose或凭证。先确认旧Blender任务已停止；保留旧任务目录。不要使用docker compose down或删除卷。

在本地上传动画运行文件到独立宿主机目录/tmp/room8_gpu_code，保留原/tmp/room8_final_code。2026-11-09起清单为9份Python源码加R3配置，共10个文件，包含`F8_room_helpers.py`，见[正式清单](room_animation_final.md)。容器重新创建会清除容器/tmp，必须之后再复制脚本进去。本文保留GPU修复依据，当前基线整理不执行重建或新渲染；新源码不能续跑旧版本任务。

远程SSH，部署目录：

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --no-deps --force-recreate --no-build --pull never app-server
docker compose cp /tmp/room8_gpu_code app-server:/tmp/
```

第一条必须成功才继续。只重新创建app-server，后端短暂中断；MinIO/PostgreSQL不重启，原数据卷继续沿用，不需要镜像build。以后部署时保留这份覆盖文件并继续用两个-f参数，直到生产compose本身已包含图形能力修复。

继续使用run_room_animation.py的final/final/overview/--direct-final参数，但脚本和配置路径改为/tmp/room8_gpu_code，选择同一已验收基础资产；使用新任务，不传--resume旧CPU目录。第一帧仍属于正式576帧，不是新增样帧/短片测试。若实际上下文非NVIDIA，第一帧保留在attempt目录，立即失败，查看renderer.json，不重复启动。

成功证据：blender.log出现renderer=...NVIDIA L20...且software_rendering_suspected=False；manifest.renderer及worker_timing.json记录相同信息；宿主机nvidia-smi可观察Blender进程/显存/负载。第一帧完成前不能只凭nvidia-smi -L宣布GPU渲染已修复。

不在容器安装NVIDIA驱动，不猜测宿主机驱动版本，不设CUDA_VISIBLE_DEVICES来冒充EEVEE图形设备选择。若重建后仍无NVIDIA EGL库，需检查宿主机驱动与容器运行时，暂不继续正式渲染。

覆盖文件回退：先停止本次任务，再用原始compose文件单独重新创建app-server；挂载数据保留。容器/tmp会再次清空，脚本可从宿主机恢复；软件后端仍会被新版正式入口拒绝。

````

</details>
