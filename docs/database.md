# PostgreSQL 房间目录：部署与核验

2026-10-30：用户已确认设计。此文档是待远端验证的操作步骤，不代表部署已完成。

本地验证：58 项检查通过，1 项 PostgreSQL 集成检查跳过；建表 SQL 通过 PostgreSQL 语法解析，未实际建库。本地临时 Python 3.13 使用较新 Pydantic 验证接口（原有 2.3.0 缺少该 Python 版本的轮子），生产 requirements 中的原有版本未改，远端原环境仍须执行集成验证。PowerShell 打包脚本仅检查语法和 BOM，未运行打包或 Docker。

## 数据边界

八张业务表见 `app/db/001_rooms.sql`，迁移记录另存 `schema_migrations`。PostgreSQL 16 只在 Compose 内部监听，图片/模型留在 MinIO 或已有工作目录。运行状态仍以 render_status.json 为准，render_jobs/render_job_assets 本轮仅建表预留，不自动同步、不替代现有渲染流程。后续完整任务历史需独立任务目录，旧 output.mp4 不自动归入客厅。

导入的相机坐标若发生变化，当前工具拒绝覆盖，需先设计明确的场景修订；户型/核验内容变化则生成新户型版本。重复导入相同输入与核验时复用版本，保留已有人工结果和房间名称。新增核验文件会创建新版本，不修改旧版本。未人工确认的点位仍是算法候选，接口的 review_kind 为空。

## 1. 本地 PowerShell：预览与核验文件

项目根目录运行（不启动数据库）：

```powershell
python -m app.import_rooms --scene KK-EEz16cmU14 --data-root .\data --probe-dir .\data\KK-EEz16cmU14\diagnostics\floorplan\20261027T063858Z_12484e9d --alignment-dir .\data\KK-EEz16cmU14\diagnostics\alignment\20261029T032340Z_177df64f
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

build 会包含 app/db SQL 与本说明、数据库测试，不包含 data/ 或真实 env。它不上传户型核验数据。通过 WinSCP 将本次 alignment 目录（含 review.json）上传到：

`/data/zhaojy/burnroom-data/app-data/KK-EEz16cmU14/diagnostics/alignment/`

远端必须同时保留匹配的 points.json、mesh.obj、timeline.json 和成功 probe 目录。工具按内容哈希核对，不依赖报告里原来的 Windows 绝对路径。

## 3. 远程 SSH：配置并启动

进入现有部署目录：

```bash
cd ~/burnroom-prod/burnroom-deploy-package
```

编辑远端 prod.env 和 .env，**仅追加** prod.env.example 中 PostgreSQL 相关变量；保留原 MinIO 密码、DK_APPKEY 等。PGPASSWORD 与 POSTGRES_PASSWORD 使用两个不同随机强密码。prod.env 注入容器，.env 供 Compose 插值。不要复制示例占位密码，不要将真实值发聊天或提交仓库。

先建目录，再构建和启动；不会触发渲染：

```bash
mkdir -p /data/zhaojy/burnroom-data/postgres
docker compose up -d postgres
docker compose ps postgres
docker build -t burnroom-app:latest .
docker compose up -d --force-recreate app-server
docker compose exec -T app-server python3 -m app.database
```

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
docker compose exec -T app-server python3 -m app.import_rooms --scene "$scene" --probe-dir "$probe" --alignment-dir "$alignment" --review-file "$alignment/review.json" --apply --upload-assets
```

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

rooms 可传 layout_version_id，默认最新导入版本；include_invalid=true 可查看异常区域。客厅预期内部 13、门口 1、关联合计 14。42 不归属房间。核验版本明确标记 xy_verified，不自动放行渲染。旧分享接口继续使用原路径，新增接口无登录保护，仅在现有内部/SSH 范围使用。

## 7. 备份与恢复（远程 SSH）

```bash
mkdir -p /data/zhaojy/burnroom-data/backups
docker compose exec -T postgres pg_dump -U postgres -d burnroom -Fc > /data/zhaojy/burnroom-data/backups/burnroom-$(date +%Y%m%d-%H%M%S).dump
```

备份还需复制到另一存储位置；MinIO 文件另行备份。恢复演练使用另建的空库，保留生产库：

```bash
docker compose exec -T postgres createdb -U postgres burnroom_restore_check
```

将实际备份路径代入（不要直接执行尖括号占位符）：

```text
docker compose exec -T postgres pg_restore -U postgres -d burnroom_restore_check --no-owner --no-acl --exit-on-error < 实际备份文件路径
```

随后用 psql 连接 burnroom_restore_check 核对表和记录数量。以上步骤未在本地执行，数据库落盘不等于已完成恢复验收。
