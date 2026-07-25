<#
.SYNOPSIS
  把同一版本号写入所有发布清单。

.DESCRIPTION
  set-version.ps1 接收一个 SemVer 版本号，更新：
  - VERSION（仓库根目录的规范版本文件）
  - backend/langdrill_agent/__init__.py
  - pyproject.toml
  - frontend/package.json
  - frontend/package-lock.json（同步 root package.version）
  - frontend/src/features/update/UpdateCenter.tsx
  - src-tauri/Cargo.toml
  - src-tauri/Cargo.lock（重新生成，避免脏 lockfile）
  - src-tauri/tauri.conf.json
  - 演示web2/src/demoVersion.ts（发布渠道元数据）
  - 演示web2/src/mock/features/update/UpdateCenter.tsx

  本脚本只做确定性字符串替换，不调用模型或网络。
  Cargo.lock 通过 cargo update --workspace --offline 重新生成；
  package-lock.json 通过 npm install --package-lock-only 重新生成。

.PARAMETER Version
  目标版本号，必须是合法 SemVer，例如 1.0.1 或 1.0.0-alpha.2。

.PARAMETER Channel
  演示站 channel 字段，可选 experimental 或 stable，默认 experimental。

.EXAMPLE
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\release\set-version.ps1 -Version 1.0.1 -Channel experimental
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [string]$Channel = "experimental"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path (Join-Path $PSScriptRoot "..") "..")
Set-Location $repoRoot

# 1. 校验 SemVer：MAJOR.MINOR.PATCH[-prerelease][+build]
#    使用简化正则避免 PowerShell 解析器对复杂字符类的处理问题。
$semverOk = $Version -match '^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?(\+[a-zA-Z0-9.-]+)?$'
if (-not $semverOk) {
    throw "Invalid SemVer: $Version"
}

# 2. 发布渠道与 SemVer 是否带预发布后缀相互独立。
#    GitHub Release 的 prerelease 元数据由工作流控制，不能据此伪造版本号后缀。
if ($Channel -notin @("experimental", "stable")) {
    throw "Channel must be experimental or stable; got: $Channel"
}

function Set-FileContent {
    param([string]$Path, [string]$Content)
    [System.IO.File]::WriteAllText($Path, $Content, (New-Object System.Text.UTF8Encoding $false))
}

# 3. VERSION 文件
Set-FileContent (Join-Path $repoRoot "VERSION") "$Version`n"

# 4. 后端包版本
$backendInitPath = Join-Path $repoRoot "backend\langdrill_agent\__init__.py"
$backendInit = Get-Content $backendInitPath -Raw -Encoding UTF8
$backendInit = $backendInit -replace '__version__\s*=\s*"[^"]+"', "__version__ = `"$Version`""
Set-FileContent $backendInitPath $backendInit

# 5. pyproject.toml：仅替换顶层 version = "..."，保留原文件行尾
$pyprojectPath = Join-Path $repoRoot "pyproject.toml"
$pyproject = Get-Content $pyprojectPath -Raw -Encoding UTF8
$pyprojectRegex = [regex]::new('(?m)^version\s*=\s*"[^"]+"')
if (-not $pyprojectRegex.IsMatch($pyproject)) {
    throw "pyproject.toml version not updated; check format"
}
$pyprojectNew = $pyprojectRegex.Replace($pyproject, "version = `"$Version`"", 1)
Set-FileContent $pyprojectPath $pyprojectNew

# 6. frontend/package.json（用 Node.js 保持 2 空格缩进格式）
$frontendPkgPath = Join-Path $repoRoot "frontend\package.json"
$nodeScript = "const fs=require('fs'); const p=process.argv[1]; const j=JSON.parse(fs.readFileSync(p,'utf8')); j.version=process.argv[2]; fs.writeFileSync(p, JSON.stringify(j,null,2)+'\n');"
& node -e $nodeScript $frontendPkgPath $Version
if ($LASTEXITCODE -ne 0) {
    throw "node: failed to update frontend/package.json"
}

