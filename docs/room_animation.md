# A阶段：冻结第三轮风格的Room8短片与性能验收

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
