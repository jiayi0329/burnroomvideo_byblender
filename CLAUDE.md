# 项目开发约束

更新：2026-11-11。当前目录/调用链见README和docs/ARCHITECTURE.md；原始规则快照在docs/archive/20261107_pre_baseline/CLAUDE.md。过期的镜像拉取阻碍、app路径和最初单房间范围不再作为任务指令。

- 本地Windows编辑、离线测试和打包；远端Ubuntu运行Blender4.2。未经当前任务授权，不启动本地Docker/服务器，不执行远端部署、数据库导入或渲染。
- FastAPI/普通业务代码不得import bpy。Blender专用脚本通过独立子进程执行；Room8使用安全启动器，不绕过任务锁直接调用worker。
- 当前FastAPI/OpenCV/Blender/FFmpeg同容器，PostgreSQL、MinIO独立服务；目录分类不等于拆服务。保持NVIDIA图形库与实际渲染器校验，不把nvidia-smi可见当作GPU执行证明。
- 文件是Blender输入输出及运行状态依据；PostgreSQL保存关系/查询摘要，MinIO保存已上传对象。新版真实导入/完整对象登记尚未完成。Blender不直接连库，不引入Redis/MySQL。
- 原模型、人工review、基础房间、历史视频和任务不覆盖。展示/火灾输出写独立版本；源码改变用新任务，不能改旧快照、签名或帧记录续跑。
- 数据与凭证不进Git。真实env留服务器；示例只含占位值，不打包密码、appkey或私有模型/报告。保持数据盘挂载，不因代码整理移动数据。
- backend/database/migrations的已应用SQL保持文件名与内容不变，用原迁移记录/指纹保护；新结构用后续迁移，不更新旧校验强行通过。
- 发布入口为deploy/scripts/build.ps1和deploy.ps1；PowerShell保留UTF-8 BOM，远端Shell为LF。SSH命令保持单行连接，不恢复多行字符串；外部命令失败即停止。
- 优先pathlib、类型注解、单一职责；所有print保留flush=True。新增功能/缺陷修复增加对应tests用例，区分离线替身与真实远端验收。
- 新API/前端/CLI/后台操作的日志与测试要求见AGENTS.md和docs/OBSERVABILITY.md；现有渲染日志不等于全链路监控完成。
- Git只提交源码、测试、公共配置和脱敏文档。按职责拆分提交，由用户指令决定是否执行；不擅自commit/push/merge/tag或破坏性清理。
