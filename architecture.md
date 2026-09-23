# 系统架构文档：火灾场景时序演变视频生成系统（V1.1）

> 版本：V1.1
> 依据：[PRD_V1.1.md](PRD_V1.1.md)
> 状态：待评审

---

## 1. 架构目标与约束

| 目标 | 说明 |
|---|---|
| **Docker 一键启动** | 单条命令完成构建与启动，打开浏览器即可使用 |
| 单机运行 | 所有服务与本机数据不出本机（PRD 7.3 合规承诺） |
| 无人值守出片 | 输入 sceneCode → 全流程自动完成（PRD 第 9 节验收标准） |
| 可增量构建 | 支持 PRD M1~M5 里程碑分阶段落地，不要求一次性完成 |
| 可演进 | V2 迁移云 GPU/任务队列时拓扑平滑扩展 |

**硬约束（来自 PRD）**：

1. bpy 与后端**不同进程**（Blender 4.2 LTS 自带 Python 3.11，bpy 不可跨进程导入）；
2. 单任务串行（V1 不引入 Celery/Redis）；
3. 程序化蔓延路线（无需流体模拟，无需水密网格）；
4. 渲染引擎 Eevee + 公告板火焰，输出 1080P 母版 + FFmpeg 转码 720P；
5. 4DKankan 下载链接为临时 URL，必须即时转存。

---

## 2. 系统上下文

```
                        ┌─────────────────────────────────────────────┐
                        │              本机 (Windows 11 + WSL2)        │
                        │                                             │
 用户浏览器 ──HTTP──>    │   Docker 网络 (bridge: burnroom-net)         │
 (localhost:8080)       │   ┌──────────┐   ┌──────────┐   ┌─────────┐  │
                        │   │ frontend │──>│ backend  │   │ engine  │  │
                        │   │ nginx    │   │ FastAPI  │──>│ Blender │  │
                        │   └──────────┘   └────┬─────┘   │ +轮询器  │  │
                        │                      │         └────┬────┘  │
                        │                      │              │       │
                        │                      └── 共享卷 scene-data ──┘
                        │                     (jobs/ progress/ data/)  │
                        └──────────────────┬──────────────────────────┘
                                           │ 出站 HTTPS（仅此一项外联）
                                           ▼
                              4DKankan 开放接口 (getSceneObj 等 9 个接口)
```

**外联边界**：系统唯一的外部通信是 backend → 4DKankan 开放接口。除此之外，任何容器不访问外网、不推送数据（PRD 7.3）。

---

## 3. 容器拓扑（三容器 + 共享卷）

| 容器 | 镜像基础 | 职责 | PRD 对应 |
|---|---|---|---|
| **frontend** | 多阶段构建：`node:20` 构建 → `nginx:alpine` 运行 | 静态 SPA + 反向代理 `/api`、`/media` | F1~F4 界面层 |
| **backend** | `python:3.11-slim` + FFmpeg | REST API、任务状态机、4DKankan 数据桥接、烧毁识别、时序计算、作业调度、视频文件服务 | F5/F6/F7/F9 |
| **engine** | `ubuntu` + Blender 4.2 LTS + GL 库 + Python3.11 | 作业轮询器 + Blender 子进程渲染（火焰/烟雾/焦痕/运镜） | F8 |
| **共享卷 scene-data** | 命名卷 | `/data`：jobs（作业投递）、progress（进度上报）、scene（转存的模型数据）、result（成片） | 数据目录规范 |

**端口**：仅 frontend 对外暴露 `127.0.0.1:8080`（**只绑定回环地址**，局域网不可见）。backend(8000)、engine 均在 Docker 内网，不对外暴露。

### 拓扑决策说明（ADR-1：为什么 engine 独立成容器）

- Blender 镜像重（≈3~4GB）且与后端生命周期、GPU 需求不同——拆开后可独立重建、独立挂 GPU；
- V2 迁移云端时，engine 容器可直接变为远程 GPU 渲染节点，backend 无需改动；
- 备选方案（backend 内嵌 Blender 的单容器胖镜像）更简单但每次改后端代码都要重建 4GB 镜像，且 GPU 直通粒度差，**不采用**。

---

## 4. 后端 ↔ 引擎通信协议（ADR-2：共享卷文件队列）

