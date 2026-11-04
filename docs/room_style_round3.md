# Room8 第三轮：背景可读、黑灰烟与背景分离

2026-11-03，对应PRD 2.2 / architecture 3.2。沿用第二轮火焰，只输出相同六张静帧等待审核。

## 参数变化

| 项目 | 第二轮 | 第三轮候选 |
|---|---|---|
| 曝光 | -0.5 | -0.35（+0.15档，约11%线性曝光增益） |
| 世界强度 | 0.15 | 0.22 |
| 背景线性RGB | 0.02 / 0.025 / 0.03 | 0.035 / 0.04 / 0.05，仍为暗灰背景 |
| 主面光 | 500W，体积倍率0.3 | 不变 |
| 填充光 | 150W，体积倍率0.3 | 190W，体积倍率0.35 |
| 侧后光 | 300W，体积倍率0.3，照向房间中心 | 340W，体积倍率0.7，目标改为照明中心上方1.6m |
| 烟薄层线性RGB | 0.028 / 0.03 / 0.033 | 0.045 / 0.048 / 0.052 |
| 黑灰烟主体、密度、吸收、形态与成长 | 第二轮配置 | 全部不变 |
| 火焰、火点灯、BFS、相机、质量 | 第二轮配置 | 全部不变 |

通过原有侧后光突出烟的薄边缘，不增加灯数量，不给烟加发光，不重新改火焰配色或结构。世界节点主要改变可见背景，不能把调世界强度等同于开启Eevee间接环境照明；房间结构由填充面光提亮。曝光仍会轻微影响火焰亮度，因此需要看六图确认未过曝。烟柱运动逻辑和6秒成长保持第二轮，静帧不证明运动连续性。

effective_settings.json回读背景、色彩管理、逐灯能量/体积倍率/位置/目标/旋转以及火烟材质。sample_manifest.json继续记录六图实际帧号、机位、灯能量、体积控制、烟对象包围盒和耗时。没有加入Hybrid、顶棚积烟或动画渲染。

## ① 本地 PowerShell：上传六个文件

在项目目录完整复制下面一块执行。文件数组用于避免长命令被手工换行破坏：

```powershell
cd D:\burnroomvideo_byblender
$styleFiles = @(
    '.\app\F8_room_demo.py'
    '.\app\F8_room_fire_style.py'
    '.\app\room_fire_config.py'
    '.\app\room_fire_round3.json'
    '.\app\F8_prepare_room_asset.py'
    '.\app\room_demo_plan.py'
)
scp -P 7777 $styleFiles zhaojy@172.25.76.201:/tmp/
```

无需重建镜像、重新打包或重做资产。不在本地运行Docker/Blender。

## ② 远程 SSH：复制文件

逐行执行，任意命令报错先停止：

```bash
cd ~/burnroom-prod/burnroom-deploy-package
docker compose cp /tmp/F8_room_demo.py app-server:/tmp/F8_room_demo.py
docker compose cp /tmp/F8_room_fire_style.py app-server:/tmp/F8_room_fire_style.py
docker compose cp /tmp/room_fire_config.py app-server:/tmp/room_fire_config.py
docker compose cp /tmp/room_fire_round3.json app-server:/tmp/room_fire_round3.json
docker compose cp /tmp/F8_prepare_room_asset.py app-server:/tmp/F8_prepare_room_asset.py
docker compose cp /tmp/room_demo_plan.py app-server:/tmp/room_demo_plan.py
```

## ③ 同一个远程 SSH 会话：确认基础资产

整块复制，保留PY标记独占一行，不给标记加空格：

```bash
asset=$(
docker compose exec -T app-server python3 - <<'PY'
from pathlib import Path
root = Path('/app/data/KK-EEz16cmU14/rooms/Room8')
items = list(root.glob('*/asset/manifest.json'))
assert items, 'No completed base asset found'
latest = max(items, key=lambda p: p.stat().st_mtime)
print(latest.parent)
PY
)
printf 'Base asset: %s\n' "$asset"
```

确认打印的asset目录就是第二轮使用的版本。若有多个版本，请将asset设为第二轮基础资产容器路径后再运行。若之前使用已确认的`--drop-component ID`，下方命令显式沿用同一参数；默认不隐藏任何孤立块。原展示墙高仍1.1m。

## ④ 同一个远程 SSH 会话：生成六张静帧

完整复制，保留每行末尾反斜杠（其后不要加空格）：

```bash
docker compose exec -T app-server blender \
  --background \
  --factory-startup \
  --python-exit-code 1 \
  --python /tmp/F8_room_demo.py \
  -- \
  --asset "$asset" \
  --mode samples \
  --config /tmp/room_fire_round3.json \
  --points /app/data/KK-EEz16cmU14/points.json
```

不要调用旧POST渲染接口。本次不启动4秒短片或完整视频。

## ⑤ WinSCP：下载审核

日志会打印`output=/app/data/.../style_round3/<UTC_UUID>`。宿主机对应：

`/data/zhaojy/burnroom-data/app-data/KK-EEz16cmU14/rooms/Room8/<基础版本>/style_round3/<UTC_UUID>/`

下载overview_1s.png / overview_3.5s.png / overview_6s.png，closeup_22_1s.png / closeup_22_3.5s.png / closeup_22_6s.png，以及effective_settings.json、sample_manifest.json、repair_report.json。

成功状态应为awaiting_visual_review、六图齐全、guarded_files_unchanged=true。审核：房间结构可辨、火焰仍最亮、烟有黑灰主体和可读边缘、6秒烟柱更清楚，不能整体发灰或烟变白。截图效果、性能仍需远端实际验证，测试不是视觉通过。失败时保留failure.json/已完成图片，排错后独立重跑。

独立保存requested_config.json、room_timeline.json和display.blend；基础room.blend/glb、模型/贴图/核验文件、旧视频与前两轮样帧不覆盖，不修改数据库。配置仍可显式选择前两轮；默认配置现为第三轮。
