# 单房间候选资产：当前演示近似策略

**本次只运行 F8-B：app/F8_prepare_room_asset.py。** F8-A（F8_inspect_room_import.py）是已完成的原模型导入检查；F8-C（F8_blender_render.py）是旧完整视频入口，本轮不运行。各脚本头部已有标记，完整索引见 [app/README.md](../app/README.md)。

2026-11-02 用户确认：Room8 采用平层地板近似，参考地板 -1.35m（主导下包络候选）。不再等待地板、平台、吊顶、墙厚的真实建筑语义确认。旧诊断及 review.json 不改，历史 ready_for_cut=false 不作回填；新 candidate 单独记录工程放行依据，physical_semantics_verified=false。该策略优先于 room_asset_checks.md / room_section_diagnostics.md 的旧物理确认门槛。

裁切用已核验的 11 顶点多边形及其逆变换，严格零外扩。跨边三角面插值 UV，保留原材质和原始 XYZ，不按对象包围盒保留整个全屋。它是开放边界候选，不保证墙厚完整、水密或没有任何纹理中拍到的邻房内容。地板为独立演示对象；扫描模型中更高的平台/家具仍保留，若检查图显示遮挡，再调整展示副本，不能假称已完成平台识别。

## 第一阶段：本地 PowerShell

在 D:\burnroomvideo_byblender，使用可用的 Python（本机 launcher 失效时使用实际 Python313 路径）：

```powershell
& 'C:\Users\86182\AppData\Local\Programs\Python\Python313\python.exe' -m unittest test.test_room_candidate -v
& 'C:\Users\86182\AppData\Local\Programs\Python\Python313\python.exe' -m app.prepare_room_candidate --data-root data --inspection data/KK-EEz16cmU14/diagnostics/room_inspection/20261031T033807Z_79b97ce7/inspection.json --blender-report data/KK-EEz16cmU14/diagnostics/room_inspection/20261031T033807Z_79b97ce7/remote_import_user_output.json --alignment-dir data/KK-EEz16cmU14/diagnostics/alignment/20261029T032340Z_177df64f --floor-z -1.35 --accept-flat-floor
```

此命令只生成候选 JSON，不启动 Blender。证据文件是用户提供终端输出的本地记录，provenance 保留这一来源，不将它冒称远端原始报告。可替换为已下载的原始 blender_import.json，但必须对应当前 inspection 指纹。

控制台会给出独立版本路径。不同房间可复用该工具，需换相应 inspection、导入证据和参考高度；不会自动将 Room8 的高度应用到其他房间。

接着上传三个文件（把 <版本目录> 换成此次输出的 UTC_UUID；不要原样粘贴占位符）。2026-11-09起，B入口依赖同目录的`F8_room_helpers.py`；本页保留资产生成步骤，当前迁移不重新裁切或出图：

```powershell
scp -P 7777 .\app\F8_prepare_room_asset.py zhaojy@172.25.76.201:/tmp/burnroom_prepare_room_asset.py
scp -P 7777 .\app\F8_room_helpers.py zhaojy@172.25.76.201:/tmp/F8_room_helpers.py
scp -P 7777 .\data\KK-EEz16cmU14\rooms\Room8\<版本目录>\candidate.json zhaojy@172.25.76.201:/tmp/burnroom_room_candidate.json
```

本轮临时测试无需重建镜像，也无需在远端编辑代码。原始 OBJ/MTL/贴图及 points/timeline 必须与本地指纹一致；若远端历史视频与候选记录不同，会拒绝并要求核对，不能靠删除视频绕过。

## 第二阶段：远程 SSH

在远端现有部署目录执行，先逐行输入：

```bash
cd ~/burnroom-prod/burnroom-deploy-package
run_id=$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')
room_run="/app/data/KK-EEz16cmU14/rooms/Room8/$run_id"
docker compose exec -T app-server mkdir -p "$room_run"
docker compose cp /tmp/burnroom_prepare_room_asset.py app-server:/tmp/burnroom_prepare_room_asset.py
docker compose cp /tmp/F8_room_helpers.py app-server:/tmp/F8_room_helpers.py
docker compose cp /tmp/burnroom_room_candidate.json "app-server:$room_run/candidate.json"
docker compose exec -T app-server blender --background --factory-startup --python-exit-code 1 --python /tmp/burnroom_prepare_room_asset.py -- --candidate "$room_run/candidate.json" --data-root /app/data --display-height 2.4
printf 'Result directory: %s/asset\n' "$room_run"
```

这次只生成静态检查图，不生成动画或视频，不访问数据库，不调用旧渲染 API。容器用户创建目录可避免 SSH 用户写 root 属主目录的权限问题；不要 chmod 整个数据盘。若 mkdir/复制失败，停止后续命令先处理错误。变量与执行命令需在同一个 SSH 会话中运行。

默认人工剖切 Z=-1.35+2.4=1.05m，只用于展示去顶，不是测量层高。内部镜头在参考地板以上 1.6m，XY 通过多边形内部离边界较远的采样选择，朝向起火点；TRACK_TO 保持。三视图用来暴露遮挡问题，仍需人工检查穿墙/遮挡，不承诺静态算法已验证视线畅通。

若失败，查看 asset/failure.json 和控制台 Traceback；不要在同一 asset 目录强行重跑。再次执行时新建 run_id，保留失败现场。

## 第三阶段：WinSCP 检查及结果回传

WinSCP 打开远端：`/data/zhaojy/burnroom-data/app-data/KK-EEz16cmU14/rooms/Room8/<run_id>/asset/`，下载到本地 data 下相应独立目录。

| 文件 | 用途/预期 |
|---|---|
| room.blend | 保留原始 XYZ、UV/材质、打包贴图的基础候选；未为看清内部删除顶部和墙体 |
| room.glb | 网页候选资产，图片/缓冲内嵌；标准 Y-up，坐标映射见 manifest |
| validation.json | status=passed，重载快照一致、贴图打包可用、GLB 自包含；point_count=14（13 内部+1 门口），重载点位位置/归属/参考地板及坐标来源元数据一致；不等于人工视觉通过 |
| top.png、oblique.png、interior.png | 俯视、斜视、内部视角；均使用派生剖面几何 |
| section_preview.blend | 带展示去顶、镜头和照明的副本；不能替代 room.blend |
| manifest.json | 来源指纹、近似策略、坐标映射、点位、视角及产物指纹；source_and_history_unchanged=true |
| failure.json | 仅失败时出现；存在时该版本不可接入效果 |

人工检查：客厅范围没有明显混入卧室/厨房；UV 和贴图没有错位；镜头内部可见、不过墙；演示地板/扫描平台不遮挡主要起火区域；基础资产顶部墙体仍保留。Room8 应有 13 个内部点、32 号独立门口点、42 号不纳入；22 号为内部起火点。

基础 blend 内 Point_<编号> 是点位 Empty 标记，不会在 PNG 中画出球体；保存原始相机 XYZ、内部/门口归属及单独的火源参考高度。GLB 导出 extras 保留这些自定义属性。重载检查读取基础 blend 验证这些点位；当前 GLB 仅做文件结构、自包含和贴图存在检查，未做 GLB 重新导入或浏览器视觉验收。

确认图像通过后再进入效果阶段：只在内部子图重新计算蔓延时间，32 号边界策略单列、不向其他房间传播；火源以参考地板定位，先火焰、再烟雾/灯光；独立目录生成样帧、短片、完整视频。20 分钟为性能目标，须按实测准备/逐帧/编码耗时判断。当前代码没有接入旧 F8、没有生成完整视频。
