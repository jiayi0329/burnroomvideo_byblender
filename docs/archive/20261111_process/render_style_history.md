# render_style_history.md

2026-11-11合并的历史原文。来源提交：`fd3b3724a6526040f09dee8dd5eab57e64e33af3`。以下旧命令、路径、门禁和“当前状态”仅用于追溯，不作为运行指令。当前说明从[文档索引](../../README.md)进入。原文以Markdown源码保存，换行统一为LF；manifest.json记录原路径、工作副本SHA、Git blob及合并后字节范围，可提取校验。

<details>
<summary>docs/room_style_round1.md</summary>

````markdown
# Room8 第一轮：只做火焰、烟雾、光照对比静帧

> 第4批后下文平铺上传命令仅供归档追溯，不能用于当前app兼容文件。完整包安装见[迁移说明](room_engine_migration.md)，本轮不重渲染。

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

````

</details>

<details>
<summary>docs/room_style_round2.md</summary>

````markdown
# Room8 第二轮：更大、更厚的火焰与深灰黑上升烟柱

> 第4批后下文平铺上传命令仅供归档追溯，不能用于当前app兼容文件。完整包安装见[迁移说明](room_engine_migration.md)，本轮不重渲染。

2026-11-09兼容更新：上传清单补入`F8_room_helpers.py`。本文为历史轮次复现依据，本轮不重新渲染。

第三轮现已针对背景与烟雾可读性微调，当前操作见[room_style_round3.md](room_style_round3.md)。本文及第二轮JSON保留供复现对比。

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
scp -P 7777 .\app\F8_room_demo.py .\app\F8_room_fire_style.py .\app\room_fire_config.py .\app\room_fire_round2.json .\app\F8_prepare_room_asset.py .\app\F8_room_helpers.py .\app\room_demo_plan.py zhaojy@172.25.76.201:/tmp/
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
docker compose cp /tmp/F8_room_helpers.py app-server:/tmp/F8_room_helpers.py
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

````

</details>

<details>
<summary>docs/room_style_round3.md</summary>

````markdown
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

## ① 本地 PowerShell：准备完整代码包

2026-11-09第4批：先按[完整代码包说明](room_engine_migration.md)上传/解压并设置`engine_root`，不能再上传平铺脚本。第三轮配置内容未改，本轮目录整理不重渲染。

未来明确授权重新运行时，在项目目录打包，再通过WinSCP上传并解压到独立目录：

```powershell
cd D:\burnroomvideo_byblender
.\release\scripts\build.ps1
```

无需重建镜像、重新打包或重做资产。不在本地运行Docker/Blender。

## ② 远程 SSH：复制文件

先完成迁移说明中的独立解压，保持同一个SSH会话和`engine_root`变量。不要再复制单个app脚本。任意命令报错先停止：

```bash
cd ~/burnroom-prod/burnroom-deploy-package
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
  --python "$engine_root/render_engine/blender/F8_room_demo.py" \
  -- \
  --asset "$asset" \
  --mode samples \
  --config "$engine_root/configs/render/room_fire_round3.json" \
  --points /app/data/KK-EEz16cmU14/points.json
```

不要调用旧POST渲染接口。本次不启动4秒短片或完整视频。

## ⑤ WinSCP：下载审核

日志会打印`output=/app/data/.../style_round3/<UTC_UUID>`。宿主机对应：

`/data/zhaojy/burnroom-data/app-data/KK-EEz16cmU14/rooms/Room8/<基础版本>/style_round3/<UTC_UUID>/`

下载overview_1s.png / overview_3.5s.png / overview_6s.png，closeup_22_1s.png / closeup_22_3.5s.png / closeup_22_6s.png，以及effective_settings.json、sample_manifest.json、repair_report.json。

成功状态应为awaiting_visual_review、六图齐全、guarded_files_unchanged=true。审核：房间结构可辨、火焰仍最亮、烟有黑灰主体和可读边缘、6秒烟柱更清楚，不能整体发灰或烟变白。截图效果、性能仍需远端实际验证，测试不是视觉通过。失败时保留failure.json/已完成图片，排错后独立重跑。

独立保存requested_config.json、room_timeline.json和display.blend；基础room.blend/glb、模型/贴图/核验文件、旧视频与前两轮样帧不覆盖，不修改数据库。配置仍可显式选择前两轮；默认配置现为第三轮。

````

</details>
