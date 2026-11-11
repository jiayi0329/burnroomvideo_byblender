# 当前目录分类与依赖规则

更新：2026-11-11。只保留新路径，没有app、release源码或test旧包。逐文件用途以[根README](../README.md)为准；七批兼容与去重过程在[历史记录](archive/20261111_process/engineering_history.md)，不再要求保留副本。

## 分类标准

职责分Backend、Engine、Tools、Tests、Deploy、配置、文档；用途分实际实现、Legacy、诊断、测试、公共预设、历史资料和私有产物。不因文件名带diagnose删除，不因可传房间ID宣称多房间已验证。

| 目录 | 当前职责 | 边界 |
| --- | --- | --- |
| backend | API、数据连接、导入、Legacy编排 | 不import bpy，不把旧API当新版房间任务 |
| backend/database/migrations | 唯一SQL位置 | 已应用迁移不可改；目录改名不重建库 |
| render_engine/geometry | 来源/坐标/指纹、对齐、面级裁切 | 不依赖诊断CLI或数据库 |
| render_engine/propagation、effects | BFS、展示分量、火烟曲线/几何 | 不访问HTTP/数据库，不擅自调R3 |
| render_engine/blender | B资产、D静帧、E动画及辅助 | bpy仅在Blender进程执行 |
| render_engine/jobs | 启动、锁、编码、续跑、报告 | 固定输入版本，真实NVIDIA上下文校验 |
| render_engine/legacy | 原F6/F7/F8-C | 保留旧功能，不替代Room8入口 |
| tools | 户型/高度/断面诊断和手工API | 历史依据保留；显式运行才联网/写诊断 |
| tests | 四组回归及隔离集成 | 不默认发现真实数据写入；用例只有一份 |
| deploy | 唯一发布脚本和生产模板 | 根Dockerfile/开发Compose有效，产物release/out忽略 |
| configs/render | R1/R2/R3各一份 | R3默认，R1/R2回归，内容不同 |
| docs | 当前规范/指南与archive | 历史命令不作当前指令 |

frontend尚未建立；未来经API访问Backend，不直接连库或取得MinIO管理凭证，不为目录齐全创建空前端。

## 依赖与版本

Backend可复用引擎纯函数；Engine不得反向依赖Backend/tools。诊断可用只读核心和Backend纯build_plan，不自动连库。包初始化不启动服务、建表或导入bpy。

旧worker为render_engine/legacy/F8_blender_render.py，工作目录显式为安装根。Room8用jobs启动器及独立输出；保留由源点位数据根推导的共享锁位置，不能移动缓存而产生互不排斥的锁根。

render_engine.paths登记26份Python和3份预设，共29份；打包白名单随路径维护。新代码/位置不重签旧任务，原28/40文件任务及V1用归档版本。模型、状态、核验、视频不因代码改名移动。

新增公共函数须核查运行、工具、测试、AST定位、打包和文档引用。按职责拆模块，不重新建立兼容副本，不把不同功能堆成大脚本。提交按职责拆分；部署、导入、渲染、main合并分别授权与验收。
