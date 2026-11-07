# Room8 NVIDIA EEVEE 修复（2026-11-04）

**2026-11-05当前生效策略（替代下文保留gpus: all的中间方案）**：远端临时容器使用同一burnroom-app:latest镜像、runtime=nvidia、NVIDIA_VISIBLE_DEVICES=all及compute,utility,graphics，但不传--gpus时，EGL/GLX均加载成功且有10_nvidia.json；原应用Runtime=nvidia但带gpus: all仍未挂载图形库。应用改用已验证的runtime+环境变量路径：生产模板删除gpus，覆盖文件用gpus: !reset []清除远端基础compose继承的GPU DeviceRequests。只删除覆盖文件中的gpus行无法清除基础文件的值。先远端config --quiet验证Compose支持该合并语法，失败时不要重建；重建后必须Runtime=nvidia、DeviceRequests为null或空列表，且ctypes加载两个库为OK。容器重建后恢复/tmp/room8_gpu_code；正式首帧继续核验实际NVIDIA renderer，不因库加载成功就宣称EEVEE已使用GPU。不修改宿主机Docker全局配置或其他容器。

2026-11-05补充：宿主机已安装580.178.04图形库，但容器依然无库。只读检查显示Docker已注册nvidia运行时、默认及app-server实际运行时为runc，Toolkit/CLI均为1.20.0。因此生产模板与GPU覆盖文件均增加app-server.runtime: nvidia，显式走NVIDIA runtime；不修改Docker全局默认运行时、不重启Docker守护进程、不改其他容器。gpus: all及compute,utility,graphics保留。此次是有依据的下一步修复，仍须重建后检查实际Runtime=nvidia、库可加载及NVIDIA EGL JSON；不能仅凭运行时名称宣布EEVEE已使用GPU。

现有远端证据：4张L20可枚举，但NVIDIA_DRIVER_CAPABILITIES未设置，EGL vendor只有50_mesa.json，无libEGL_nvidia/libGLX_nvidia。NVIDIA Toolkit默认utility/compute不足以提供EEVEE所需graphics能力。配置修复不保证宿主机图形驱动本身完整，必须观察实际上下文。

只将release/docker-compose.gpu.yml上传为远端部署目录的docker-compose.gpu.yml，叠加现有compose。不要用本地生产模板整体替换远端compose或凭证。先确认旧Blender任务已停止；保留旧任务目录。不要使用docker compose down或删除卷。

在本地上传新版9个动画运行文件到独立宿主机目录/tmp/room8_gpu_code，保留原/tmp/room8_final_code。容器重新创建会清除容器/tmp，必须之后再复制脚本进去。

远程SSH，部署目录：

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --no-deps --force-recreate --no-build --pull never app-server
docker compose cp /tmp/room8_gpu_code app-server:/tmp/
```

第一条必须成功才继续。只重新创建app-server，后端短暂中断；MinIO/PostgreSQL不重启，原数据卷继续沿用，不需要镜像build。以后部署时保留这份覆盖文件并继续用两个-f参数，直到生产compose本身已包含图形能力修复。

继续使用run_room_animation.py的final/final/overview/--direct-final参数，但脚本和配置路径改为/tmp/room8_gpu_code，选择同一已验收基础资产；使用新任务，不传--resume旧CPU目录。第一帧仍属于正式576帧，不是新增样帧/短片测试。若实际上下文非NVIDIA，第一帧保留在attempt目录，立即失败，查看renderer.json，不重复启动。

成功证据：blender.log出现renderer=...NVIDIA L20...且software_rendering_suspected=False；manifest.renderer及worker_timing.json记录相同信息；宿主机nvidia-smi可观察Blender进程/显存/负载。第一帧完成前不能只凭nvidia-smi -L宣布GPU渲染已修复。

不在容器安装NVIDIA驱动，不猜测宿主机驱动版本，不设CUDA_VISIBLE_DEVICES来冒充EEVEE图形设备选择。若重建后仍无NVIDIA EGL库，需检查宿主机驱动与容器运行时，暂不继续正式渲染。

覆盖文件回退：先停止本次任务，再用原始compose文件单独重新创建app-server；挂载数据保留。容器/tmp会再次清空，脚本可从宿主机恢复；软件后端仍会被新版正式入口拒绝。
