# Room8 引擎

2026-11-09第4批迁移。只迁移已有实现，不宣称支持其他房间，不改R3艺术参数、BFS、裁切算法或真实资产。

| 目录 | 内容 |
| --- | --- |
| geometry/ | OBJ/MTL/坐标/来源读取、UV裁切、候选生成，以及第6批提取的只读floorplan_alignment分析 |
| propagation/room_demo_plan.py | 现有内部子图BFS及展示分量分析；暂不继续拆分或改算法 |
| effects/room_fire_config.py | 纯参数校验、绝对时间曲线和程序化火舌/烟柱几何 |
| blender/ | B资产生成、D静帧、E动画worker，以及材质/相机辅助；仅Blender可导入 |
| jobs/ | 普通Python启动器、锁、GPU采样、编码、报告与续跑契约 |
| paths.py | 按安装位置寻址、默认配置和完整源码指纹清单 |

普通Python入口：`python -m render_engine.jobs.run_room_animation --help`。候选入口：`python -m render_engine.geometry.prepare_room_candidate --help`。原`python -m app.run_room_animation`、`python app/run_room_animation.py`及候选入口继续可用。

Blender通过`--python render_engine/blender/F8_room_animation.py`执行worker，实际任务仍须由安全启动器创建，不能绕过任务锁直接运行。B/D也保留原app脚本入口。所有包初始化文件均不导入bpy；jobs/effects/geometry/propagation不依赖Backend或诊断工具。

`app/`内13个旧模块是共享模块对象的兼容入口；旧函数名及测试替换继续有效。旧F8-C、F6/F7和FastAPI仍保留原位置。

默认R3读取`configs/render/room_fire_round3.json`，不依赖当前工作目录。旧app下JSON保留兼容副本，打包时要求字节一致。第6批增加共享分析Core后，`paths.CODE_FILES`覆盖21份引擎Python、13份兼容模块、6份预设/兼容副本，共40份；静帧和动画均登记。纯分析迁移不改火烟或传播，但源码版本已变，不能重签旧任务续跑。

必须安装完整目录，不能再把单个app兼容脚本复制到容器/tmp执行。操作边界见[迁移说明](../docs/room_engine_migration.md)。迁移仅完成本地离线验证，实际Blender/GPU尚未重新运行；复现V1使用其归档代码。
