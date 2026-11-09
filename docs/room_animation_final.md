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
