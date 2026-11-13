# 操作日志与执行追踪

更新：2026-11-12。公共组件、API中间件、主要CLI及Room8任务接入已实现并离线验证；3be7124完成远端HTTP与Room8单帧GPU关联日志的最小验收，证据见[发布记录](RELEASES.md)。前端尚未存在，不能宣称已实现真实按钮上报或监控网页。

## 已实现的范围

| 入口 | 记录与关联 | 仍有边界 |
| --- | --- | --- |
| backend.api.main全部HTTP请求 | 请求开始、响应完成、状态码、路由模板、UTC时间与单调耗时；覆盖404/422/503/500与取消 | 不记录请求体、查询字符串、Authorization或响应内容；不新增业务API |
| 主要后台阶段 | catalog读取/分享，Legacy下载、时序、启动、后台守护及发布 | 旧文本/Blender第三方日志不是本组件输出；没有改写历史记录 |
| catalog CLI | import_rooms的输入核验/显式apply、check_catalog、database显式迁移；包含参数拒绝、返回非零和异常 | 不自动执行导入/迁移；--help不写日志；诊断tools未全部接入 |
| Room8产物登记CLI | register_room_assets的本地清单、数据库绑定、私有桶、上传回读、事务阶段与失败/耗时，关联原job_id；功能已远端验收 | 本次未单独提取完整trace或远端失败注入；登记回执不替代渲染状态 |
| 新版任务API | HTTP→预留任务→独立CLI→原attempt/worker的trace/request/job关联，状态/视频查询及摘要失败日志 | 本地实现并离线测试，尚未远端验收；前端尚未实现 |
| Room8启动器 | CLI、预检、冲突检查、job/attempt、Blender启动、编码、ffprobe、完整解码及失败 | 复用原状态、逐帧manifest、timing/GPU文件，不另建状态机 |
| Blender动画worker | 继承关联上下文、准备阶段、worker总耗时、每24个输出的轻量进度事件 | 不复制完整逐帧记录；真实GPU单帧及准备/worker/attempt关联已验收；静帧/裁切入口未统一接入 |
| 时间线CLI | 从JSONL生成单trace/job的JSON摘要及可选Markdown文档 | 本地/维护工具，不是公开日志API；无前端、鉴权、告警或集中监控集群 |

业务Python不import bpy；公共标准库组件位于render_engine/jobs/operation_logging.py，Backend依赖它，不让Engine反向依赖Backend。导入模块不创建日志目录或连接服务。

## 文件与写入策略

| 日志类型 | 默认位置 |
| --- | --- |
| API、CLI、创建任务之前的事件 | `<project_root>/data/logs/operations/`，生产安装通常为`/app/data/logs/operations/` |
| 自定义服务日志目录 | 可选环境变量`OPERATION_LOG_ROOT`；不需要修改现有env才能使用默认值 |
| 新版Room8任务事件 | `render_jobs/<run_id>/attempts/<attempt_id>/operations/` |
| 逐帧/GPU/视频技术证据 | 继续使用已有manifest、gpu_metrics、timing_report、video_receipt，不复制进请求日志 |

分片命名为`YYYY-MM-DD-<pid>-<process_token>-<part>.jsonl`。按UTC日期及单文件50MiB轮转；每个进程写独立文件，线程通过进程内锁追加单行，避免多个worker共写一个文件。文件创建权限在Linux请求0600，Windows遵从目录ACL；不是分布式锁或防篡改审计库。

默认不自动删除任何历史日志。建议先保留14天服务日志、将交付任务日志随任务归档，具体容量/保留期由维护者安排；自动清理尚未实现。完整安装目录及数据盘挂载保持原状，`data/`不入Git。日志普通写入失败时保留业务结果与原异常，标准logging向stderr输出不含路径/异常正文的告警，同一进程最多每60秒一次；日志缺失不能解释成执行成功。

## 字段与关联

| 字段 | 实际含义 |
| --- | --- |
| schema_version / event_id / pid / ts | 模式1、事件唯一ID、当前进程、UTC ISO时间 |
| trace_id | 一次操作的关联ID；HTTP接受格式合规的X-Trace-ID，否则生成；CLI生成新ID或复用已有受控上下文 |
| request_id | 每次HTTP请求新生成，轮询不复用请求ID；响应返回X-Request-ID和X-Trace-ID |
| span_id / parent_span_id | 请求、CLI及阶段的父子关系；后台线程与子进程显式传递 |
| operation / stage / event | 动作、阶段和start/success/failure/cancel/accepted/progress；accepted不等于任务成功 |
| method / route / status_code | HTTP方法、路由模板、HTTP结果；未命中路径写unmatched，不记录原始路径 |
| scene_code / room_id / asset_version / job_id / attempt_id | 可用且格式校验后的业务上下文；未知字段缺省，不伪造数据库身份 |
| duration_ms | 本进程perf_counter得到的阶段耗时；开始或进度事件可无此字段 |
| error_code / error_type / exit_code | 有限错误分类、异常类型或退出码；不记录异常正文/任意参数 |
| completed_outputs | 轻量进度计数；完整逐帧依据仍是render_manifest |

