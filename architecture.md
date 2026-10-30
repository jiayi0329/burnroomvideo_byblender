# 系统架构文档：火灾场景时序演变视频生成系统

> 版本：V2.0（现状架构如实化 + 版本路线图映射）
> 依据：[PRD_V1.1.md](PRD_V1.1.md)（V2.0 版本化路线图）
> 状态：已评审

---

## 1. 架构目标与硬约束

| 目标 | 说明 |
|---|---|
| 链接交付 | 输入 sceneCode → 全流程自动完成 → 浏览器打开公开链接看片（V6.0 验收） |
| 远程 GPU 渲染 | 生产环境为远程 Ubuntu 服务器（172.25.76.201，4×NVIDIA L20） |
| 可观测 | 生命周期事件 + GPU 指标全程落盘，为观测网页/大屏提供数据源 |
| 可增量演进 | V6.0-V9.0 逐版本点亮组件，不要求一次性完成 |

**硬约束**：

1. bpy 与后端**不同进程**：禁止在 FastAPI/业务代码中 import bpy，Blender 通过 `subprocess` 独立子进程调用；
2. 2026-10-30 确认调整：PostgreSQL 管理房间/点位/文件关系；运行状态仍以 JSON 为准，数据库任务状态仅查询摘要；不引入 Redis/MySQL；
3. 数据 I/O：输入资产与输出视频走 S3 SDK + MinIO（本地 data/ 为开发通道）；
4. 生产数据强制挂载服务器独立数据盘 `/data/zhaojy/burnroom-data/`。

---

## 2. 现状架构（已实现，V5 里程碑）

```
┌────────────────────────── 远程服务器 (Ubuntu, 4×L20) ──────────────────────────┐
│                                                                                │
│  docker compose (burnroom-deploy-package)                                      │
│   ┌─────────────────────────────┐        ┌──────────────────────┐             │
│   │ app-server (胖单体镜像)      │        │ minio-oss            │             │
│   │  FastAPI (8000)             │  S3    │  (9000 API/9001 控制台)│             │
│   │  OpenCV (F6)                │ ─────> │  burnroom-assets      │             │
│   │  Blender 4.2 (F8 子进程)    │        │  burnroom-outputs     │             │
│   │  GPU 采样/守护线程          │        └──────────┬───────────┘             │
│   └───────────┬─────────────────┘                   │持久化                     │
│               │ /app/data (挂载)                     ▼                           │
│   ┌───────────▼─────────────────────────────┐  /data/zhaojy/burnroom-data/minio │
│   │ /data/zhaojy/burnroom-data/app-data     │   (服务器独立数据盘)               │
│   │  {scene_code}/: 资产+timeline+output.mp4│                                   │
│   │  logs/: render.log, lifecycle.jsonl,    │                                   │
│   │         failure.log                     │                                   │
│   │  metrics/: gpu_metrics.jsonl            │                                   │
│   └─────────────────────────────────────────┘                                   │
└────────────────────────────────────────────────────────────────────────────────┘
        ▲ 本地开发: Windows + Docker Desktop (无 GPU, 软渲染兜底)
        ▲ 部署通道: build.ps1 打包 → deploy.ps1 SCP → 服务器解压 → compose up
```

### 2.1 模块清单

| 模块 | 职责 |
|---|---|
| `app/main.py` | API 层：场景下载 / `POST generate_timeline` / `POST render`（Popen 拉起 Blender + 守护线程收敛状态）/ status 查询 |
| `app/F6_detect.py` | 起火点识别（OpenCV 烧黑像素占比） |
| `app/F7_spread.py` | 蔓延时序（visibles 拓扑 BFS → timeline.json） |
| `app/F8_blender_render.py` | Blender 子进程脚本（单房间过滤/体积火焰/焦黑化/动态运镜/贴图兜底） |
| `app/s3_io.py` | MinIO 数据流转（资产拉取/产物上传/桶管理） |
| `app/observability.py` | 生命周期事件流、GPU 指标采样（nvidia-smi→jsonl）、失败追踪、状态快照 |
| `release/` | 生产 compose、prod.env 模板、build.ps1 / deploy.ps1 |

### 2.2 可观测文件规范（`/app/data/{scene_code}/`）

| 文件 | 内容 | 消费者 |
|---|---|---|
| `render.log` | Blender 原始输出 + 逐帧进度 | 人工/WinSCP |
| `logs/render.log` | 生命周期文本日志 | 人工 |
| `logs/lifecycle.jsonl` | 结构化事件流（prepare/process/verify/upload） | V7.0 观测网页 |
| `logs/failure.log` | 失败摘要 + 日志尾部 | 排障 |
| `metrics/gpu_metrics.jsonl` | GPU 利用率/显存/温度（5 秒采样） | V7.0 观测网页折线图、V6.0 温度告警 |
| `render_status.json` | 任务状态快照（running/done/failed + pid + 产物） | API/守护线程 |

### 2.3 关键机制

- **渲染异步模型**：POST 立即返回 → Popen 子进程 → 守护线程（等待退出→验证产物→上传 MinIO→收敛状态）+ GPU 采样线程；status 接口按 `/proc/{pid}` 存活兜底
- **幂等与覆盖**：运行中重复触发返回当前状态；渲染前强制删除旧 output.mp4，防误判旧片
- **GPU 策略**：compose `gpus: all`（当前暴露全部 4 卡；未来按需收敛到单卡）；容器内 nvidia-utils-535 提供 nvidia-smi；无 GPU 环境自动跳过指标采样
- **镜像构建（服务器侧已知方案）**：Docker Hub 被墙 → 基础镜像经 1panel 代理拉取打本地标签；download.blender.org 403 → 从旧镜像 `docker cp` 提取 Blender 或更换国内源
- **部署流水线**：本地 `build.ps1`（打包代码+compose+模板，剔除敏感文件）→ `deploy.ps1`（SCP 7777 → 解压）→ 服务器 `docker build -t burnroom-app:latest . && docker compose up -d --force-recreate`

