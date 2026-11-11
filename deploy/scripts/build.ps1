[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
# deploy/scripts/build.ps1: canonical release implementation
$ErrorActionPreference = "Stop"

# 获取项目根目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = (Get-Item $ScriptDir).Parent.Parent.FullName
# Require canonical production templates and standalone helper.
foreach ($Relative in @('docker-compose.prod.yml', 'docker-compose.gpu.yml', 'prod.env.example', 'scripts/prepare_deploy.sh')) {
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "deploy/$Relative") -PathType Leaf)) { throw "Required deployment template/helper missing: $Relative" }
}
$OutDir = Join-Path $ProjectRoot "release\out"
$BuildId = (Get-Date -Format "yyyyMMdd-HHmmssfff") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
$WorkDir = Join-Path $OutDir ".stage-$BuildId"
$StagingDir = Join-Path $WorkDir "burnroom-deploy-package"

# 定义版本号与时间戳 (符合tag 命名规范)
$Version = "v1.0.0"
$Timestamp = $BuildId
$PackageName = "burnroom-deploy-package-$Version-$Timestamp.tar.gz"
$PackagePath = Join-Path $OutDir $PackageName
$PartialPackagePath = "$PackagePath.part"

Write-Host "===> [1/4] 初始化打包环境..." -ForegroundColor Cyan
New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null