外来ID限制为1–96个ASCII字母数字及`_.:-`，拒绝空白/控制字符/URL。其余字段采用允许列表、类型和长度限制；没有认证就不记录虚构actor。API响应成功仅表示HTTP结果，业务返回failed的阶段单独记录失败；awaiting_visual_review不等于人工通过。

响应耗时截至最后一段响应body发送完成，不包含之后的Starlette后台任务；后台阶段单独计时。若响应后任务出错，记录http.background失败，保留原HTTP响应结果。请求取消、流式响应失败与未完成响应分别记录；不跨机器相减时间，不将嵌套span耗时相加当作任务总耗时。

Legacy后台守护使用copy_context传递上下文。Room8通过BURNROOM_OPERATION_CONTEXT向子进程传递允许字段；worker在自己的进程分片写入同一attempt目录。重试保留同一job但创建新的attempt与CLI trace，不改写先前事件。新的日志模块纳入29份引擎源码/预设保护；旧28/40文件及V1任务只能用原版本续跑，不能修改旧快照或改签。

## 如何查看（本轮不需启动渲染）

在已有依赖的本地PowerShell中，查看命令帮助不会调用服务：

```powershell
python -m backend.cli.log_timeline --help
```

已有服务日志下载到本地后，替换示例TRACE_ID查看一条操作；输出文件必须不存在：

```powershell
python -m backend.cli.log_timeline --logs .\data\logs\operations --trace-id TRACE_ID --output .\release\out\operation-timeline.md
```

远程SSH、现有Compose目录中，已部署新代码可查看已存在的任务（不启动新任务）：

```bash
docker compose exec -T app-server python3 -m backend.cli.log_timeline --logs /app/data/SCENE/rooms/Room8/render_jobs/JOB/attempts/ATTEMPT/operations --job-id JOB
```

SCENE/JOB/ATTEMPT均需替换为实际值；历史任务没有operations文件则无法反推完整追踪。跨服务与任务查询可以用相同trace_id分别读两个目录，不需要合并或移动原始日志。WinSCP只负责下载JSONL/Markdown报告。

时间线只读取命名匹配的操作分片、重新应用字段白名单，忽略损坏/未写完行并报告数量。默认最多展示5000条（上限20000），截断明确标记；不会改写源日志或覆盖既有Markdown。HTTP摘要只统计所选事件里的已结束请求，给出数量、失败/取消率、平均和P90，缺数据为null，不能把截断子集当全站指标。

## 测试与后续验收

本地离线测试使用临时JSONL、进程/Blender替身和进程内TestClient，不启动服务器或调用真实外部API。新增tests/backend/test_operation_logging.py及tests/engine/test_room_operation_logging.py，覆盖脱敏、ID校验、父子span、线程/进程隔离、轮转、HTTP成功/拒绝/异常/取消/流式响应、响应后任务、CLI退出、日志失败、Room8输出隔离及子进程传递。

前端下一阶段再实现按钮动作的关联ID、请求、后台阶段及结果/播放上报；前端输入视为不可信。远端最小验收已证明HTTP和单帧GPU任务能写入并关联日志；完整动画编码、失败恢复等本次没有重新实测，不能扩大验收范围。真实数据导入及首批产物登记功能已验收，但对应完整trace未单独提取；磁盘保留和真实前端仍待验收。日志不是鉴权、数据库审计或共享服务器全局调度器。

2026-11-13新版任务API已本地接入：request_operation、注册来源核验、任务预留/进程握手、launcher_exit及数据库摘要同步复用公共stage。HTTP trace/request通过BURNROOM_OPERATION_CONTEXT传入独立CLI，再进入原Room8 attempt/worker。轮询和视频查询绑定scene/room/job；同键重试返回submission_trace_id指向原创建操作，当前HTTP仍有独立request_id。api_launcher.log为本任务子进程输出，操作JSONL继续分进程存放；不输出请求正文、幂等键明文、数据库错误正文或签名URL。视频流异常由现有ASGI中间件记录。离线测试覆盖这些关联和失败脱敏；尚未远端提取新API完整trace或验收前端按钮。
