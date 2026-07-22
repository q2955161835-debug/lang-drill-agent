<#
.SYNOPSIS
  把同一版本号写入所有发布清单。

.DESCRIPTION
  set-version.ps1 接收一个 SemVer 版本号，更新：
  - VERSION（仓库根目录的规范版本文件）
  - pyproject.toml
  - frontend/package.json
  - frontend/package-lock.json（同步 root package.version）
  - src-tauri/Cargo.toml
  - src-tauri/Cargo.lock（重新生成，避免脏 lockfile）
  - src-tauri/tauri.conf.json
  - 演示web2/src/demoVersion.ts（实验版元数据）

  本脚本只做确定性字符串替换，不调用模型或网络。
  Cargo.lock 通过 cargo update --workspace --offline 重新生成；
  package-lock.json 通过 npm install --package-lock-only 重新生成。

.PARAMETER Version
  目标版本号，必须是合法 SemVer，例如 1.0.0-experimental.1。

.PARAMETER Channel
  演示站 channel 字段，默认 experimental。Task 5 强制实验版，不接收 stable。

.EXAMPLE
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\release\set-version.ps1 -Version 1.0.0-experimental.1
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

# 2. 拒绝 stable 版本：本任务只允许实验版（带 prerelease 标签）。
if (-not $Version.Contains('-')) {
    throw "Task 5 requires a prerelease (experimental) version; got stable: $Version"
}

if ($Channel -ne "experimental") {
    throw "Task 5 requires channel=experimental; got: $Channel"
}

function Set-FileContent {
    param([string]$Path, [string]$Content)
    [System.IO.File]::WriteAllText($Path, $Content, (New-Object System.Text.UTF8Encoding $false))
}

# 3. VERSION 文件
Set-FileContent (Join-Path $repoRoot "VERSION") "$Version`n"

# 4. pyproject.toml：仅替换顶层 version = "..."（逐行匹配，兼容 PS 5.1）
$pyprojectPath = Join-Path $repoRoot "pyproject.toml"
$pyprojectLines = Get-Content $pyprojectPath -Encoding UTF8
$pyprojectFound = $false
for ($i = 0; $i -lt $pyprojectLines.Count; $i++) {
    if ($pyprojectLines[$i] -match '^version\s*=\s*"([^"]+)"') {
        $pyprojectLines[$i] = "version = `"$Version`""
        $pyprojectFound = $true
        break
    }
}
if (-not $pyprojectFound) {
    throw "pyproject.toml version not updated; check format"
}
$pyprojectNew = ($pyprojectLines -join "`r`n") + "`r`n"
Set-FileContent $pyprojectPath $pyprojectNew

# 5. frontend/package.json（用 Node.js 保持 2 空格缩进格式）
$frontendPkgPath = Join-Path $repoRoot "frontend\package.json"
$nodeScript = "const fs=require('fs'); const p=process.argv[1]; const j=JSON.parse(fs.readFileSync(p,'utf8')); j.version=process.argv[2]; fs.writeFileSync(p, JSON.stringify(j,null,2)+'\n');"
& node -e $nodeScript $frontendPkgPath $Version
if ($LASTEXITCODE -ne 0) {
    throw "node: failed to update frontend/package.json"
}

# 6. frontend/package-lock.json：先更新 package.json，再让 npm 重新生成 lockfile。
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

# 8. src-tauri/Cargo.toml：替换 [package].version（逐行，[package] 段后第一个 version）
$cargoTomlPath = Join-Path $repoRoot "src-tauri\Cargo.toml"
$cargoLines = Get-Content $cargoTomlPath -Encoding UTF8
$inPackage = $false
$cargoFound = $false
for ($i = 0; $i -lt $cargoLines.Count; $i++) {
    if ($cargoLines[$i] -match '^\[package\]') { $inPackage = $true; continue }
    if ($cargoLines[$i] -match '^\[') { $inPackage = $false; continue }
    if ($inPackage -and $cargoLines[$i] -match '^version\s*=\s*"([^"]+)"') {
        $cargoLines[$i] = "version = `"$Version`""
        $cargoFound = $true
        break
    }
}
if (-not $cargoFound) {
    throw "Cargo.toml version not updated"
}
$cargoNew = ($cargoLines -join "`r`n") + "`r`n"
Set-FileContent $cargoTomlPath $cargoNew

# 9. src-tauri/tauri.conf.json（用 Node.js 保持 2 空格缩进格式）
$tauriConfPath = Join-Path $repoRoot "src-tauri\tauri.conf.json"
$nodeScript2 = "const fs=require('fs'); const p=process.argv[1]; const j=JSON.parse(fs.readFileSync(p,'utf8')); j.version=process.argv[2]; fs.writeFileSync(p, JSON.stringify(j,null,2)+'\n');"
& node -e $nodeScript2 $tauriConfPath $Version
if ($LASTEXITCODE -ne 0) {
    throw "node: failed to update tauri.conf.json"
}

# 10. src-tauri/Cargo.lock：用 cargo update --workspace 重新生成，
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

# 11. 演示web2/src/demoVersion.ts
$demoDir = Join-Path $repoRoot "演示web2\src"
if (-not (Test-Path $demoDir)) {
    New-Item -ItemType Directory -Path $demoDir -Force | Out-Null
}
$demoTs = @"
// 演示站实验版元数据。
// 由 scripts/release/set-version.ps1 自动生成，不要手动编辑。
// 仅用于演示站显示，不连接真实后端。
export const demoVersion = {
  version: "$Version",
  channel: "$Channel",
} as const;
"@
Set-FileContent (Join-Path $demoDir "demoVersion.ts") $demoTs

Write-Host "set-version: $Version (channel=$Channel)" -ForegroundColor Green
Write-Host "  - VERSION"
Write-Host "  - pyproject.toml"
Write-Host "  - frontend/package.json + package-lock.json"
Write-Host "  - src-tauri/Cargo.toml + Cargo.lock + tauri.conf.json"
Write-Host "  - 演示web2/src/demoVersion.ts"
