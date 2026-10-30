# PostgreSQL 房间目录：部署与核验

2026-10-30：用户已确认设计。此文档是待远端验证的操作步骤，不代表部署已完成。

本地验证：69 项检查通过，1 项 PostgreSQL 集成检查跳过；之前建表 SQL 通过语法解析，未实际建库。本地临时 Python 3.13 使用较新 Pydantic 验证接口（原有 2.3.0 缺少该 Python 版本的轮子），生产 requirements 中的原有版本未改，远端原环境仍须执行集成验证。PowerShell 脚本检查语法和 BOM，并在临时合成目录测试真实打包及模拟失败；未对项目执行部署，未启动 Docker 或远端备份/恢复。

## 数据边界

八张业务表见 `app/db/001_rooms.sql`，迁移记录另存 `schema_migrations`。PostgreSQL 16 只在 Compose 内部监听，图片/模型留在 MinIO 或已有工作目录。运行状态仍以 render_status.json 为准，render_jobs/render_job_assets 本轮仅建表预留，不自动同步、不替代现有渲染流程。后续完整任务历史需独立任务目录，旧 output.mp4 不自动归入客厅。

导入的相机坐标若发生变化，当前工具拒绝覆盖，需先设计明确的场景修订；户型/核验内容变化则生成新户型版本。重复导入相同输入与核验时复用版本，保留已有人工结果和房间名称。新增核验文件会创建新版本，不修改旧版本。未人工确认的点位仍是算法候选，接口的 review_kind 为空。

## 1. 本地 PowerShell：预览与核验文件

项目根目录运行（不启动数据库）：

```powershell
python -m app.import_rooms --scene KK-EEz16cmU14 --data-root .\data --probe-dir .\data\KK-EEz16cmU14\diagnostics\floorplan\20261027T063858Z_12484e9d --alignment-dir .\data\KK-EEz16cmU14\diagnostics\alignment\20261029T032340Z_177df64f --review-file .\data\KK-EEz16cmU14\diagnostics\alignment\20261029T032340Z_177df64f\review.json
```

若 `python` 启动器不可用，改用本机实际 Python 路径。预览不联网、不写库、不上传，也不修改输入文件。

人工核验文件放在同一个 alignment 私有目录，命名 review.json，不进入 Git。结构示例（替换为本次真实报告 SHA256 和复核信息）：

```json
{
  "scene_code": "YOUR_SCENE",
  "alignment_report_sha256": "REPORT_SHA256",
  "reviewed_by": "复核人",
  "reviewed_at": "2026-10-30T12:00:00+08:00",
  "xy_verified": true,
  "notes": "二维叠加核验；不代表高度和裁切已验证",
  "points": {
    "22": {"kind": "interior", "room_id": "Room8"},
    "32": {"kind": "doorway", "room_id": "Room8"},
    "42": {"kind": "outside", "room_id": null}
  }
}
```

报告哈希可用 `Get-FileHash -Algorithm SHA256 <报告路径>` 获取，JSON 内填写小写哈希。首期无核验文件也可导入草稿，但 xy_verified=false；不得据此自动裁切。核验文件中的 reviewed_by 是复核记录，不是已认证用户。

当前本地 alignment 目录已根据用户会话确认准备好 review.json，可直接使用；其中复核日期按会话记录，非精确操作时间，不包含账号或密钥。请随 alignment 目录单独上传，打包不会携带 data/。

## 2. 本地 PowerShell：打包上传

```powershell
.\release\scripts\build.ps1
.\release\scripts\deploy.ps1
```

build 会包含 app/db SQL、.dockerignore、本说明及全部测试源文件，不包含 data/ 或真实 env；旧安装包保留。Docker 构建采用默认排除、显式允许源码的规则，避免远端目录中的 .env/prod.env 和私有数据进入镜像。它不上传户型核验数据。

deploy 检查每条外部命令退出码。覆盖前 prepare_deploy.sh 检查 render_status.json，无运行任务才继续；异常/过期 running 状态需先人工核对。脚本将当前代码及配置备份到受保护的 `/data/zhaojy/burnroom-data/deploy-backups/{时间}/package.tar.gz`，给当前运行镜像打 rollback 标签，复制现有 output.mp4；若已有运行的 postgres，另做数据库备份。任一步失败不解压。请记录输出的 backup 和 rollback_image。目录含凭证，权限 700，不能上传仓库。第一次部署必须存在当前部署目录和运行后端；本脚本不是全新安装器。

此阶段只上传/备份/解压，不构建镜像，不重启现有容器。通过 WinSCP 将本次 alignment 目录（含 review.json）上传到：

`/data/zhaojy/burnroom-data/app-data/KK-EEz16cmU14/diagnostics/alignment/`

远端必须同时保留匹配的 points.json、mesh.obj、timeline.json 和成功 probe 目录。工具按内容哈希核对，不依赖报告里原来的 Windows 绝对路径。WinSCP 若提示同名文件覆盖，先比较/另存，不覆盖旧核验结果。

## 3. 远程 SSH：配置并启动

进入现有部署目录：

```bash
cd ~/burnroom-prod/burnroom-deploy-package
```

