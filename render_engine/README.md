# Render Engine

几何、传播、效果、Blender和任务执行按职责分层；完整用途见[根清单](../README.md#完整文件清单)。只验证了Room8，不宣称通用多房间已验收。

- geometry只读来源/坐标/证据、对齐和面级裁切；不依赖诊断CLI/数据库。
- propagation/effects提供内部BFS、展示分量、曲线火舌/烟柱及配置校验；不实现CFD或Hybrid。
- blender下F8-B生成基础资产，D只做检查/样帧，E为动画worker；火烟节点/helper无独立任务入口。
- jobs普通Python启动器负责锁、冲突、子进程、编码、报告和续跑；业务端不导入bpy。
- legacy保留F6/F7/F8-C供旧HTTP使用，不能替代Room8新入口。
- paths登记25份Python与3份公共预设，共28份；缺失/变更拒绝，不能换签名续跑原40文件/V1任务。

默认配置是安装根configs/render/room_fire_round3.json，不依赖工作目录。普通帮助入口为`python -m render_engine.jobs.run_room_animation --help`。必须安装完整包；基础资产、样帧和视频输出都写独立版本，不覆盖数据或历史文件。

当前操作：[房间资产](../docs/rendering/room_assets.md)、[R3风格](../docs/rendering/style.md)、[动画](../docs/rendering/animation.md)。V1已出片，本轮不重渲染；原版本及实测见[RELEASES](../docs/RELEASES.md)。
