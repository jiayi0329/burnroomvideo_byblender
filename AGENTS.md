# 后续开发约定

本文件供接续开发工具读取。项目约束见[CLAUDE.md](CLAUDE.md)，当前需求/架构/状态分别见docs/PRD.md、docs/ARCHITECTURE.md、docs/PROJECT_STATUS.md；完整文件职责见根README。历史归档不是当前执行指令，用户当前授权范围优先。

## 新功能必须考虑操作日志

新增或修改API、前端交互、CLI及后台运行功能时，按[OBSERVABILITY](docs/OBSERVABILITY.md)设计可关联的操作/请求/任务日志：记录时间、操作、阶段、结果、耗时和失败，传递trace_id/request_id/job_id等上下文，并增加对应日志回归测试。不要仅靠print或浏览器console宣称实现监控。

公共日志、请求中间件、主要CLI及Room8动画任务追踪已实现；2026-11-12完成HTTP、catalog只读检查及Room8单帧GPU任务的远端最小验收，证据见docs/RELEASES.md。真实前端上报尚未验收；后续优先复用render_engine/jobs/operation_logging.py，不重复创建日志系统。任务依赖未落地能力时明确说明，不假称已有。文档、注释和静态预设调整不需要伪造运行日志。不得为满足这条规则擅自调用真实API、渲染、写数据库或部署。

日志不得包含凭证、Authorization、完整签名URL或原始敏感数据。复用现有任务状态与耗时证据，禁止另造冲突状态机。真实前端尚未存在，按钮链路在前端开发后单独验收。
