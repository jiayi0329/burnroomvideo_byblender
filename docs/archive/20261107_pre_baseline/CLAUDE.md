# Project: Burnroom - Architecture, DevOps & Guidelines

## 1. 核心架构约束 (V1 MVP)
- **环境分离**: 
  - 本地开发: Windows 11, VS Code, PowerShell.
  - 远程生产: Ubuntu, IP `172.25.76.201`, 端口 `7777`, 用户 `zhaojy`.
- **单体胖容器**: FastAPI 后端、OpenCV 和 Blender 4.2 均在同一个 Ubuntu 容器内运行。
- **进程隔离**: 绝对禁止在 FastAPI 或业务逻辑中 `import bpy`。Blender 必须通过 `subprocess.run` 作为完全独立的子进程调用。
- **数据 I/O与持久化**: 
  - 摒弃本地文件系统，输入资产与输出视频全部通过 S3 SDK 与 `minio-oss` 容器交互。
  - 生产环境 MinIO 数据强制挂载至服务器独立数据盘: `/data/zhaojy/burnroom-data/minio`。
- **数据关系（2026-10-30 用户确认变更）**: 允许 PostgreSQL 保存房间/点位/文件关系和任务摘要；Redis/MySQL 不引入。渲染运行状态首期仍以 JSON 为准，数据库摘要不是独立状态机；Blender 只读取文件，不直接连接数据库。数据库仅 Docker 内部访问，数据落独立数据盘。

## 2. CI/CD 自动化部署规范 (Strict Rules)
- **交付流**: Local Pack (`build.ps1`) -> SCP Transfer (`deploy.ps1`) -> Remote SSH Extract -> Docker Compose Up。
- **打包脚本 (`build.ps1`)**: 剥离无用文件，将 `app/` 及生产配置打包为 `burnroom-deploy-package-*.tar.gz`。必须维持 `UTF-8 with BOM` 编码，防止 Windows PowerShell 乱码。
- **部署脚本 (`deploy.ps1`)**: 为避免 Windows `\r\n` 换行符导致 Linux `bash` 报错，远程 SSH 执行的多行命令已被压缩为 `&&` 串联的单行命令，**后续修改绝对禁止恢复多行写法**。
- **密钥管理**: 真实密码文件 `.env` 仅存在于服务器端（由 `prod.env.example` 复制而来），严禁通过脚本打包或推送任何包含明文密码的配置文件。

## 3. Python 编码规范
- 强制标注 Type Hints (`->` 和 `:` 声明)。
- 使用 `pydantic` 进行数据类和 API 输入输出校验。
- 优先使用 `pathlib` 替代 `os.path`，处理跨平台路径问题。
- 保持函数单一职责，拒绝几百行的“面条代码”。

## 4. 业务域认知 (4DKankan)
- **场景数据**: 下载资产包括 `mesh.obj`, `[id].jpg` 高清全景图, 以及 `points.json` (记录各图片位姿与 `visibles` 拓扑可视关系)。
- **第一期极简 Scope**: 仅处理单房间 (room: 0) 且点位 < 5 个的极简场景。

## 5. 当前任务与阻碍 (Current Blocker - For Claude Code)
- **当前状态**: CI/CD 流水线已打通，生产环境代码与配置已成功部署至 `/home/zhaojy/burnroom-prod/burnroom-deploy-package`，MinIO `.env` 已配置。
- **当前阻碍**: 在服务器执行 `docker compose pull` 或 `sudo docker compose up -d` 时，终端抛出 `Error response from daemon: denied`。
- **下一步行动**: 
  1. **解决网络/镜像问题**: 协助用户诊断并修复 Ubuntu 服务器的 Docker 镜像拉取问题（极大概率为国内 GFW 导致 Docker Hub 被墙/代理未覆盖/国内镜像源失效）。请提供修改 `daemon.json` 或设置代理的具体方案，直至容器成功 `Started`。
  2. **编写文档**: 容器启动成功后，编写标准 `README.md`。
  3. **跑通闭环**: 测试整体的“本地改代码 -> 运行脚本打包推送 -> 线上重启生效”工作流。
