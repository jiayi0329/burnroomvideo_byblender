# Room8 第一轮：只做火焰、烟雾、光照对比静帧

2026-11-09兼容更新：上传清单补入`F8_room_helpers.py`。本文为历史轮次复现依据，本轮不重新渲染。

当前默认入口已进入[第二轮静帧优化](room_style_round2.md)。本文及room_fire_round1.json保留作为第一轮记录/显式对比配置；不是当前第二轮参数说明。

2026-11-03 用户确认实施。当前 F8-D 仅允许 inspect/samples，short 已禁用，不执行4秒短片或313帧视频。Hybrid没有实现；仍使用原13个内部点的BFS，32/42排除，层间1.5秒。基础资产、扫描模型、人工核验、旧图和视频、数据库均不写。

## 配置与实现

`app/room_fire_round1.json` 是完整请求配置：

| 组 | 本轮主要值 |
|---|---|
| art 光照 | Exposure=-0.5，世界0.15，面光500/150/300W，尺寸3/4/2.5m |
| art 火焰 | 主4条/次2条，高度和半径随机错落、曲线偏斜、向上流动、3.2Hz/14%闪烁；每点合为一个火焰对象 |
| art 颜色 | 四层黄橙核心/橙黄主体/橙外层/暗橙红边缘，少量核心；发光系数11和密度0.45独立，不是密度×9 |
| art 烟 | 深灰黑到灰黑，系数7，上升0.35m/s；独立浓度/成长曲线，激活后5～8秒浓度保持，不随火焰缩回 |
| events | 现有13点BFS和火焰慢成长曲线，1.5秒层间；禁止配置改变32/42排除 |
| quality | AgX、Medium High Contrast、Gamma1；960×540、12fps时间映射、渲染32采样、体积4档/48步、体积阴影8步；不使用Bloom/合成器/景深/运动模糊 |

JSON中的颜色是线性节点RGBA，不是最终显示像素值。`room_fire_config.py`为纯Python配置校验/曲线/火舌网格，`F8_room_fire_style.py`为Blender内部辅助、没有独立执行入口。使用Blender4.2的ACCURATE体积交界处理合并火舌内表面，深度预算16；这有额外显存成本，实际耗时以报告为准。[Blender 4.2体积交界说明](https://docs.blender.org/api/4.2/bpy.types.Material.html#bpy.types.Material.volume_intersection_method)

每项关键渲染设置先赋值再读回；不支持、枚举不符或被截断则报错，并保留failure.json，不静默沿用旧blend设置。源码测试不等于远端API验证。配置可后续复用，但本轮事件策略锁定。没有新增贴地前沿或体积多边形遮罩，不能把点位排除描述成效果边界完全约束。

## 本地 PowerShell：上传6个文件

在 D:\burnroomvideo_byblender，先完成本地测试（实际Python路径按本机安装）：

```powershell
& 'C:\Users\86182\AppData\Local\Programs\Python\Python313\python.exe' -m unittest test.test_room_fire_config test.test_room_fire_style test.test_room_demo test.test_room_demo_plan -v
scp -P 7777 .\app\F8_room_demo.py .\app\F8_room_fire_style.py .\app\room_fire_config.py .\app\room_fire_round1.json .\app\F8_prepare_room_asset.py .\app\F8_room_helpers.py .\app\room_demo_plan.py zhaojy@172.25.76.201:/tmp/
```

无需重新打包、重建镜像或上传模型。不要只上传F8-D主脚本，辅助文件和JSON必须同目录、同版本。

## 远程 SSH：复制代码并生成六张图

同一SSH会话逐行执行；任何一条报错先停止，不继续启动Blender：

```bash
cd ~/burnroom-prod/burnroom-deploy-package
docker compose cp /tmp/F8_room_demo.py app-server:/tmp/F8_room_demo.py
docker compose cp /tmp/F8_room_fire_style.py app-server:/tmp/F8_room_fire_style.py
docker compose cp /tmp/room_fire_config.py app-server:/tmp/room_fire_config.py
docker compose cp /tmp/room_fire_round1.json app-server:/tmp/room_fire_round1.json
docker compose cp /tmp/F8_prepare_room_asset.py app-server:/tmp/F8_prepare_room_asset.py
docker compose cp /tmp/F8_room_helpers.py app-server:/tmp/F8_room_helpers.py
docker compose cp /tmp/room_demo_plan.py app-server:/tmp/room_demo_plan.py
asset=$(docker compose exec -T app-server python3 -c 'from pathlib import Path; items=list(Path("/app/data/KK-EEz16cmU14/rooms/Room8").glob("*/asset/manifest.json")); assert items,"No completed base asset found"; print(max(items,key=lambda p:p.stat().st_mtime).parent)')
printf 'Base asset: %s\n' "$asset"
docker compose exec -T app-server blender --background --factory-startup --python-exit-code 1 --python /tmp/F8_room_demo.py -- --asset "$asset" --mode samples --config /tmp/room_fire_round1.json --points /app/data/KK-EEz16cmU14/points.json
```

如先前展示修正版使用了已确认的 --drop-component ID，本次须显式沿用同一参数；默认不隐藏任何未确认分量。展示墙高仍为1.1m，未改变房间平面裁切或基础几何；基础room.blend不覆盖。

脚本会打印每张图的渲染秒数，最后打印：

```text
[room-demo] mode=samples output=/app/data/.../style_round1/<UTC_UUID> base_unchanged=true
```

没有动画渲染调用，不会自动进入短片。

## WinSCP 下载与验收

容器路径 `/app/data/` 对应宿主机 `/data/zhaojy/burnroom-data/app-data/`。新目录在原成功版本旁边的 `style_round1/<UTC_UUID>/`，与旧asset/display_versions分开。

| 文件 | 内容 |
|---|---|
| overview_1s.png / overview_3.5s.png / overview_6s.png | 同一房间总览、相同时间点 |
| closeup_22_1s.png / closeup_22_3.5s.png / closeup_22_6s.png | 22号中近景，35mm透视；相同事件场景和光照，不人为移除其他点 |
| requested_config.json | 本次请求的全部艺术/事件/质量参数 |
| effective_settings.json | Blender版本、实际回读色彩管理/采样/体积/输出及世界/面光 |
| sample_manifest.json | 每张图实际机位、帧号、灯能量、密度/发光控制值、耗时和指纹；成功后status=awaiting_visual_review |
| repair_report.json | 配置/代码/输入指纹、火舌数量与形态/相位、实际材质/灯设置、保护文件校验、总耗时/逐图耗时 |
| room_timeline.json | 独立时序；不覆盖场景根目录timeline |
| display.blend | 仅新派生场景，包含效果关键帧供检查；不代表已生成动画 |
| failure.json | 仅失败时出现；可保留已经输出的样帧，不能据此宣称全部通过 |

本轮审核：主火有多条错落尖舌，核心少量黄橙、边缘暗橙红，不能是白块/浅色雾柱；主火在6秒减弱时烟仍保留；总览有暗部和局部火光，中近景可辨主火轮廓。对比图仅改变机位，时刻/风格一致。实际结果以远端图片为准，离线没有运行Blender或生成这些新图。

先下载六图及三份设置/样帧/修复报告给用户审核。下一轮Hybrid先做22号到少量邻点、路径与效果受多边形约束，通过后扩展；本轮不实现、不启动。
