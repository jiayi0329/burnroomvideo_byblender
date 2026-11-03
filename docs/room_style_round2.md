# Room8 第二轮：更大、更厚的火焰与深灰黑上升烟柱

对应PRD 2.2 / architecture 3.2，2026-11-03。只生成六张静帧，先审核；不进入短片或完整视频。

## 本轮改变与保留

| 参数 | 第一轮 | 第二轮 |
|---|---|---|
| 22号名义火舌高度 / 半径 | 1.7 / 0.18m | 2.975 / 0.261m（1.75 / 1.45倍） |
| 次级名义高度 / 半径 | 1.25 / 0.13m | 1.625 / 0.13m（高度1.3倍） |
| 主/次级火舌数，四色，发光 | 4/2，黄橙至暗橙红，11 | 保持；同种子和形态算法 |
| 火体密度系数 | 0.45，噪声×高度 | 1.4，另乘径向厚度和主体噪声保底0.65 |
| 径向密度权重（边缘/外层/主体/核心） | 无 | 0.06 / 0.45 / 1 / 0.9；不改变发光输入 |
| 烟体网格 | UV球体 | 14圈×16边闭合卷曲烟柱；基底半径比0.2，往上扩散，顶端收束 |
| 烟散射颜色（线性RGB） | 浅部0.075～0.09 | 薄处0.028/0.03/0.033；厚处0.008/0.01/0.012 |
| 烟密度系数，独立吸收 | 7，无额外吸收 | 9，另加0.6倍密度的中性VolumeAbsorption，不发光 |
| 烟浓度包络（相对激活年龄） | 5秒到峰值 | 3.5秒0.65、6秒1、10秒1、14秒0.7、20秒0 |
| 烟成长包络 | 3.5秒约0.83、6秒约1.03 | 3.5秒0.8、6秒1.1、10秒1.3 |
| 烟主点半径 / 高度公式 | 球体整体上移 | 0.85×成长；2.8×成长+0.22×年龄（m），次级乘0.78 |
| 烟上升方式 | 球体中心上移、噪声 | 烟底固定在火源+名义火高×0.22；上体拉伸增长、4D噪声向上平移0.6归一化单位/秒 |
| 火点灯 | 80W，截止距离4m | 80W不变，截止5m，体积照亮系数0.55 |
| 环境/面光/曝光 | 世界0.15，500/150/300W，-0.5 | 保持；仅面光体积照亮系数0.3，表面照明不改 |
| 22号中近景 | 35mm，目标高0.9m | 30mm，目标高1.3m；位置不变，容纳放大火焰 |

以上高度是随机错落及时间包络前的系数；逐舌实际参数记录在effective_settings/repair_report。密度权重是节点系数，不是固定像素不透明度。火焰保留高度衰减和噪声边缘；增密不会联动提高发光。单火点仍为1火体+1烟体，共26体积对象；质量设置、13点BFS及1.5秒层间不改，32/42排除，不含Hybrid/积顶/CFD。更大体积可能增加遮挡和耗时，须远端看图，不能靠测试判定视觉通过。

