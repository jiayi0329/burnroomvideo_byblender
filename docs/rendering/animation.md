# Room8 动画与视频运行指南

更新：2026-11-11。合并原动画、正式出片、相机修复和GPU说明。Room8 V1已交付，本轮不运行任何渲染或部署；本页命令供之后明确执行时使用。历史过程见[动画历史](../archive/20261111_process/animation_history.md)，实测与资产指纹见[RELEASES](../RELEASES.md)。

## 正式入口与输出契约

普通Python入口为render_engine/jobs/run_room_animation.py；它负责预检、锁、GPU冲突检查、Blender子进程、编码与失败保留。Blender worker为render_engine/blender/F8_room_animation.py，不应绕过启动器单独运行。

| 参数 | 当前含义 |
| --- | --- |
| --stage camera_check | 默认，仅从动画入口输出总览3.5秒检查图，不编码视频 |
| --stage short --preset test | 4秒/48帧、960×540、12fps短片，并保留额外关键帧检查 |
| --stage final --preset final | 正式档1280×720、24fps；当前Room8时序与生命周期得到24秒/576帧 |
| --camera-mode overview | 默认独立正交斜视总览，覆盖Room8；closeup为明确选择的细节镜头 |
| --config | 默认安装目录内configs/render/room_fire_round3.json |
| --direct-final | 显式直接正式出片授权，当前契约要求final档及overview；不自动取得授权 |
| --approval | 绑定短片、输入及配置的人工审批文件，属于另一条正式门禁路径 |
| --resume | 只对同一路径、同代码/配置/资产的已有任务补缺帧 |
| --report-job | 只读已有相机/耗时证据，不创建渲染任务 |

两种正式门禁保留：有效审批，或显式direct-final。生成短片不会自动启动正式视频。当前不强制重跑短片来复现已接受的V1风格，也不因为文档示例而自动执行final。

## 完整代码包与执行位置

本地Windows仅编辑、离线测试、打包。PowerShell项目根目录：

```powershell
.\deploy\scripts\build.ps1
```

安装包仍在release/out。WinSCP上传选定唯一文件名到服务器/tmp；不上传平铺app脚本，不覆盖数据盘。下面远程SSH命令仅将包安装到容器内唯一临时目录，看帮助；不会启动渲染。先确认app-server运行，使用同一SSH会话，替换package_name占位值：

```bash
cd ~/burnroom-prod/burnroom-deploy-package
package_name='替换为实际安装包文件名.tar.gz'
install_id=$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')
install_root="/tmp/room8-engine-$install_id"
docker compose exec -T app-server mkdir "$install_root"
docker compose cp "/tmp/$package_name" "app-server:$install_root/package.tar.gz"
docker compose exec -T app-server tar -xzf "$install_root/package.tar.gz" -C "$install_root"
code_root="$install_root/burnroom-deploy-package"
docker compose exec -T app-server python3 "$code_root/render_engine/jobs/run_room_animation.py" --help
printf 'Code root: %s\n' "$code_root"
```

逐条检查，任何失败即停止。code_root是容器内完整安装根，不是宿主机目录；变量跨SSH会话不会保留。不要用独立/tmp安装测试代替正式服务升级；临时目录也必须保留到任务完成，续跑不能换路径。

## 正式运行示例（另行授权后）

选取已核验资产版本，不按mtime自动挑选。以下使用V1基础资产；启动器仍核验来源、点位和配置。已存在任务会先检查冲突，不自动终止其他任务。当前操作不得调用旧POST /api/render代替本入口。

```bash
asset='/app/data/KK-EEz16cmU14/rooms/Room8/20261102T025550Z-7f677509/asset'
points='/app/data/KK-EEz16cmU14/points.json'
launch_log="$HOME/burnroom-prod/room8-final-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
nohup docker compose exec -T app-server python3 -u "$code_root/render_engine/jobs/run_room_animation.py" --asset "$asset" --points "$points" --config "$code_root/configs/render/room_fire_round3.json" --stage final --preset final --camera-mode overview --direct-final > "$launch_log" 2>&1 < /dev/null &
printf 'Launch log: %s\n' "$launch_log"
tail -n 30 "$launch_log"
```

只启动一次，Shell后台PID不代表成功。日志会输出job和attempt的具体路径。按实际输出赋值后查看，不原样使用占位符：

```bash
job='/app/data/KK-EEz16cmU14/rooms/Room8/render_jobs/替换为实际run_id'
attempt='替换为实际attempt_id'
docker compose exec -T app-server cat "$job/status.json"
docker compose exec -T app-server tail -n 40 -f "$job/attempts/$attempt/blender.log"
```

Ctrl+C只结束这个tail观察命令。SSH断开后原nohup任务可继续，但电脑关机不代表服务器任务已结束；重新进入Compose目录检查状态。

## GPU与镜头验收

Blender4.2 EEVEE需要NVIDIA图形运行库，单有CUDA或nvidia-smi输出不足以证明GPU渲染。生产模板使用runtime=nvidia、NVIDIA_VISIBLE_DEVICES=all和compute,utility,graphics；GPU覆盖文件清除旧gpus DeviceRequests。真实NVIDIA上下文证据由正式任务首帧renderer记录，软件/未知后端会拒绝继续；若失败保留证据，请管理员核对宿主机库和容器注入，不照历史中间方案盲目改配置。

overview与closeup有独立相机对象、data和目标；manifest记录实际类型、位置、目标、尺度。检查总览应包含房间轮廓及主要传播区域，不能因名字是overview就假定构图正确。GPU温度85°C告警、90°C终止本任务；现有锁只约束协作入口，不是共享服务器全局调度器。

## 产物、失败和续跑

| 任务内文件 | 核对内容 |
| --- | --- |
| config_snapshot.json | 资产/源码/配置/相机/preset/授权绑定 |
| room_timeline.json | Room8内部13点BFS，22号0秒，其余层1.5/3秒，32/42排除 |
| status.json | preparing/rendering/encoding；技术完成为awaiting_visual_review |
| frames/ | 已登记PNG与指纹；final应有576张视频帧 |
| attempts/<attempt>/ | blender.log、GPU采样、worker耗时、编码/解码及失败证据 |
| render_manifest.json | 实际相机、逐帧时刻/耗时、来源及产物 |
| timing_report.json | 本次准备、渲染、编码、总耗时及采样范围；续跑保留原帧耗时 |
| fire_final.mp4 / video_receipt.json | H.264/yuv420p/faststart；帧数、时长、分辨率及完整解码验证 |

WinSCP对应宿主机根为/data/zhaojy/burnroom-data/app-data，容器根为/app/data。下载指定任务，实际播放到结尾；MP4存在或Blender quit都不能替代回执和人工审核。V1约6分钟实测仅适用于当次任务，不承诺其他资产或环境耗时。

失败保留日志、帧和尝试目录。同一新版本任务续跑时，在原启动命令附加`--resume "$job"`，保持stage/preset/camera/授权等完全一致；先确认原进程已停止。当前29文件源码清单不能续跑旧28/40文件或V1原始任务，禁止改签名、删锁或删坏帧强行通过。改代码、安装路径或资产后应新建任务，V1复现使用归档版本。