Write-Host "===> [2/4] 组装核心代码与依赖..." -ForegroundColor Cyan
# 拷贝纯净代码，自动剔除本地缓存
# Backend implementations and unchanged baseline SQL accompany all app shims.
$BackendModules = @{
    api = @('main', 'room_api')
    'adapters/postgres' = @('database')
    'adapters/minio' = @('s3_io')
    cli = @('import_rooms', 'check_catalog')
    services = @('observability')
}
$BackendFiles = @('backend/__init__.py', 'backend/paths.py', 'backend/adapters/__init__.py', 'backend/database/migrations/001_rooms.sql')
foreach ($Group in $BackendModules.Keys) {
    $BackendFiles += "backend/$Group/__init__.py"
    foreach ($Module in $BackendModules[$Group]) { $BackendFiles += "backend/$Group/$Module.py" }
}
foreach ($Relative in $BackendFiles) {
    $Source = Join-Path $ProjectRoot $Relative
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Required backend source/migration missing: $Relative" }
    $Destination = Join-Path $StagingDir $Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination
}
if ((Get-FileHash -LiteralPath (Join-Path $ProjectRoot 'backend/database/migrations/001_rooms.sql') -Algorithm SHA256).Hash -ne 'F87B9E6D1C6513FA7F8FE00C0FA2D3674796CD136CDC5B4C9080967FE97E5668') {
    throw 'Baseline migration changed; do not edit applied migrations'
}
# Canonical Room8 and Legacy engine packages.
$EngineModules = @{
    blender = @('F8_prepare_room_asset', 'F8_room_demo', 'F8_room_animation', 'F8_room_fire_style', 'F8_room_helpers')
    jobs = @('run_room_animation', 'room_animation_job')
    effects = @('room_fire_config')
    propagation = @('room_demo_plan')
    geometry = @('room_source_io', 'room_source_inputs', 'room_clip_geometry', 'prepare_room_candidate', 'floorplan_alignment')
    legacy = @('F6_detect', 'F7_spread', 'F8_blender_render')
}
$EngineFiles = @('render_engine/__init__.py', 'render_engine/paths.py')
foreach ($Group in $EngineModules.Keys) {
    $EngineFiles += "render_engine/$Group/__init__.py"
    foreach ($Module in $EngineModules[$Group]) { $EngineFiles += "render_engine/$Group/$Module.py" }
}
foreach ($Relative in $EngineFiles) {
    $Source = Join-Path $ProjectRoot $Relative
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Required engine source missing: $Relative" }
    $Destination = Join-Path $StagingDir $Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination
}
$ApprovedPresetHashes = @{
    1 = 'F1F6A552746C999C416BC7DA5B36A4FF0F515F596140D6C0D6588F774B41A815'
    2 = '6E99A2327305A668458BEA516D9DE87285164EC4C7BA67B0C21F41D5B59CE375'
    3 = 'AF9854A21F47E840C837B9299584D4D7D9FD74DFA4FAC19251E91873369D4202'
}
foreach ($Revision in 1, 2, 3) {
    $Relative = "configs/render/room_fire_round$Revision.json"
    $Source = Join-Path $ProjectRoot $Relative
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Required render preset missing: $Relative" }
    if ((Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash -ne $ApprovedPresetHashes[$Revision]) { throw "Approved render preset changed: $Relative" }
    $Destination = Join-Path $StagingDir $Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination
}
# Explicit diagnostic sources only. Manual integration tools are not production code.
$DiagnosticFiles = @(
    'tools/__init__.py', 'tools/diagnostics/__init__.py',
    'tools/diagnostics/diagnose_room_sections.py',
    'tools/diagnostics/room_section_geometry.py', 'tools/diagnostics/room_section_plots.py',
    'tools/diagnostics/analyze_floorplan.py', 'tools/diagnostics/inspect_room_asset.py',
    'tools/diagnostics/probe_floorplan.py', 'tools/diagnostics/blender/__init__.py',
    'tools/diagnostics/blender/F8_inspect_room_import.py'
)
foreach ($Relative in $DiagnosticFiles) {
    $Source = Join-Path $ProjectRoot $Relative
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Required diagnostic source missing: $Relative" }
    $Destination = Join-Path $StagingDir $Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination
}
Copy-Item -Path "$ProjectRoot\Dockerfile" -Destination $StagingDir
Copy-Item -LiteralPath "$ProjectRoot\.dockerignore" -Destination $StagingDir
Copy-Item -Path "$ProjectRoot\requirements.txt" -Destination $StagingDir
Copy-Item -Path "$ProjectRoot\docs" -Destination $StagingDir -Recurse
# Canonical test sources only, never generated test artifacts.
$TestEntries = @(
    'tests/__init__.py', 'tests/suites.py', 'tests/run_regression.py',
    'tests/backend/__init__.py', 'tests/engine/__init__.py',
    'tests/tools/__init__.py', 'tests/deploy/__init__.py',
    'tests/deploy/test_migration_cleanup.py', 'tests/deploy/test_canonical_layout.py'
)
foreach ($Relative in $TestEntries) {
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $Relative) -PathType Leaf)) { throw "Required test entry missing: $Relative" }
}
foreach ($Folder in @('tests')) {
    $SourceRoot = Join-Path $ProjectRoot $Folder
    if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container)) { throw "Required test package missing: $Folder" }
    Get-ChildItem -LiteralPath $SourceRoot -Recurse -File | Where-Object {
        $_.Extension -eq '.py' -or $_.Name -eq 'README.md'
    } | ForEach-Object {
        $Relative = $_.FullName.Substring($SourceRoot.Length).TrimStart([IO.Path]::DirectorySeparatorChar)
        $Destination = Join-Path (Join-Path $StagingDir $Folder) $Relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $Destination
    }
}
# Even an accidentally placed nested credential must not enter the archive.
$StagePrefix = [IO.Path]::GetFullPath($StagingDir) + [IO.Path]::DirectorySeparatorChar
Get-ChildItem -LiteralPath $StagingDir -File -Recurse -Force | Where-Object {
    $_.Name -eq '.env' -or $_.Name -like '.env.*' -or $_.Name -eq 'prod.env' -or $_.Extension -in '.pem', '.key'
} | ForEach-Object {
    if (-not $_.FullName.StartsWith($StagePrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "非预期暂存文件路径" }
    Remove-Item -LiteralPath $_.FullName -Force
}

Write-Host "===> [3/4] 注入生产环境配置..." -ForegroundColor Cyan
# 提取 deploy 中的服务器专属模板，保留服务器上的标准文件名
Copy-Item -Path "$ProjectRoot\deploy\docker-compose.prod.yml" -Destination "$StagingDir\docker-compose.yml"
Copy-Item -Path "$ProjectRoot\deploy\prod.env.example" -Destination "$StagingDir\prod.env.example"
# 创建占位数据文件夹 (供服务器挂载模型与产物使用)
New-Item -ItemType Directory -Path "$StagingDir\data" | Out-Null
Set-Content -Path "$StagingDir\data\.gitkeep" -Value ""

Write-Host "===> [4/4] 压缩封箱 (生成 .tar.gz)..." -ForegroundColor Cyan
# 使用 Windows 10/11 自带的 tar 命令生成 Linux 友好的压缩包
tar -czf $PartialPackagePath -C $WorkDir (Split-Path $StagingDir -Leaf)
if ($LASTEXITCODE -ne 0) { throw "tar 打包失败；保留暂存目录供检查：$WorkDir" }
Move-Item -LiteralPath $PartialPackagePath -Destination $PackagePath -ErrorAction Stop
$ResolvedWorkDir = (Resolve-Path -LiteralPath $WorkDir).Path
$ExpectedWorkDir = [IO.Path]::GetFullPath((Join-Path $ProjectRoot "release\out\.stage-$BuildId"))
if ($ResolvedWorkDir -ne $ExpectedWorkDir) { throw "拒绝清理非预期暂存目录" }
Remove-Item -LiteralPath $ResolvedWorkDir -Recurse -Force

Write-Host "=========================================" -ForegroundColor Green
Write-Host " 打包成功！(符合 DevOps 交付规范)" -ForegroundColor Green
Write-Host " 产物名称: $PackageName"
Write-Host " 产物路径: $PackagePath"
Write-Host "=========================================" -ForegroundColor Green
