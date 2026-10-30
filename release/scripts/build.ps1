[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
# release/scripts/build.ps1
$ErrorActionPreference = "Stop"

# 获取项目根目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = (Get-Item $ScriptDir).Parent.Parent.FullName
$OutDir = Join-Path $ProjectRoot "release\out"
$StagingDir = Join-Path $OutDir "burnroom-deploy-package"

# 定义版本号与时间戳 (符合tag 命名规范)
$Version = "v1.0.0"
$Timestamp = Get-Date -Format "yyyyMMdd"
$PackageName = "burnroom-deploy-package-$Version-$Timestamp.tar.gz"
$PackagePath = Join-Path $OutDir $PackageName

Write-Host "===> [1/4] 初始化打包环境..." -ForegroundColor Cyan
if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Path $StagingDir | Out-Null
New-Item -ItemType Directory -Path "$StagingDir/scripts" | Out-Null

Write-Host "===> [2/4] 组装核心代码与依赖..." -ForegroundColor Cyan
# 拷贝纯净代码，自动剔除本地缓存
Copy-Item -Path "$ProjectRoot\app" -Destination $StagingDir -Recurse
if (Test-Path "$StagingDir\app\__pycache__") { Remove-Item "$StagingDir\app\__pycache__" -Recurse -Force }
Copy-Item -Path "$ProjectRoot\Dockerfile" -Destination $StagingDir
Copy-Item -Path "$ProjectRoot\requirements.txt" -Destination $StagingDir
Copy-Item -Path "$ProjectRoot\docs" -Destination $StagingDir -Recurse
New-Item -ItemType Directory -Path "$StagingDir/test" | Out-Null
Copy-Item -Path "$ProjectRoot\test\test_room_database.py" -Destination "$StagingDir/test"
Copy-Item -Path "$ProjectRoot\test\__init__.py" -Destination "$StagingDir/test"

Write-Host "===> [3/4] 注入生产环境配置..." -ForegroundColor Cyan
# 提取 release 中的服务器专属配置，并重命名为标准名称供服务器直接使用
Copy-Item -Path "$ProjectRoot\release\docker-compose.prod.yml" -Destination "$StagingDir\docker-compose.yml"
Copy-Item -Path "$ProjectRoot\release\prod.env.example" -Destination "$StagingDir\prod.env.example"
# 创建占位数据文件夹 (供服务器挂载模型与产物使用)
New-Item -ItemType Directory -Path "$StagingDir\data" | Out-Null
Set-Content -Path "$StagingDir\data\.gitkeep" -Value ""

Write-Host "===> [4/4] 压缩封箱 (生成 .tar.gz)..." -ForegroundColor Cyan
Set-Location $OutDir
# 使用 Windows 10/11 自带的 tar 命令生成 Linux 友好的压缩包
tar -czf $PackageName (Split-Path $StagingDir -Leaf)
Remove-Item $StagingDir -Recurse -Force
Set-Location $ProjectRoot

Write-Host "=========================================" -ForegroundColor Green
Write-Host " 打包成功！(符合 DevOps 交付规范)" -ForegroundColor Green
Write-Host " 产物名称: $PackageName"
Write-Host " 产物路径: $PackagePath"
Write-Host "=========================================" -ForegroundColor Green
