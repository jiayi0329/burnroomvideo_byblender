# 第4批：新版Room8引擎与预设迁移

> 2026-11-11后续决定覆盖本文旧兼容约定：app/release源码与test旧包已移除，只使用新路径；SQL改为backend/database。当前操作见[正式路径说明](canonical_paths.md)，下文七批兼容过程仅作历史依据。本次不运行部署或渲染。

第7批后发布实现位于deploy/scripts，release/scripts旧命令继续转调；安装包仍输出release/out。本轮不改引擎40文件指纹。离线回归统一入口为`python -B -m tests.run_regression`，原test模块命令保留；完整仓库执行发布回归，不把Linux运行镜像等同于完整开发环境。见[发布边界](../deploy/README.md)及[收尾说明](migration_closeout.md)。

第5批后完整安装包还包含Backend源码及原样SQL，app旧入口依赖这些包；只传app文件仍不可用。Room8引擎及39文件指纹未变，数据库迁移/导入不会随打包、解压或普通引擎启动自动执行。具体边界见[Backend说明](../backend/README.md)。

2026-11-10第6批：共用对齐分析Core已独立，诊断源码迁入tools，Backend不导入诊断CLI。清单扩为40份，下面为当前完整包边界；不得用它续跑39文件清单的旧任务。算法/R3不改，工具见[tools/README](../tools/README.md)。

本轮只整理和离线验证，不部署、不重建容器、不重新出图或出片。旧V1资产、任务和配置保持原样。下列传输说明仅供之后明确授权运行时使用。

## 当前代码位置

实际实现位于[render_engine](../render_engine/README.md)，默认R3位于[configs/render](../configs/render/README.md)。app保留13份兼容模块，旧函数接口/CLI继续可用；旧全场景F8没有迁移。不能再使用历史文档中的“上传几个平铺脚本到/tmp”方案。

源码指纹由安装根目录计算，包含引擎、兼容入口和预设共40份文件；`preflight`仍接受旧app目录参数，也接受安装根。静帧同样使用完整清单。任何源码版本改变均新建任务；旧V1只能恢复归档版本运行，不能修改旧任务快照、帧记录或签名。

同一新版任务若需续跑，必须恢复原安装路径及完全相同的文件版本；不要换一个临时目录后强行复用旧帧。唯一安装目录用于隔离不同版本，不表示续跑可以更改源码位置。

## 本地PowerShell：以后需要传输时

在项目目录运行既有`release/scripts/build.ps1`生成tar.gz。安装包现在同时携带app、render_engine及三份configs/render预设；只复制命名Python源码/预设，不携带真实资产。缺失引擎文件/预设或兼容副本不一致时，打包失败并保留现场。脚本UTF-8 BOM保留。

此次不要求运行deploy.ps1或重建服务。未来如只验证独立引擎，可通过WinSCP把生成的tar.gz上传至服务器`/tmp/`，保持其唯一文件名；不要将归档内容直接覆盖现有部署或历史任务代码。

## 远程SSH：以后只读检查独立安装包

先进入既有Compose目录。将下方文件名占位符替换成实际包名；这些命令仅解压独立代码并看帮助，不启动渲染。正式执行前应确认当前没有依赖同一容器的其他维护动作。

```bash
cd ~/burnroom-prod/burnroom-deploy-package
package_name='替换为实际安装包文件名.tar.gz'
install_id=$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')
install_root="/tmp/room8-engine-$install_id"
docker compose exec -T app-server mkdir "$install_root"
docker compose cp "/tmp/$package_name" "app-server:$install_root/package.tar.gz"
docker compose exec -T app-server tar -xzf "$install_root/package.tar.gz" -C "$install_root"
engine_root="$install_root/burnroom-deploy-package"
docker compose exec -T app-server python3 "$engine_root/app/run_room_animation.py" --help
printf 'Engine root: %s\n' "$engine_root"
```

逐条执行，任何一步失败先停止。变量只在当前SSH会话有效；不运行docker compose down、不改挂载、不删旧/tmp或任务。解压目标为唯一临时目录，不覆盖/app/data或现有部署。以后的正式操作必须保留整棵目录和这些文件的版本。

## 实际入口（需另外授权才运行）

- 动画启动器：`$engine_root/app/run_room_animation.py`，实际worker自动选取`$engine_root/render_engine/blender/F8_room_animation.py`。
- 默认R3：`$engine_root/configs/render/room_fire_round3.json`；省略--config也会按安装位置找到它。
- 静帧：Blender的--python指向`$engine_root/render_engine/blender/F8_room_demo.py`。
- 资产生成：Blender的--python指向`$engine_root/render_engine/blender/F8_prepare_room_asset.py`。

资产、点位、人工核验和render_jobs仍使用原数据盘路径。当前不重新裁切、不生成短片或完整视频，不能因帮助命令成功就宣称远端GPU/视觉验收通过。

## 本地验证范围

新增`test/test_engine_migration.py`，覆盖新旧导入同一性、旧接口替换、跨工作目录CLI、Blender入口导入替身、默认R3、全部源码指纹、旧任务拒绝、安装包完整性/私有文件排除、解压后独立导入、缺文件/配置分叉时打包中止及BOM。

原AST测试改为读取实际实现，不删除原相机、UV、时序、编码、失败保留断言。测试中的出片日志来自合成进程；没有执行真实Blender、数据库、SSH或Docker。当前测试数量和未验证项见[test/README](../tests/README.md)。
