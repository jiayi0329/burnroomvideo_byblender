# Burnroom — 火灾蔓延视频生成系统

基于 4DKankan 室内全景资产（`mesh.obj` / 全景 jpg / `points.json`），自动识别起火点、
推导火势蔓延时序，并用 Blender 渲染火灾蔓延动画的 MVP 系统。

## 架构速览

单机单体胖容器方案：**FastAPI + OpenCV + Blender 4.2 同在一个 Ubuntu 容器**内运行，
对象存储与任务状态通过 **MinIO** 维系（无 Redis/MySQL，无状态设计）。

| 容器 | 端口 | 说明 |
|---|---|---|
| `app-server` | 8000 | FastAPI 后端 + OpenCV + Blender 4.2（Ubuntu 22.04 / Python 3.11 / FFmpeg） |
| `minio-oss` | 9000 / 9001 | MinIO 对象存储（9000 = S3 API，9001 = Web 控制台） |

### 核心模块（app/）

| 模块 | 职责 |
|---|---|
| `main.py` | API 层：场景下载、`POST /api/generate_timeline/{scene_code}` 串联 F6→F7 并落盘 `timeline.json` |
| `F6_detect.py` | 起火点识别：OpenCV 统计全景图"碳化黑/深褐"像素占比，取最高者为起火点 |
| `F7_spread.py` | 蔓延时序：解析 `points.json` 的 `visibles` 拓扑，从起火点做 1-2 层 BFS，输出时间轴 |
| `F8_blender_render.py` | 渲染占位：Blender 子进程脚本，读 `timeline.json` 在对应 3D 坐标生成红色发光球并输出 MP4 |

### 测试（test/，unittest）

```bash
docker exec burnroomvideo_byblender-app-server-1 python3 -m unittest test.test_f6 test.test_f7 test.test_api -v
```

## 本地开发

```bash
docker compose up -d --build   # 热更新开启，改 app/*.py 免重启
```

- Swagger 文档：http://localhost:8000/docs
- MinIO 控制台：http://localhost:9001
- 测试数据位于 `data/{scene_code}/`（含 `points.json`、全景 jpg、`mesh.obj`、`timeline.json`）

## DevOps 自动化流转

```
本地修改代码 → 打包 (build.ps1) → SCP 上传 (deploy.ps1) → 服务器解压 → docker compose up -d
```

### 打包脚本 `release/scripts/build.ps1`

- 剥离缓存与敏感文件，将 `app/`、`Dockerfile`、`requirements.txt`、生产 compose 与配置模板
  打包为 `release/out/burnroom-deploy-package-<版本>-<日期>.tar.gz`
- 注意：**只打包 `prod.env.example` 模板，绝不打包真实密码文件**

### 部署脚本 `release/scripts/deploy.ps1`

- 服务器：`172.25.76.201`，SSH 端口 `7777`，用户 `zhaojy`
- SCP 上传压缩包至 `/home/zhaojy/burnroom-prod`，远程解压替换代码
- ⚠️ 远程 SSH 命令必须保持单行 `&&` 串联写法（Windows `\r\n` 会破坏 bash，禁止恢复多行）

## 服务器目录结构

| 路径 | 内容 |
|---|---|
| `/home/zhaojy/burnroom-prod/burnroom-deploy-package/` | 部署代码、Dockerfile、生产 `docker-compose.yml` |
| `/data/zhaojy/burnroom-data/minio` | **独立数据盘**挂载的 MinIO 持久化目录（生产 compose 绑定） |

服务器侧镜像准备（首次部署一次性操作）：

```bash
docker build -t burnroom-app:latest .          # 后端镜像（本地构建，不推送仓库）
docker pull docker.1panel.live/minio/minio:latest   # MinIO 走国内代理源
```

## 镜像源与网络（国内服务器）

- Docker Hub / quay.io 直连被墙，daocloud 匿名代理限流严重
- 当前可用方案：**`docker.1panel.live`**（Docker Hub 代理，已实测）
- 未来如需拉取裸名镜像（如 `ubuntu:22.04`），可在服务器 `/etc/docker/daemon.json` 配置
  `{"registry-mirrors": ["https://docker.1panel.live"]}`

## .env 脱敏规范（⚠️ 严格遵守）

- 仓库内只有 **`release/prod.env.example` 模板**（占位密码），可安全提交
- 真实密码文件 `prod.env`（容器 env_file）与 `.env`（compose 变量插值）**仅存在于服务器上**，
  由模板复制后手工填写；本地 `release/prod.env` 已被 `.gitignore` 排除
- **严禁**通过 build/deploy 脚本打包、推送任何含明文密码的配置文件
- 两份文件变量需保持一致；需要 4DKankan 能力时再追加 `DK_APPKEY=<key>`

## 核心铁律（继承自 CLAUDE.md）

1. **绝对禁止在 FastAPI 或业务逻辑中 `import bpy`**。
   Blender 必须通过 `subprocess.run` 作为独立子进程调用：
   `blender --background --python app/F8_blender_render.py -- --scene <code>`
2. 数据 I/O 走 S3 SDK 与 MinIO；任务状态用 MinIO 或 JSON 文件维系，禁用 Redis/MySQL
3. Python 规范：完整类型提示、pydantic 数据类、`pathlib` 替代 `os.path`、函数单一职责
