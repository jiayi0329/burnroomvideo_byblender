# 诊断与手工集成

逐文件用途见[根清单](../README.md#完整文件清单)，现行资产流程见[房间指南](../docs/rendering/room_assets.md)。app兼容入口和根test_4dkankan已移除，只使用tools正式路径。

diagnostics用于上游户型探测/脱敏、对齐报告、材质/UV/高度、断面/墙面及可选绘图；Blender子目录F8-A只做原模型导入检查，不裁切/渲染。共用分析函数在render_engine/geometry/floorplan_alignment，报告外壳留在tools。Z轴/高度和487点依据继续保留，不重新设为Room8物理确认前置。

integration/probe_scene_api是手工联网检查，不属于自动回归或生产包；默认不请求，须显式--allow-network和注入DK_APPKEY。导入不自动加载.env，输出不包含真实场景、签名URL或凭证。当前可用`python -m tools.integration.probe_scene_api --help`只看帮助。

普通分析应在完整源码/安装包中运行。probe和F8-A实际源脚本可独立使用；不要复制已移除的兼容入口到/tmp。工具只在显式调用时生成独立诊断，不把技术报告等同于人工语义/画面通过。

发布白名单包含10份诊断Python，排除integration及私有返回包、JSON/图片/模型；额外脚本不因在tools目录就自动发布。原流程全文见[主题归档](../docs/archive/20261111_process/README.md)。
