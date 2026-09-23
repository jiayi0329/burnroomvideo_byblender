# Project Skills & Guardrails

## 1. 核心架构约束 (V1 MVP)
- **单体胖容器**: FastAPI 后端、OpenCV 和 Blender 4.2 均在同一个 Ubuntu 容器内运行。
- **进程隔离**: 绝对禁止在 FastAPI 或业务逻辑中 `import bpy`。Blender 必须通过 `subprocess.run` 作为完全独立的子进程调用。
- **数据 I/O**: 摒弃本地文件系统，输入资产与输出视频全部通过 S3 SDK 与 `minio-oss` 容器交互。
- **无状态设计**: 禁止使用 Redis/MySQL，任务流转状态通过 MinIO 或本地简单 JSON 文件维系。

## 2. Python 编码规范
- 强制标注 Type Hints (`->` 和 `:` 声明)。
- 使用 `pydantic` 进行数据类和 API 输入输出校验。
- 优先使用 `pathlib`，摒弃 `os.path`。
- 保持函数单一职责，拒绝动辄几百行的“面条代码”。

## 3. 业务域认知
- **场景数据**: 4DKankan 下载的资产包括 `mesh.obj`, `[id].jpg` 高清全景图, 以及 `points.json` (记录各图片位姿与 `visibles` 拓扑可视关系)。
- **第一期极简 Scope**: 仅处理单房间 (room: 0) 且点位 < 5 个的极简场景。