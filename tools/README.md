# 诊断与手工集成工具

2026-11-10第6批迁移。所有历史Z轴、高度采样、墙体/断面依据保留；不重新运行真实诊断，不改变Room8平层近似或渲染参数。

| 实际位置 | 职责与边界 |
| --- | --- |
| diagnostics/probe_floorplan.py | 户型API探测/脱敏与离线包检查；联网仅在显式运行时发生 |
| diagnostics/analyze_floorplan.py | 对齐报告、CSV与overlay、CLI；旧app函数名继续导出 |
| diagnostics/inspect_room_asset.py | 原材质/UV/高度采样诊断，保留历史门槛和证据 |
| diagnostics/blender/F8_inspect_room_import.py | F8-A原模型坐标/UV/材质导入检查；只在Blender执行，不裁切/渲染 |
| diagnostics/diagnose_room_sections.py及room_section_* | 第2批已迁移的断面诊断与绘图，保持原算法 |
| integration/probe_scene_api.py | 原根test_4dkankan.py的手工连接测试；不属于自动测试或生产入口 |

共用18个读取、解析与对齐分析函数位于render_engine/geometry/floorplan_alignment.py，只读输入、不写报告、不依赖tools/Backend/bpy。Backend导入工具直接复用该模块，不再导入诊断CLI。inspect仍复用Backend的纯build_plan，不会因此连库。

4份app兼容模块保留旧CLI/函数入口，并与新工具指向同一模块对象。分析CLI继续导出原几何函数名；其实现与Core共享。新旧CLI的`--help`均不连接服务。例：

```text
python -m app.analyze_floorplan --help
python -m tools.diagnostics.analyze_floorplan --help
python -m app.inspect_room_asset --help
python -m tools.diagnostics.inspect_room_asset --help
python -m tools.diagnostics.probe_floorplan --help
```

普通分析/检查须安装完整代码包，不能把app兼容脚本复制到/tmp或stdin运行。F8-A和probe的实际源脚本仍可独立使用；历史单文件操作须改为复制tools中的真实实现。脚本迁移不授权新诊断、相机API请求或Blender执行。

## 手工API测试的明确变化

根`test_4dkankan.py`继续可作手工入口，默认不发请求；两个模块均标记不参与自动测试。导入时不再自动加载.env，不再要求python-dotenv；凭证来自显式注入的DK_APPKEY。只有操作者明确传入`--allow-network`才会请求场景列表；缺少开关或凭证时停止。请求有超时、禁用重定向，输出仅状态和数量，不打印真实场景、返回URL、凭证或底层异常文本。本轮全部使用假响应测试，没有调用真实API。

## 打包与证据

发布包仅包含明确列出的10份tools诊断Python源码；额外脚本、integration、私有JSON、模型和图片不随它进入生产包。缺少任一必需工具源码会停止打包。共用分析Core另列入引擎清单，完整指纹从39扩为40；不允许重签旧任务续跑。R3、火烟、传播、裁切算法和真实资产不变。

历史487点高度采样、floor_z=-1.35m决策及人工review继续保留在原私有data或历史文档；本轮不回填旧ready_for_cut，也不把精确建筑语义重新设为出片前置。验收口径见[test/README](../test/README.md)，后续第7批再处理测试/部署收尾和主线审阅。