`Light.volume_factor` 是Blender4.2对体积照明的独立倍率，赋值后读回，失败即中止；不是关闭烟的吸收或修改面光功率。见[官方API](https://docs.blender.org/api/4.2/bpy.types.Light.html#bpy.types.Light.volume_factor)。新烟柱有非凸轮廓，与火舌一样用ACCURATE体积交界；旧球烟的FAST仅保留在显式第一轮分支。

## ① 本地 PowerShell：测试、上传

在项目目录执行；本地不运行Docker或Blender：

```powershell
cd D:\burnroomvideo_byblender
& 'C:\Users\86182\AppData\Local\Programs\Python\Python313\python.exe' -m unittest test.test_room_fire_round2 test.test_room_fire_config test.test_room_fire_style test.test_room_demo test.test_room_demo_plan -v
scp -P 7777 .\app\F8_room_demo.py .\app\F8_room_fire_style.py .\app\room_fire_config.py .\app\room_fire_round2.json .\app\F8_prepare_room_asset.py .\app\room_demo_plan.py zhaojy@172.25.76.201:/tmp/
```

只上传代码/配置，不重建镜像，不重新裁切或上传基础模型。六个文件保持同目录同版本。

## ② 远程 SSH：复制后生成六张静帧

逐行执行，任意报错先停。不要调用旧POST渲染接口。

```bash
cd ~/burnroom-prod/burnroom-deploy-package
docker compose cp /tmp/F8_room_demo.py app-server:/tmp/F8_room_demo.py
docker compose cp /tmp/F8_room_fire_style.py app-server:/tmp/F8_room_fire_style.py
docker compose cp /tmp/room_fire_config.py app-server:/tmp/room_fire_config.py
docker compose cp /tmp/room_fire_round2.json app-server:/tmp/room_fire_round2.json
docker compose cp /tmp/F8_prepare_room_asset.py app-server:/tmp/F8_prepare_room_asset.py
docker compose cp /tmp/room_demo_plan.py app-server:/tmp/room_demo_plan.py
asset=$(docker compose exec -T app-server python3 -c 'from pathlib import Path; items=list(Path("/app/data/KK-EEz16cmU14/rooms/Room8").glob("*/asset/manifest.json")); assert items,"No completed base asset found"; print(max(items,key=lambda p:p.stat().st_mtime).parent)')
printf 'Base asset: %s\n' "$asset"
docker compose exec -T app-server blender --background --factory-startup --python-exit-code 1 --python /tmp/F8_room_demo.py -- --asset "$asset" --mode samples --config /tmp/room_fire_round2.json --points /app/data/KK-EEz16cmU14/points.json
```

`asset`自动选择最近的完整基础资产目录，执行前核对打印路径是否就是第一轮使用的版本；若不是，在当前SSH会话将asset手动设为第一轮对应的容器内asset绝对路径。入口仍会核对manifest/validation/文件指纹并重新派生展示场景。此前若有已确认的`--drop-component ID`，须显式沿用；默认不删孤立块。展示墙高仍1.1m。

支持显式传旧room_fire_round1.json生成新的第一轮对比版本；原配置/已有六图保持。默认配置是第二轮，输出路径取配置revision，不覆盖上次运行。

## ③ WinSCP：下载并审核

日志末行示例：`[room-demo] mode=samples output=/app/data/.../style_round2/<UTC_UUID> base_unchanged=true`。

宿主机目录为`/data/zhaojy/burnroom-data/app-data/KK-EEz16cmU14/rooms/Room8/<基础版本>/style_round2/<UTC_UUID>/`。

下载：

- overview_1s.png、overview_3.5s.png、overview_6s.png。
- closeup_22_1s.png、closeup_22_3.5s.png、closeup_22_6s.png。
- effective_settings.json：回读渲染/色彩/照明设置、节点层权重/额外吸收、生成的逐点火舌参数；effects.smoke_samples为公式预测，不冒充画面分析。
- sample_manifest.json：status应为awaiting_visual_review；六项逐图耗时、SHA、实际机位、灯/体积系数、材质密度/发光包络、烟柱变换及世界Z包围盒。
- requested_config.json、repair_report.json：请求值、来源/脚本指纹、变更说明、受保护文件不变与总耗时。

独立room_timeline.json与display.blend仅为新派生文件；旧room.blend/glb、贴图、原始模型、核验文件、视频、第一轮图片均不覆盖，不访问数据库。failure.json出现时先排错，不能将部分出图当成通过。

审核重点：主火更大更厚但边缘仍透、非白块；近景轮廓不被裁掉；浓烟深灰黑、基底窄而上部不规则扩散，6秒比3.5秒更明显；总览仍看得清房间/主火且没有整体过曝。静帧只能检查不同时间状态，运动连续性等用户通过后再用短片验收。本次不自动启动动画。
