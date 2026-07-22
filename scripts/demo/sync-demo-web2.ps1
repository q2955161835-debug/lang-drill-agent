<#
.SYNOPSIS
  把 frontend/src 的 UI 文件单向同步到 演示web2/src/mock。

.DESCRIPTION
  sync-demo-web2.ps1 把 frontend/src/ 下除 api.ts、main.tsx 和测试文件外的
  所有 .ts/.tsx/.css/.d.ts 文件复制到 演示web2/src/mock/，保持 1:1 一致。
  mock/api.ts 是演示站专有的本地 mock，不会被覆盖。
  mock/main.tsx 不存在（演示站用 src/app-main.tsx 作为入口）。
  同步后自动重写 src/app-main.tsx 以包含 I18nProvider，让同步后的 App.tsx
  能正常使用 useI18n()。

  -Verify 模式只比较文件内容，不修改任何文件，发现不一致时返回非零退出码。

.PARAMETER Verify
  只验证 mock 与 frontend/src 的一致性，不复制文件。

.EXAMPLE
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\demo\sync-demo-web2.ps1
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\demo\sync-demo-web2.ps1 -Verify
#>

[CmdletBinding()]
param(
    [switch]$Verify
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path (Join-Path $PSScriptRoot "..") "..")
$frontendSrc = Join-Path $repoRoot "frontend\src"
$mockSrc = Join-Path (Join-Path $repoRoot "演示web2") "src\mock"
$appMainPath = Join-Path (Join-Path $repoRoot "演示web2") "src\app-main.tsx"

if (-not (Test-Path $frontendSrc)) {
    throw "frontend/src not found: $frontendSrc"
}
if (-not (Test-Path $mockSrc)) {
    throw "演示web2/src/mock not found: $mockSrc"
}

# ---------- 排除规则 ----------

function Test-ShouldSkip {
    param([string]$RelativePath)
    # 根 api.ts 由 mock 替换
    if ($RelativePath -eq "api.ts") { return $true }
    # 根 main.tsx 由演示站 app-main.tsx 替换
    if ($RelativePath -eq "main.tsx") { return $true }
    # 测试文件不入 mock
    if ($RelativePath -match '\.test\.(ts|tsx)$') { return $true }
    return $false
}

# ---------- 收集前端源文件 ----------

function Get-FrontendFiles {
    $files = @()
    Get-ChildItem -Path $frontendSrc -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($frontendSrc.Length + 1).Replace("\", "/")
        if (Test-ShouldSkip -RelativePath $rel) { return }
        if ($_.Extension -notin ".ts", ".tsx", ".css", ".d.ts") { return }
        $files += [PSCustomObject]@{
            RelativePath = $rel
            FullName = $_.FullName
        }
    }
    return $files
}

# ---------- 文件读写工具 ----------

function Read-FileNormalized {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $content = [System.Text.Encoding]::UTF8.GetString($bytes)
    # 归一化行尾
    $content = $content -replace "`r`n", "`n"
    $content = $content -replace "`r", "`n"
    return $content
}

function Write-FileUtf8NoBom {
    param([string]$Path, [string]$Content)
    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Copy-FileUtf8 {
    param([string]$Source, [string]$Destination)
    $content = [System.IO.File]::ReadAllText($Source, [System.Text.Encoding]::UTF8)
    Write-FileUtf8NoBom -Path $Destination -Content $content
}

# ---------- app-main.tsx 重写 ----------

function Write-AppMain {
    $content = @"
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./mock/App";
import { I18nProvider } from "./mock/i18n/I18nProvider";
import "./mock/styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </StrictMode>
);
"@
    Write-FileUtf8NoBom -Path $appMainPath -Content $content
}

# ---------- 收集 mock 现有文件 ----------

function Get-MockFiles {
    $files = @()
    Get-ChildItem -Path $mockSrc -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($mockSrc.Length + 1).Replace("\", "/")
        if ($_.Extension -notin ".ts", ".tsx", ".css", ".d.ts") { return }
        $files += [PSCustomObject]@{
            RelativePath = $rel
            FullName = $_.FullName
        }
    }
    return $files
}

# ---------- 主逻辑 ----------

$frontendFiles = Get-FrontendFiles
$mockFiles = Get-MockFiles

if ($Verify) {
    # 验证模式：只比较，不修改
    $missing = @()
    $mismatches = @()

    foreach ($f in $frontendFiles) {
        $mockPath = Join-Path $mockSrc ($f.RelativePath -replace "/", "\")
        $mockContent = Read-FileNormalized -Path $mockPath
        if ($null -eq $mockContent) {
            $missing += $f.RelativePath
            continue
        }
        $frontendContent = Read-FileNormalized -Path $f.FullName
        if ($mockContent -ne $frontendContent) {
            $mismatches += $f.RelativePath
        }
    }

    # 检查 mock 中的遗留文件（前端已删除的）
    $frontendRels = @()
    foreach ($f in $frontendFiles) { $frontendRels += $f.RelativePath }
    $frontendRels += "api.ts"  # mock 专有
    $extra = @()
    foreach ($m in $mockFiles) {
        if ($frontendRels -notcontains $m.RelativePath) {
            $extra += $m.RelativePath
        }
    }

    $hasError = $false
    if ($missing.Count -gt 0) {
        Write-Host "MISSING in mock:" -ForegroundColor Red
        $missing | ForEach-Object { Write-Host "  $_" }
        $hasError = $true
    }
    if ($mismatches.Count -gt 0) {
        Write-Host "MISMATCH (mock != frontend):" -ForegroundColor Red
        $mismatches | ForEach-Object { Write-Host "  $_" }
        $hasError = $true
    }
    if ($extra.Count -gt 0) {
        Write-Host "STALE in mock (not in frontend):" -ForegroundColor Yellow
        $extra | ForEach-Object { Write-Host "  $_" }
        $hasError = $true
    }

    if ($hasError) {
        Write-Host "VERIFY FAILED" -ForegroundColor Red
        exit 1
    } else {
        Write-Host "VERIFY OK: all $($frontendFiles.Count) mock files match frontend/src" -ForegroundColor Green
        exit 0
    }
} else {
    # 同步模式：复制文件并清理遗留
    $copied = 0
    $skipped = 0

    foreach ($f in $frontendFiles) {
        $mockPath = Join-Path $mockSrc ($f.RelativePath -replace "/", "\")
        $frontendContent = Read-FileNormalized -Path $f.FullName
        $mockContent = Read-FileNormalized -Path $mockPath

        if ($null -ne $mockContent -and $mockContent -eq $frontendContent) {
            $skipped++
            continue
        }

        Copy-FileUtf8 -Source $f.FullName -Destination $mockPath
        $copied++
    }

    # 清理 mock 中的遗留文件（前端已删除但 mock 中还在的，保留 api.ts）
    $frontendRels = @()
    foreach ($f in $frontendFiles) { $frontendRels += $f.RelativePath }
    $frontendRels += "api.ts"
    $deleted = 0
    foreach ($m in $mockFiles) {
        if ($frontendRels -notcontains $m.RelativePath) {
            Remove-Item -Path $m.FullName -Force
            $deleted++
        }
    }

    # 重写 app-main.tsx 以包含 I18nProvider
    Write-AppMain

    Write-Host "sync-demo-web2: copied=$copied skipped=$skipped deleted=$deleted" -ForegroundColor Green
    Write-Host "  app-main.tsx rewritten with I18nProvider"
    Write-Host "  mock/api.ts preserved (not overwritten)"
    exit 0
}
