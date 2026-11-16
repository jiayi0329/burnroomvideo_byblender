# 基于三维场景的火灾可视化与视频生成平台：前端第一阶段

本项目当前为实验室科研原型，Room8 是已验证的演示样例，其余功能按实际接入状态显示。中文 React / TypeScript / Vite 工作平台，Tailwind CSS 与 shadcn/ui Button（Radix Slot/CVA 组合）。四页覆盖场景资源、房间处理、火灾模拟、任务成果。第一阶段没有真实业务API请求、模型、视频、任务或持久化日志。

## 本地运行

在项目根目录的 PowerShell 执行：

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

访问 http://127.0.0.1:5173 。仅绑定本机；端口被占用时直接报错，不悄悄换端口。Ctrl+C 停止。Node 26.13.1 / npm 11.20.0 已用于本次验证。

## 检查

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run test
npm.cmd run build
npm.cmd run test:e2e
npm.cmd run preview -- --host 127.0.0.1 --port 4173 --strictPort
```

单元/组件测试使用 jsdom 与服务替身。浏览器测试默认使用本机 Microsoft Edge 无头模式，自动复用或启动4173端口的生产构建预览（先运行build），避免开发热更新干扰导航；检查四页在1440/390像素宽度下的布局及交互、无运行时异常和无业务API请求。截图在忽略目录 `test-results/`。其他操作系统需调整 `playwright.config.ts` 的浏览器 channel 并准备相应浏览器。

首次初始化之后使用锁文件安装；无需安装 Python、Blender 或启动 Docker。`dist/`、`node_modules/` 和测试报告不提交。格式整理使用 `npm.cmd exec prettier -- --write .`。

## 当前可操作与待接入项

- 可操作：四页导航、模型/检查图/视频占位切换、五个演示滑块与数值框、质量/相机契约选项预览、草稿差异及重置、中文输入错误。
- 滑块0–100是无物理单位演示刻度，初值50不是R3默认值。实际物理单位、范围与默认值待后端能力确认。正式档预览只允许overview；重置只影响本地草稿。
- 待接入且禁用：下载/导入、房间裁切、起火点选择、保存预设、提交、媒体播放/下载和授权日志查询。
- 服务始终显示“未连接”，不轮询或探测远端。统一组件支持未连接、加载、空数据、错误、成功；当前页面不冒充任何成功结果或进度。
- `lib/api` 为只读适配边界，默认关闭，拒绝旧渲染入口；启用后仍无POST及自动重试。类型基于现有Room8来源上下文、创建请求和catalog资产字段，不将业务房间号与数据库主键混用。真实响应需第二阶段补充运行时校验。
- `lib/telemetry` 只定义白名单事件/关联与可注入传输接口，不创建另一套后端日志系统。默认没有接收、持久化或查询，不能据此宣称全链路日志完成。错误正文、凭证、签名URL不进入事件。

## 下一阶段

先经受控隧道和开发代理只读连接服务器：来源与catalog确定实际房间、资产版本及GLB/检查图，安装R3F/Drei并实现RoomPreview接口；GLB不重复转换坐标，核验MinIO可达性与CORS。使用现有room-jobs视频接口连接原V1，验证播放、Range拖动与下载。

随后单独接入受控提交、幂等键、服务端参数验证和已有状态；前端事件经可信接收入口复用现有operation_logging，完成脱敏及关联回归后再验收真实按钮日志。不改R3基线，不通过旧API替代，不自动渲染。