编辑远端 prod.env 和 .env，**仅追加** prod.env.example 中 PostgreSQL 相关变量；保留原 MinIO 密码、DK_APPKEY 等。PGPASSWORD 与 POSTGRES_PASSWORD 使用两个不同随机强密码。prod.env 注入容器，.env 供 Compose 插值。不要复制示例占位密码，不要将真实值发聊天或提交仓库。

以下逐条执行，每条成功再继续；不要整段不检查地粘贴。Compose 解析会要求 POSTGRES_PASSWORD；缺少它会使管理命令失败，但不会自动停止正在运行的旧容器。先配置正确再执行：

```bash
mkdir -p /data/zhaojy/burnroom-data/postgres
docker compose config --quiet
docker compose up -d postgres
docker compose ps postgres
```

确认 postgres 为 healthy；检查数据目录容量和权限。若目录已有 PG_VERSION，先确认版本及来源，不删除它。然后构建和检查镜像：

```bash
docker build -t burnroom-app:latest .
docker run --rm --network none --entrypoint python3 burnroom-app:latest -c "from pathlib import Path; assert not Path('/app/.env').exists(); assert not Path('/app/prod.env').exists(); print('image credentials excluded')"
```

确认没有渲染任务后，只重建后端，不重建 MinIO。后端将短暂中断：

```bash
docker compose up -d --no-deps --force-recreate app-server
curl --fail --silent --show-error --connect-timeout 5 --max-time 10 http://localhost:8000/
docker compose exec -T app-server python3 -m app.database
docker compose exec -T app-server python3 -m app.database
docker compose exec -T app-server python3 -m app.check_catalog
```

迁移执行两次均应成功，用于验证幂等；check_catalog 使用实际应用账号连接，检查账号不是超级用户且八表 SELECT/INSERT/UPDATE 授权齐全，不写数据。如果配置/迁移失败，停止导入；旧接口仍不依赖数据库。

等待 postgres 为 healthy 再执行迁移。官方 postgres:16 镜像若无法拉取，请使用管理员确认可用的镜像源，保持主版本 16，不随意切换现有数据目录的主版本。

迁移通过管理员连接创建表和专用 burnroom_app 登录角色，给应用必要的查询/写入权限，不授予超级用户/建库权限；版本和校验和用于重复执行检查。应用进程不在启动时自动建表。迁移需临时读取管理员密码，首期由现有 env_file 提供，后续可进一步独立迁移凭证。

Postgres 的初始化环境变量只作用于空数据目录。后续修改 .env 不会自动修改已有管理员密码，需用 SQL 管理账号，不得删除数据目录“重置”。

## 4. 远程 SSH：数据库集成测试

```bash
docker compose exec -T -e ROOM_DB_INTEGRATION=1 app-server python3 -m unittest test.test_room_database -v
```

测试使用随机独立 schema，并在事务结束回滚测试数据，不读取真实场景。验证八表建表、重复导入以及跨场景外键拒绝。仍需下一步以真实场景验证业务结果。未设置环境变量时数据库测试跳过，不应误报为已验证。

## 5. 远程 SSH：先预览，后导入

为减少重复输入，可以设置非敏感路径变量：

```bash
scene=KK-EEz16cmU14
probe=/app/data/$scene/diagnostics/floorplan/20261027T063858Z_12484e9d
alignment=/app/data/$scene/diagnostics/alignment/20261029T032340Z_177df64f
docker compose exec -T app-server python3 -m app.import_rooms --scene "$scene" --probe-dir "$probe" --alignment-dir "$alignment" --review-file "$alignment/review.json"
```

确认预览的数量及 xy_verified 后，执行：

```bash
docker compose exec -T app-server python3 -m app.import_rooms --scene "$scene" --probe-dir "$probe" --alignment-dir "$alignment" --review-file "$alignment/review.json" --apply
docker compose exec -T app-server python3 -m app.check_catalog --scene "$scene"
```

这里真实导入使用应用账号，配合应用账号查询验证授权。预期 rooms=6、valid_rooms=5、points=22、xy_verified=true。核对下一节人工关联后，再执行相同导入应返回 reused=true。最后单独登记上传状态：

```bash
docker compose exec -T app-server python3 -m app.import_rooms --scene "$scene" --probe-dir "$probe" --alignment-dir "$alignment" --review-file "$alignment/review.json" --apply --upload-assets
```

旧下载逻辑现只消费场景根目录文件，明确排除 catalog/history 等嵌套目录，不再将目录资源展开为当前渲染输入。

--apply 才写数据库；--upload-assets 才上传文件。对象采用内容哈希路径，不覆盖原有 output.mp4，也不触发 Blender。未上传时目录可查询，分享接口返回 409，不能假定历史缓存已在 MinIO。

MinIO 上传在 SQL 事务之前：上传失败不写入本次目录；数据库失败时可能留下未关联的内容哈希对象，重试可复用同一路径，本轮不自动删除对象。日志只显示错误类型，不输出密钥；如失败，先检查路径、环境和迁移状态。

## 6. 远程 SSH：SQL 与 API 查询

进入 SQL 终端：

