# Compatibility entry; implementation lives in deploy/scripts.
$ErrorActionPreference = "Stop"
$ProjectRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$Implementation = Join-Path $ProjectRoot "deploy/scripts/deploy.ps1"
if (-not (Test-Path -LiteralPath $Implementation -PathType Leaf)) { throw "Required deployment implementation missing: $Implementation" }
& $Implementation @args
