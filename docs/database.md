# PostgreSQL目录与真实数据导入

更新：2026-11-11。服务/八表/CLI实现已有，真实场景导入尚未完成。本页为下一阶段计划和当前正确入口，本轮不执行任何命令。原部署和导入过程见[数据库历史](archive/20261111_process/database_history.md)。

## 当前文件与存储

| 内容 | 位置/含义 |
| --- | --- |
| 结构 | backend/database/migrations/001_rooms.sql，唯一且不可改写的初始迁移 |
| 连接/迁移执行 | backend/adapters/postgres/database.py；显式运行，不随启动迁移 |
| 关系预览/导入 | backend/cli/import_rooms.py；默认预览，--apply才写库 |
| 权限/目录核验 | backend/cli/check_catalog.py；使用应用账号只读检查 |
| 查询接口 | backend/api/room_api.py，/api/catalog |
| 持久化 | 生产Compose挂载/data/zhaojy/burnroom-data/postgres，不发布数据库5432端口 |
| 环境模板 | deploy/prod.env.example，真实.env/prod.env在服务器，不能覆盖原MinIO密码/DK_APPKEY |

八表为scenes、layout_versions、rooms、points、point_room_memberships、assets、render_jobs、render_job_assets。另有执行器维护的schema_migrations迁移记录。数据库只存关系、位置、指纹与摘要，不存模型/视频二进制或过期签名URL；Blender不连库。

## 导入前门禁

1. 实现公共CLI/API操作日志后安排本步骤；当前没有完整trace时间线，不能宣称已符合老师要求。
2. 确认已部署/独立安装的是新路径代码，先看帮助、核对原Python/依赖；不直接在旧服务里照新命令执行。
3. 请管理员处理需要的目录权限，仅针对实际目标，不对整个数据盘chmod/chown。冻结任务提交，核对Legacy和Room8无活动任务。
4. 核对生产PostgreSQL健康、持久化目录、原迁移记录及应用账号；不删除PG_VERSION、数据卷或重建空库冒充导入。
5. 备份数据库、部署配置及人工review，记录时间、目标、dump文件大小/指纹，并在隔离目标验证可恢复。真实备份与恢复尚需远端执行，现有代码/视频归档不能代替数据库备份。
6. 选择明确的成功probe、alignment_report及绑定review，不用本地旧目录或mtime自动挑最新。保存输入SHA和导入前查询结果。

## 各环境的操作

| 环境 | 操作 |
| --- | --- |
| 本地PowerShell | tests.run_regression；deploy/scripts/build.ps1打完整包；不启动数据库/Docker |
| WinSCP | 上传选定代码包和核验版本，下载备份/回执；不远端编辑源码、不覆盖已有review |
| 远程SSH | 先进入~/burnroom-prod/burnroom-deploy-package；部署/原环境验收另行安排，逐步执行备份、预览、人工核对、显式导入和查询 |

### 先预览，不写库

以下以已验收新代码位于容器/app为前提。若使用独立完整包，以其固定code_root替换路径。probe_dir、alignment_dir先赋为容器内经过核对的实际目录；不要把Windows路径传进去：

```bash
cd ~/burnroom-prod/burnroom-deploy-package
probe_dir='/app/data/KK-EEz16cmU14/diagnostics/floorplan/替换为已核对的成功版本'
alignment_dir='/app/data/KK-EEz16cmU14/diagnostics/alignment/替换为已核对的版本'
docker compose exec -T app-server python3 /app/backend/cli/import_rooms.py --scene KK-EEz16cmU14 --probe-dir "$probe_dir" --alignment-dir "$alignment_dir" --review-file "$alignment_dir/review.json"
```

预期mode=preview、rooms=6、points=22、xy_verified=true，数据库/MinIO不写入。数目正确仍要核对来源指纹、人工结论和资产路径；不是拿6/22当唯一验收标准。

### 显式写入与核验（后续授权步骤）

确认备份可用、预览及人工关联正确后，在同一组参数中显式增加--apply；本次真实导入先不加--upload-assets：

```bash
docker compose exec -T app-server python3 /app/backend/cli/import_rooms.py --scene KK-EEz16cmU14 --probe-dir "$probe_dir" --alignment-dir "$alignment_dir" --review-file "$alignment_dir/review.json" --apply
docker compose exec -T app-server python3 /app/backend/cli/check_catalog.py --scene KK-EEz16cmU14
```

返回layout_version_id需保存，后续查询按这个版本核对，不把其他历史版本总量算进本次结果。相同输入再apply应reused=true，不新增重复版本或覆盖人工结论。事务失败应整体回滚；网络中断后先查询是否已提交，不盲目清空表或重复补写。

迁移已部署则先核验schema_migrations；只有明确需要补迁移/账号授权时才运行`python3 /app/backend/adapters/postgres/database.py`。这会写结构/权限，不是只读检查，不能作为每次服务启动的默认步骤。

## 导入前后对照

| 检查项 | 预期 |
| --- | --- |
| 房间/点位 | 本次layout_version有6条房间记录；该场景22个唯一源点位，不宣称6个均有效 |
| Room11 | 按核验标记无效，不进入正常渲染选择 |
| 22号 | 人工关联客厅Room8内部 |
| 32号 | 人工门口关联Room8，不转成传播内部点 |
| 42号 | 户型外，不误绑定Room8 |
| 人工/算法结果 | 分字段保存；未人工复核的点不能伪造已复核 |
| Room8内部13点 | 是现有房间资产/传播输入的核验事实；需与本版本关系对照，不等于库中13条均已有人工review |
| 重复导入 | 相同指纹复用原版本/点位，不覆盖review/人工名称；改变输入需新版本/显式修订 |
| 资产 | 文件位置/大小/SHA可追溯，未上传对象不能填成MinIO可用；不自动把旧全屋视频归为Room8 |
| 原文件/视频 | OBJ、贴图、review、room.blend、timeline和历史视频SHA不变 |
| API/日志 | catalog以应用账号查询；失败可定位。旧健康/分享不因数据库失败不可用 |

查询用`/api/catalog/scenes/KK-EEz16cmU14/rooms?layout_version_id=实际ID&include_invalid=true`核对无效记录，再用返回的整数room_id查点位/资产；不要把字符串Room8当数据库主键。应用账号权限、跨场景外键、重复导入、错误回滚和备份恢复分别验收，不能用管理员连接成功代替。

## 失败、备份和回退

备份使用服务器pg_dump自定义格式，先写唯一备份目录的临时文件，成功后校验/重命名；用pg_restore列目录并在隔离数据库实测恢复，再保存回执。权限问题由管理员针对该目录处理，凭证不发聊天、不入Git。未做恢复实测的dump不标“恢复通过”。

代码回退与数据库恢复是两件事：先停止写入，确认事务结果/错误阶段；必要时恢复上一代码镜像，不因此删除数据库数据。生产恢复须先选隔离目标核验，再明确切换，不能直接对当前库执行清空/--clean。目录改名本身没有SQL内容变化，也不要求重新建库。

数据库真实导入完成后，新版Room8资产/视频的MinIO上传核对与登记继续单独实施；数据库摘要不是任务状态真相源，登记失败不重新渲染视频。