---

## 3. 目标架构（PRD V9.0 对齐）

```
用户浏览器 ──> frontend (nginx, 单入口) ──/api──> backend (FastAPI)
                                                    │ 作业文件队列 (jobs/<jobId>/)
                                                    ▼
                                              engine (Blender 子进程渲染)
                                                    │
                                              MinIO (资产/产物/公开链接)
```

| 演进项 | 现状基础 | V9.0 目标 |
|---|---|---|
| 前端 | 无（Swagger + WinSCP） | Vue SPA（F1-F4 全量） |
| 任务体系 | 单场景状态文件 | jobId + 历史 + 排队（V9.0） |
| 作业协议 | 直调 subprocess | 文件队列 jobs/<jobId>/（可重放、可断点） |
| 产物交付 | 数据盘 + MinIO 桶 | **公开只读策略 + 分享链接**（V6.0 先行） |
| 观测 | jsonl 落盘 | 观测网页（V7.0 先行）+ 前端集成（V9.0） |

**演进原则**：渲染运行状态继续文件化，PostgreSQL 接管房间业务关系；Blender 子进程隔离保持不变。数据库不可用不影响旧渲染/分享接口，新房间查询返回可诊断的 503。

### 3.1 PostgreSQL 房间目录（V2.3）

新增内部 postgres 服务及八张核心表，详见 PRD 2.1 与 `docs/database.md`。户型版本绑定源数据指纹；点位归属同时保留算法结果和人工结果。文件实际留在 MinIO/工作目录，库中只记路径与关联；渲染任务通过配置 JSON 向引擎交付。本轮不自动迁移旧任务状态，不更改 F6/F7/F8。

---

## 4. 版本路线图与架构组件映射

| 版本 | 架构动作 | 涉及模块 |
|---|---|---|
| **V6.0** 链接交付 | MinIO 公开策略+分享链接接口；流水线编排接口；下载缓存去重；`--quality` 参数；GPU 温度告警 | main.py / s3_io.py / observability.py / F8 |
| **V7.0** 渲染攻坚+观测 | 观测网页（读 jsonl）；房间级评分分档数据层；F8 物理拟真/材质语义；断点续渲（PNG 序列）；自动验收指标 | 新：静态观测页 + 验收模块；F6/F8 升级 |
| **V8.0** 全屋+运镜+容错 | 门窗通风口检测（网格开口分析）；智能运镜算法；手动起火点接口；公告板降级预案；水印 | F7/F8/main.py |
| **V9.0** 产品化 | 前端 SPA + job 文件队列 + jobId 体系；Epic 1 多室算法 | 新：frontend/ + 队列模块 |

---

## 5. 架构决策记录（ADR 汇总）

| # | 决策 | 理由 |
|---|---|---|
| 1 | **单体胖容器**（FastAPI+OpenCV+Blender 同容器） | MVP 交付最快；服务器单机部署场景下拆容器收益低；V9.0 前端化时再评估 engine 独立 |
| 2 | 任务状态以文件为真相源（JSON/挂载盘） | 无数据库依赖、崩溃可恢复、WinSCP 可直查 |
| 3 | Blender 经 subprocess 子进程调用 | bpy 与后端 Python 强绑定，进程隔离唯一可靠方案 |
| 4 | GPU 直通 + 软渲染兜底 | 服务器 4×L20 用 `gpus: all`；无 GPU 环境自动降级不报错 |
| 5 | 数据盘挂载 + MinIO 双通道 | 本地文件满足渲染 I/O；MinIO 满足交付与无状态约束 |
| 6 | 可观测性三文件规范（lifecycle/gpu/failure） | 为 V7.0 观测网页与未来大屏预留结构化数据源 |
| 7 | 部署流水线 build.ps1/deploy.ps1 | 国内网络环境下手动 SCP 最可控；敏感文件只留服务器 |

---

## 6. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 端口未放行（9000/9001）导致公开链接不可访问 | **高** | V6.0 前置：找管理员放行；兜底走 SSH 隧道 |
| 体积特效渲染性能/超时 | 中 | V8.0 公告板降级预案；`--quality preview` 快速验证 |
| GPU 过热宕机（历史事件） | 中 | V6.0 温度告警守护（metrics 已具备） |
| Docker Hub/Blender 下载被墙 | 中 | 1panel 代理拉取 + 旧镜像提取 Blender（已形成标准方案，见 2.3） |
| 户型数据缺失（无 room 字段） | 中 | V7.0 先验证 getSceneViewUserFile；缺失时评分分档+拓扑聚类自建房间 |
| 渲染中断丢失进度 | 中 | V7.0 断点续渲（PNG 帧序列） |

---

## 7. 演进路径（Backlog 预留）

| 演进项 | 架构预留 |
|---|---|
| FDS MCP 代理（Epic 2） | engine 层新增数据输入通道，timeline.json 可被物理模拟结果替换 |
| 公网 Web（Epic 3） | frontend 独立部署，MinIO 公开链接机制直接复用 |
| 云 GPU 迁移 | engine 子进程协议不变，容器整体可迁 |
| 多任务并发 | 状态机文件化天然支持 N 任务并行（V9.0 队列化后解锁） |
