# Room8 R3 火焰、烟雾与灯光

更新：2026-11-11。当前唯一风格基线为[room_fire_round3.json](../../configs/render/room_fire_round3.json)。本页独立说明当前效果，不要求先阅读R1/R2；三轮原始记录见[风格历史](../archive/20261111_process/render_style_history.md)。本文不授权新渲染或调参。

## 配置与实现

| 内容 | 实际文件 |
| --- | --- |
| 公共请求配置 | configs/render/room_fire_round3.json |
| 配置校验、火舌/烟柱几何和曲线 | render_engine/effects/room_fire_config.py |
| Blender节点、灯光及设置回读 | render_engine/blender/F8_room_fire_style.py |
| 六张样帧入口 | render_engine/blender/F8_room_demo.py，mode=samples |
| 绝对时间动画 | render_engine/blender/F8_room_animation.py，由安全启动器调用 |

JSON的art/events/quality分别描述艺术、事件和静帧质量；动画preset可覆盖分辨率/FPS等质量项，不应改变批准的艺术风格。参数真相源是JSON和effective_settings.json，不是文档中的手抄数值。

## 当前已实现的视觉方案

以下数值直接核对当前R3配置，作为阅读索引；修改应另立任务，并处理批准指纹与回归。

| 项目 | 当前值/行为 |
| --- | --- |
| 火舌 | 主火点4条，次级点2条，固定种子731；曲线偏斜、错落高度、向上噪声和闪烁 |
| 名义高度/半径 | 主点2.975m/0.261m，次级1.625m/0.13m；实际尺寸还受随机错落及时间曲线影响 |
| 火体密度/发光系数 | 1.4/11，分别驱动；密度有径向分层和0.65噪声保底 |
| 火焰颜色 | 暗橙红边缘、橙色外层、橙黄主体、小范围亮黄核心；线性节点颜色不等于最终像素颜色 |
| 动态 | 闪烁3.2Hz、幅度0.14；不是CFD或Mantaflow模拟 |
| 烟形态 | 不规则卷曲烟柱，14圈×16边，窄底向上扩散；单独计算成长、浓度和消散 |
| 烟密度/吸收 | 密度9，吸收倍率0.6；不发光 |
| 烟颜色 | 主体线性RGB 0.008/0.01/0.012，薄层0.045/0.048/0.052，以深灰黑为主 |
| 烟生命周期 | 相对点燃年龄6秒浓度到1，10秒仍为1，20秒降到0；火焰减弱后烟继续保留 |
| 环境 | Exposure=-0.35；世界强度0.22，背景线性RGBA 0.035/0.04/0.05/1 |
| 三面光 | Key/Fill/Rim为500/190/340W；填充与侧后灯体积倍率0.35/0.7，侧后目标上移1.6m |
| 色彩管理 | sRGB、AgX、AgX - Medium High Contrast、Gamma=1；不添加Bloom |
| 静帧质量 | 960×540、12fps时间映射、32采样；体积tile字符串"4"、48步、阴影8步 |
| 传播 | Room8内部13点重新BFS，层间1.5秒；32、42排除，不经外部点绕行 |

世界背景节点并不等于已启用Eevee间接环境照明。表面灯光与体积照明分开控制，以保持深色烟层次；不能为了看清烟而把整体重新打白。

## 六张静帧的当前入口

仅在明确需要重新出图时执行。先按[动画指南的完整包步骤](animation.md#完整代码包与执行位置)获得容器内code_root；保持它指向完整且固定的安装目录。远程SSH、已有Compose目录、同一会话设置：

```bash
asset='/app/data/KK-EEz16cmU14/rooms/Room8/20261102T025550Z-7f677509/asset'
points='/app/data/KK-EEz16cmU14/points.json'
docker compose exec -T app-server blender --background --factory-startup --python-exit-code 1 --python "$code_root/render_engine/blender/F8_room_demo.py" -- --asset "$asset" --points "$points" --config "$code_root/configs/render/room_fire_round3.json" --mode samples
```

入口读取既有基础资产，写独立style_round3版本，不覆盖旧图。输出overview与closeup_22的1/3.5/6秒六图、requested_config.json、effective_settings.json、sample_manifest.json、repair_report.json及派生display.blend。以终端输出的具体目录为准，不用修改时间挑“最新”冒充已验收版本。

人工检查火焰颜色/轮廓、主次火点、黑灰烟层次、房间可读性及穿墙/漂浮。静帧不能证明动画连续性；技术检查也不能代替人工视觉审核。

## 保留限制

- R3已被接受为Room8演示风格，V1暂不重渲染。
- 火焰在各点激活后约8秒退场；最后一层3秒激活，因此不同点退场时间不同，后段以烟为主。
- 没有Hybrid贴地前沿、复杂顶棚积烟或按真实墙面裁切火烟体积。
- R1/R2 JSON内容不同且仍用于回归，继续保留；旧三份操作MD已合并归档。
- 后续生命周期增强单独排期，不因本次文档整理修改R3。