```bash
docker compose exec postgres psql -U postgres -d burnroom
```

```sql
\dt
SELECT id, scene_code FROM scenes;
SELECT id, scene_id, xy_verified FROM layout_versions ORDER BY id DESC;
SELECT source_room_id, name, area_m2, is_valid FROM rooms ORDER BY id;
```

退出输入 `\q`。房间 API：

```bash
curl -fsS "http://localhost:8000/api/catalog/scenes/KK-EEz16cmU14/rooms"
```

取得返回的数据库房间 id 后，代入下面的数字位置（不是源编号 Room8）：

```text
GET /api/catalog/rooms/{id}/points
GET /api/catalog/rooms/{id}/assets
GET /api/catalog/assets/{asset_id}/share
```

rooms 可传 layout_version_id，默认最新导入版本；include_invalid=true 可查看异常区域。不要再不带 review-file 导入草稿，否则最新版本可能变成未核验版本（旧版保留）。预期：6 条房间记录、默认 5 个有效房间；22 个点位/归属记录；客厅内部13+门口1=14，次卧2、厨房4、卫生间1、阳台0；Room11无效。22 人工确认 interior/Room8；32 保留算法 boundary、人工 doorway/Room8；42 人工 outside、无房间。人工结论3条，其余19条仍是算法结果。当前完整本地输入对应29个文件；缺图时文件数会减少，22点位不代表22张图齐全。

首次导入前后应比较 mesh.obj、points.json、timeline.json、review.json 和旧 output.mp4 的 SHA256，确保未变；重复导入不增加同版记录，render_jobs 仍为空（尚未接入历史）。核验版本明确标记 xy_verified，不自动放行渲染。旧分享接口继续使用原路径，新增接口无登录保护，仅在现有内部/SSH 范围使用。浏览器仍受内网/SSH 隧道限制，签名主机不可手工替换。

部署前备份会记录当时已有的源文件/核验/视频哈希。将 backup_dir 设置为部署输出的实际备份目录后，可在远程核对（此次上传的新 review 文件不在旧快照中，另按报告绑定校验）：

```bash
sha256sum -c "$backup_dir/scene-inputs.sha256"
```

## 7. 备份与恢复（远程 SSH）

```bash
umask 077
mkdir -p /data/zhaojy/burnroom-data/backups
backup_file=/data/zhaojy/burnroom-data/backups/burnroom-$(date +%Y%m%d-%H%M%S).dump
docker compose exec -T postgres pg_dump -U postgres -d burnroom -Fc > "$backup_file.part" && mv "$backup_file.part" "$backup_file"
```

备份还需复制到另一存储位置；MinIO 文件另行备份。恢复演练使用另建的空库，保留生产库：

```bash
docker compose exec -T postgres createdb -U postgres burnroom_restore_check
```

将实际备份路径代入（不要直接执行尖括号占位符）：

```text
docker compose exec -T postgres pg_restore -U postgres -d burnroom_restore_check --no-owner --no-acl --exit-on-error < 实际备份文件路径
```

恢复后需重新配置授权（--no-owner/--no-acl 不恢复所有者和授权），再用应用账号查询，不能只验证管理员能读：

```bash
docker compose exec -T -e PGDATABASE=burnroom_restore_check app-server python3 -m app.database
docker compose exec -T -e PGDATABASE=burnroom_restore_check app-server python3 -m app.check_catalog --scene KK-EEz16cmU14
```

此处迁移会按当前配置重设共享应用角色密码；保持凭证与生产一致，不在恢复演练中变更密码。恢复演练库已存在时不要重复覆盖，先检查是否为空。以上步骤未在本地执行，数据库落盘不等于已完成恢复验收。

## 8. 后端部署失败回退（远程 SSH，按实际备份路径操作）

以下在确认需要回退、且无运行任务时逐条执行。将 deploy.ps1 输出的 backup 路径填入变量，不执行尖括号占位符：

```text
backup_dir=实际备份绝对路径
```

```bash
test -s "$backup_dir/package.tar.gz"
rollback_image=$(cat "$backup_dir/image-tag.txt")
deploy_path=$(cat "$backup_dir/deploy-path.txt")
docker image inspect "$rollback_image" > /dev/null
docker image tag "$rollback_image" burnroom-app:latest
tar -xzf "$backup_dir/package.tar.gz" -C "$deploy_path"
cd "$deploy_path"
docker compose up -d --no-deps --force-recreate app-server
curl --fail --silent --show-error --connect-timeout 5 --max-time 10 http://localhost:8000/
```

恢复旧代码、Compose、env 与镜像；新增文件可能保留，但运行的后端来自已保存旧镜像，无须重新构建。数据库、MinIO 与 app-data 不删除；此次导入不需要通过删库撤销。新数据库容器可暂时保留，后续再决定停用。不要执行 docker compose down -v、docker image prune 或删除数据目录，回退验证前保留 rollback 镜像。上述恢复不会覆盖成片；备份 videos/ 供必要时单独恢复，不自动替换当前视频。若原本没有数据库，数据库文件也继续保留；如果要回滚已有库的数据，先另行备份当前库，再制定恢复操作，不能顺手覆盖生产。