V1 **不引入** Redis/Celery（Windows 兼容性差、增加基础设施）。backend 与 engine 通过共享卷 `scene-data` 上的**作业目录协议**协作，完全解耦、可重启恢复、天然支持断点续渲：

```
/data/jobs/<jobId>/
├── input.json       # backend 写入（作业参数，见下）
├── claimed          # engine 轮询器领取作业时创建（空文件，含时间戳）
├── progress.json    # engine 每渲染 1 帧更新（进度上报）
├── log.txt          # engine 的 Blender 运行日志（失败排查）
├── done             # 成功后写入（内容为 result 摘要）
└── failed           # 失败时写入（内容为错误摘要）
```

**作业协议示例**：

```jsonc
// input.json（backend → engine）
{
  "jobId": "8f3a...",
  "sceneCode": "xxxx",
  "sceneDir": "/data/scene/xxxx/",     // 已转存好的模型数据
  "originRoom": 2,                      // 起火房间（自动识别结果或用户修正）
  "timeline": "/data/scene/xxxx/timeline.json",  // F7 蔓延时序输出
  "duration": 60, "fps": 24, "resolution": "1080p",
  "burnIn": {"timecode": true, "roomLabel": true},
  "cameraMode": "pointinfo"             // 采集点位运镜 | orbit 兜底
}
```

```jsonc
// progress.json（engine 周期性写入，backend 轮询读取推给前端）
{ "stage": "render", "frame": 720, "totalFrames": 1440, "percent": 50,
  "message": "渲染中 720/1440", "elapsed": 1820 }
```

- **领取**：engine 轮询器扫描 `jobs/`，对存在 `input.json` 且无 `claimed` 的作业做原子领取（创建 `claimed` 文件）；
- **串行**：engine 同时只运行 1 个作业（PRD 单任务串行），其余排队；
- **续渲**：engine 崩溃重启后，检查已渲染帧目录，从断点续渲（PRD 7.2）；
- **清理**：backend 定期删除过期作业目录（默认 30 天，可配置）。

---

## 5. 运行时数据流

```
用户: 输入 sceneCode + 参数
  │
  ▼
backend: /api/scenes/{code}          → F5 桥接层校验场景（getSceneList）
  │
  ▼
backend: 创建 job（状态: downloading）→ F5 调 getSceneObj/getScenePanorama/
         getScenePointInfo，下载即时转存 /data/scene/<code>/
  │
  ▼
backend: F6 烧毁识别（全景图分析）→ 房间评分 → 起火房间（置信度低则等用户修正）
  │
  ▼
backend: F7 房间图 + 蔓延计算 → timeline.json
  │
  ▼
backend: 写 jobs/<jobId>/input.json（状态: queued）
  │
  ▼
engine : 领取 → blender -b -P render_pipeline.py -- input.json
         → 火焰/烟雾/焦痕/火光动画 + 点位运镜
         → 逐帧输出 PNG → FFmpeg 合成 1080P → 转码 720P
         → progress.json 持续更新
  │
  ▼
backend: 轮询 progress.json → 前端进度条（帧进度）
         engine 写 done 后 → 状态 completed
  │
  ▼
frontend: <video> 播放 /media/result/<jobId>/xxx_1080p.mp4，提供下载
```

**前端进度轮询**：每 2 秒 GET `/api/jobs/{jobId}`，backend 直接读 progress.json 文件返回（无中间态存储，状态机以文件为真相源，重启不丢）。

---

## 6. 目录结构（仓库与容器内映射）

```
burnroomvideo_byblender/
├── architecture.md / PRD_V1.1.md
├── docker-compose.yml            # 一键启动编排（含 gpu profile）
├── .env.example → .env           # 凭据与配置（appkey、清理天数等）
├── frontend/                     # Vue 3 SPA（构建产物由 nginx 托管）
├── backend/
│   ├── Dockerfile                # python:3.11-slim + ffmpeg
│   └── app/                      # FastAPI：api/ bridge/ detect/ spread/
├── engine/
│   ├── Dockerfile                # Blender 4.2 LTS + 轮询器
│   ├── poller.py                 # 作业轮询器（stdlib，无三方依赖）
│   └── blender_scripts/          # render_pipeline.py 等 bpy 脚本
└── data/（开发期可选 bind mount，生产用命名卷）
```