# 7. frontend/package-lock.json：先更新 package.json，再让 npm 重新生成 lockfile。
#    PowerShell 5.1 的 ConvertFrom-Json 无法处理 package-lock.json 中的空字符串键，
#    所以跳过手改，直接依赖 npm install --package-lock-only 写入正确版本。
Push-Location (Join-Path $repoRoot "frontend")
try {
    & npm install --package-lock-only --no-audit --no-fund 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "npm install --package-lock-only failed"
    }
} finally {
    Pop-Location
}

# 8. 更新中心 Web 默认版本与演示站 mock 默认版本
$updateCenterPaths = @(
    (Join-Path $repoRoot "frontend\src\features\update\UpdateCenter.tsx"),
    (Join-Path $repoRoot "演示web2\src\mock\features\update\UpdateCenter.tsx")
)
foreach ($updateCenterPath in $updateCenterPaths) {
    $updateCenter = Get-Content $updateCenterPath -Raw -Encoding UTF8
    $updateCenter = $updateCenter -replace 'const DEFAULT_CURRENT_VERSION = "[^"]+";', "const DEFAULT_CURRENT_VERSION = `"$Version`";"
    Set-FileContent $updateCenterPath $updateCenter
}

# 9. src-tauri/Cargo.toml：替换 [package].version，保留原文件行尾
$cargoTomlPath = Join-Path $repoRoot "src-tauri\Cargo.toml"
$cargoToml = Get-Content $cargoTomlPath -Raw -Encoding UTF8
$cargoRegex = [regex]::new('(?ms)(^\[package\][^\[]*?^version\s*=\s*")[^"]+(")')
if (-not $cargoRegex.IsMatch($cargoToml)) {
    throw "Cargo.toml version not updated"
}
$cargoNew = $cargoRegex.Replace(
    $cargoToml,
    { param($match) $match.Groups[1].Value + $Version + $match.Groups[2].Value },
    1
)
Set-FileContent $cargoTomlPath $cargoNew

# 10. src-tauri/tauri.conf.json（用 Node.js 保持 2 空格缩进格式）
$tauriConfPath = Join-Path $repoRoot "src-tauri\tauri.conf.json"
$nodeScript2 = "const fs=require('fs'); const p=process.argv[1]; const j=JSON.parse(fs.readFileSync(p,'utf8')); j.version=process.argv[2]; fs.writeFileSync(p, JSON.stringify(j,null,2)+'\n');"
& node -e $nodeScript2 $tauriConfPath $Version
if ($LASTEXITCODE -ne 0) {
    throw "node: failed to update tauri.conf.json"
}

# 11. src-tauri/Cargo.lock：用 cargo update --workspace 重新生成，
#     避免 lockfile 与 Cargo.toml 不一致导致 test 失败。
#     cargo 输出到 stderr，需用 cmd /c 包装避免 PS ErrorActionPreference=Stop 误判。
Push-Location (Join-Path $repoRoot "src-tauri")
try {
    cmd /c "cargo update --workspace --offline 2>&1" 1>$null
    if ($LASTEXITCODE -ne 0) {
        cmd /c "cargo update --workspace 2>&1" 1>$null
        if ($LASTEXITCODE -ne 0) {
            throw "cargo update failed"
        }
    }
} finally {
    Pop-Location
}

# 12. 演示web2/src/demoVersion.ts
$demoDir = Join-Path $repoRoot "演示web2\src"
if (-not (Test-Path $demoDir)) {
    New-Item -ItemType Directory -Path $demoDir -Force | Out-Null
}
$demoTs = @"
// 演示站发布渠道元数据。
// 由 scripts/release/set-version.ps1 自动生成，不要手动编辑。
// 仅用于演示站显示，不连接真实后端。
export const demoVersion = {
  version: "$Version",
  channel: "$Channel",
} as const;
"@
Set-FileContent (Join-Path $demoDir "demoVersion.ts") "$demoTs`n"

Write-Host "set-version: $Version (channel=$Channel)" -ForegroundColor Green
Write-Host "  - VERSION"
Write-Host "  - backend/langdrill_agent/__init__.py"
Write-Host "  - pyproject.toml"
Write-Host "  - frontend/package.json + package-lock.json + UpdateCenter.tsx"
Write-Host "  - src-tauri/Cargo.toml + Cargo.lock + tauri.conf.json"
Write-Host "  - 演示web2/src/demoVersion.ts + mock UpdateCenter.tsx"
