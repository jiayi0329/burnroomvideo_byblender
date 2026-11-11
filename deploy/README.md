# 发布实现与执行边界

只使用deploy/scripts和本目录生产/GPU模板；release源码及兼容副本已移除。根Dockerfile/开发Compose仍有效，服务、端口、GPU风格和数据盘不因文档整理改变。逐文件用途见[根清单](../README.md#完整文件清单)。

| 位置 | 操作 |
| --- | --- |
| 本地PowerShell项目根 | python -B -m tests.run_regression；.\deploy\scripts\build.ps1打包到release/out |
| 本地PowerShell，另行安排 | .\deploy\scripts\deploy.ps1通过SSH/SCP上传、备份/检查、解压；不是启动服务或自动获准部署 |
| WinSCP | 传唯一版本包和核验输入、下载产物，不远端改源码/覆盖数据 |
| 远程SSH | 进入既有Compose目录，安排完整包验收或明确的镜像/服务升级；独立包步骤见[动画指南](../docs/rendering/animation.md#完整代码包与执行位置) |

打包只复制明确Backend/引擎/诊断源码、三份预设、SQL和测试源码；固定SHA保护批准SQL/预设，排除env/密钥/私有产物。PowerShell保留BOM，Shell为LF，外部命令失败停止；旧release/out备份不删除、不移动。

prepare_deploy在备份前只读检查Legacy running及房间created/preparing/rendering/encoding；损坏JSON也停止。过期状态人工核对，不自动删除。检查与部署之间仍有竞争窗口，维护期须冻结新任务，不能宣称有全局原子调度。

现有保护会保存部署代码/配置、旧镜像标签、根视频及相应数据库备份条件；它不等于对所有新版Room8资产/帧做完整异地备份。V1私有归档范围见[发布记录](../docs/RELEASES.md)，数据库备份/恢复另验收。回退代码不清空数据库或数据盘。

本轮没有构建/启动Docker、SSH、数据库或Blender。Linux原环境/GPU验收须后续安排；生产包不是完整开发仓库，Windows发布回归在完整源码检出执行。