| 容器内路径 | 来源 | 用途 |
|---|---|---|
| `/data` | 命名卷 `scene-data`（backend/engine 共享） | jobs、scene、result |
| `/app`（backend） | 镜像内 | 后端代码 |
| `/scripts`（engine） | 镜像内 | bpy 脚本与轮询器 |
| `/usr/share/nginx/html`（frontend） | 构建产物 | SPA 静态文件 |

---

## 7. 镜像构建策略

| 镜像 | 基础 | 关键构建步骤 | 预估体积 |
|---|---|---|---|
| frontend | node:20 → nginx:alpine | `npm run build` 产物拷贝；nginx.conf 写入 `/api`、`/media` 反代规则 | ~60MB |
| backend | python:3.11-slim | apt 装 ffmpeg；pip 装 fastapi/uvicorn/opencv/numpy 等 | ~800MB |
| engine | ubuntu:22.04 | 下载官方 Blender 4.2 LTS tarball 解压；apt 装 `libgl1 libglx-mesa0 libx11-6 libxi6 libxkbcommon0` 等 GL 运行库 + Python3.11 + FFmpeg | ~3.5GB |

**镜像固定**：engine 镜像构建时锁定 Blender 小版本号（如 4.2.x 具体版本），避免上游更新破坏脚本兼容性。

---

## 8. GPU 策略（ADR-3）

- **默认 CPU 模式**：Eevee 经 Mesa 软件光栅化（llvmpipe）可离线渲染，满足 PRD"无独显 ≤ 4 小时"预算，零额外配置，**保证一键启动永远可用**；
- **可选 GPU 加速**：`docker compose --profile gpu up -d --build`，engine 容器通过 NVIDIA Container Toolkit（WSL2 + Docker Desktop ≥ 3.2 + NVIDIA 驱动 ≥ 5xx）直通显卡，达成 PRD"有独显 ≤ 1.5 小时"目标；
- engine 启动时探测 GPU 可用性并写入日志；不可用时自动降级 CPU，不报错。

---

## 9. 配置管理

`.env`（不入库，提供 `.env.example`）：

```ini
DK_APPKEY=                 # 4DKankan 接入 appkey（必填）
DK_USERNAME= / DK_PASSWORD=  # 可选：/user/v1/login 方式鉴权
DATA_RETENTION_DAYS=30     # 任务数据自动清理周期
RENDER_BURNIN_WATERMARK=on # 演示水印开关
WEB_PORT=8080              # 本机访问端口
```

凭据经 docker-compose 注入 backend 容器环境变量；日志脱敏（不打印 token/密码，PRD 7.3）。

---

## 10. 一键启动体验（目标 UX）

```powershell
# 前置：安装 Docker Desktop（WSL2 后端）+ 可选 NVIDIA 驱动
Copy-Item .env.example .env   # 填入 appkey
docker compose up -d --build  # 一键构建+启动（CPU 模式）
# 打开 http://localhost:8080

# 有 NVIDIA 独显时：
docker compose --profile gpu up -d --build
```

- 首次构建约 15~30 分钟（engine 镜像下载 Blender），此后启动 < 30 秒；
- 容器重启策略 `unless-stopped`，宿主机重启后自动拉起，任务从文件状态机恢复。

---

## 11. 安全与合规设计

| 项 | 措施 |
|---|---|
| 暴露面 | 仅 127.0.0.1:8080；backend/engine 不映射宿主机端口 |
| 凭据 | .env 注入容器环境变量；日志脱敏；不入镜像、不入 git |
| 数据 | 全部落本机命名卷；无外传通道；按 DATA_RETENTION_DAYS 自动清理 |
| 供应链 | 镜像基础层锁定版本；Blender 官方 tarball 校验 |
| 内网隔离 | 三个容器在专用 bridge 网络，仅 backend 有出站外联需求（4DKankan） |

V1 明确**非目标**：Web 用户登录、多用户隔离、外网访问、HTTPS（本机回环访问无需）。

---

## 12. 架构决策记录（ADR 汇总）

