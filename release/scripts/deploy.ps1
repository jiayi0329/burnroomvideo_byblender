[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

# ==========================================
# 你的真实服务器信息
# ==========================================
$ServerIP = "172.25.76.201"
$ServerUser = "zhaojy"
$ServerPort = "7777"
$RemoteDir = "/home/zhaojy/burnroom-prod"  # 代码与脚本的存放地址
# ==========================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = (Get-Item $ScriptDir).Parent.Parent.FullName
$OutDir = Join-Path $ProjectRoot "release\out"

# 自动寻找 release/out/ 目录下最新生成的一个压缩包
$LatestPackage = Get-ChildItem -Path $OutDir -Filter "*.tar.gz" | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if (-not $LatestPackage) {
    Write-Host "❌ 错误: 找不到任何打包文件，请先运行 build.ps1 打包！" -ForegroundColor Red
    throw "请先运行 build.ps1"
}

$PackageName = $LatestPackage.Name
$PackagePath = $LatestPackage.FullName
if ($PackageName -notmatch '^burnroom-deploy-package-[A-Za-z0-9_.-]+\.tar\.gz$') { throw "安装包名称不合法" }

Write-Host "===> [1/3] 找到最新安装包: $PackageName" -ForegroundColor Cyan
Write-Host "===> [2/3] 正在通过 SCP 上传到服务器 (${ServerIP}:${ServerPort}) ..." -ForegroundColor Cyan

# 1. 在服务器上创建目标文件夹（如果不存在的话）
# 注意：ssh 指定端口用小写 -p
ssh -p $ServerPort ${ServerUser}@${ServerIP} "mkdir -p $RemoteDir"
if ($LASTEXITCODE -ne 0) { throw "远程目录检查失败，停止部署" }

# 2. 上传压缩包 
# 注意：scp 指定端口必须用大写 -P (这是 Linux 的硬性规定)
scp -P $ServerPort $PackagePath ${ServerUser}@${ServerIP}:${RemoteDir}/
if ($LASTEXITCODE -ne 0) { throw "安装包上传失败，停止部署" }
scp -P $ServerPort "$ScriptDir\prepare_deploy.sh" ${ServerUser}@${ServerIP}:${RemoteDir}/prepare_deploy.sh
if ($LASTEXITCODE -ne 0) { throw "部署前检查脚本上传失败，停止部署" }
ssh -p $ServerPort ${ServerUser}@${ServerIP} "bash -n $RemoteDir/prepare_deploy.sh && bash $RemoteDir/prepare_deploy.sh $RemoteDir"
if ($LASTEXITCODE -ne 0) { throw "备份或渲染任务检查失败；未解压覆盖代码" }

Write-Host "===> [3/3] 正在服务器上解压替换文件..." -ForegroundColor Cyan
# 3. 在服务器上解压文件并清理压缩包
$RemoteCommand = "cd $RemoteDir && tar -xzf $PackageName && rm $PackageName && echo '✅ 远程服务器解压部署完成！'"

ssh -p $ServerPort ${ServerUser}@${ServerIP} $RemoteCommand
if ($LASTEXITCODE -ne 0) { throw "远程解压失败；请使用上一步备份恢复，不要继续启动服务" }

Write-Host "=========================================" -ForegroundColor Green
Write-Host " 🚀 远程同步成功！代码已就绪！" -ForegroundColor Green
Write-Host " 💻 代码部署目录: $RemoteDir"
Write-Host " 🗄️ 数据存储目录: /data/zhaojy (稍后我们在远程启动配置中挂载)"
Write-Host "=========================================" -ForegroundColor Green