| # | 决策 | 理由 | 被否方案 |
|---|---|---|---|
| 1 | 三容器拓扑，engine 独立 | Blender 镜像重、生命周期/GPU 需求不同、V2 可远程化 | 单容器胖镜像（重建慢、GPU 粒度差） |
| 2 | 共享卷文件队列 | 无新增基础设施、重启可恢复、天然断点续渲、Windows 无 Celery 负担 | Celery+Redis（Windows 兼容差）、HTTP/gRPC 引擎服务（多一次网络失败面） |
| 3 | GPU 走 compose profile，默认 CPU | 硬件未知时保证一键启动可用；有卡时一条命令加速 | 强制 GPU（无卡用户无法启动） |
| 4 | Blender 以子进程运行于 engine | bpy 与 Python 版本强绑定，进程隔离最简单可靠 | bpy 作为 Python 模块安装（与 FastAPI 依赖冲突风险高） |
| 5 | 数据用命名卷 | 避免 Windows bind mount 到 Linux 容器的权限/性能问题 | bind mount（开发期可用，生产不稳） |
| 6 | nginx 统一入口反代 | 免 CORS、单一端口、静态资源高效 | 双端口直连（CORS + 部署复杂） |
| 7 | 状态机以文件为真相源 | 无数据库依赖、崩溃可恢复、符合单机定位 | SQLite/Redis（V2 多任务化时再评估） |

---

## 13. 性能预算映射（对应 PRD 第 4 节 F8）

| 阶段 | 预算 | 容器 |
|---|---|---|
| 数据下载（约 1~2GB 场景） | 视网速，≤ 20 分钟 | backend |
| 烧毁识别 + 时序计算 | ≤ 5 分钟（CPU） | backend |
| 渲染 1440 帧（60s@24fps，1080P Eevee） | GPU：≤ 1.5h / CPU：≤ 4h | engine |
| FFmpeg 合成+转码 | ≤ 10 分钟 | engine（backend 亦可） |

WSL2 内存建议 ≥ 16GB（.wslconfig 配置），否则大场景 OBJ 导入可能 OOM——写入 README 前置检查。

---

## 14. 开发模式（可选）

`docker compose --profile dev up`：frontend 换成 Vite dev server（热更新，5173 端口）、backend 挂载代码目录 + uvicorn --reload、engine 挂载 blender_scripts 目录。生产一键启动与开发热更新互不干扰。

---

## 15. 演进路径（V2+）

| 演进项 | 架构预留 |
|---|---|
| 云端部署 | engine 变远程 GPU 渲染节点，文件队列升级为对象存储 + 消息队列（ADR-2 协议不变） |
| 多任务并发 | backend 状态机支持 N 个并行 job，engine 横向扩展多副本（compose `scale`） |
| Cycles 质量模式 | engine 镜像不变，仅切换渲染脚本与 GPU profile |
| 多用户/鉴权 | 在 frontend 入口前加网关层，backend 增加用户维度 |
| 起火点标注回写 | 直接复用 F5 桥接层已封装的 `sceneMarkShape/saveOrEdit` |

---

## 16. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| Windows Docker Desktop 的 GPU 直通失败 | 中 | 默认 CPU 模式兜底；前置检查文档给出 NVIDIA 驱动/WSL2 配置清单 |
| Blender 容器无显示环境渲染异常 | 中 | 镜像预装 Mesa GL 库，llvmpipe 软件渲染；engine 启动自检脚本 |
| 大场景导入内存溢出 | 中 | WSL2 内存 ≥ 16GB 前置要求；OBJ 分房间按需导入 |
| 首次构建时间长（3.5GB 镜像） | 低 | 构建产物可 `docker save` 归档复用；文档给出镜像离线导入方法 |
| 4DKankan 接口真实行为与文档偏差 | 中 | M1 里程碑首验（appkey 权限、临时 URL 时效、坐标系一致性），验证通过后再推进后续构建 |

---

## 17. 与里程碑的对应关系（可增量构建）

| PRD 里程碑 | 需要就位的架构组件 |
|---|---|
| M1 数据桥接 | backend 容器 + 共享卷（可先以 CLI 形态验证，不依赖 engine） |
| M2 Blender 管线 | engine 容器 + poller + 静态渲染脚本 |
| M3 识别+时序 | backend 新增 detect/spread 模块（纯 CPU，无新组件） |
| M4 火焰整合 | engine 渲染脚本升级，作业协议字段冻结 |
| M5 Web 应用 | frontend 容器 + nginx 反代 + 进度轮询 |

架构支持"M1 先行验证、组件逐个点亮"的开发顺序，与 PRD 里程碑一一对应。
