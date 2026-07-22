<#
.SYNOPSIS
  验证实验版发布产物是否齐全且自洽。

.DESCRIPTION
  verify-release-assets.ps1 在 desktop-build 之后、release 发布之前运行，
  检查所有更新器与发布资源是否就位：

  - NSIS 安装包 (*-setup.exe)
  - 更新器签名文件 (.sig)
  - latest.json 更新清单
  - checksums.sha256 校验和
  - pi-runtime-manifest.json
  - release-notes/v<VERSION>.md

  使用 -DryRun 仅检查不写入任何文件；不读取任何密钥。

.PARAMETER DryRun
  仅检查产物存在性，不重新生成 latest.json / checksums.sha256。

.PARAMETER BundleDir
  NSIS bundle 目录，默认 src-tauri\target\release\bundle\nsis。
  若未提供，会自动检测。

.PARAMETER StageDir
  Staged 产物目录。若提供，则检查 staging 目录；否则检查 BundleDir。

.EXAMPLE
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\release\verify-release-assets.ps1 -DryRun
#>

[CmdletBinding()]
param(
    [switch]$DryRun,
    [string]$BundleDir = "",
    [string]$StageDir = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$repoRoot = (Resolve-Path (Join-Path (Join-Path $PSScriptRoot "..") "..")).Path

# 解析版本号
$versionFile = Join-Path $repoRoot "VERSION"
if (-not (Test-Path -LiteralPath $versionFile)) {
    throw "VERSION file missing at $versionFile"
}
$version = (Get-Content -LiteralPath $versionFile -Raw -Encoding UTF8).Trim()
$tag = "v$version"
Write-Host "verify-release-assets: version=$version tag=$tag dryRun=$DryRun"

# 确定检查目录
if ($StageDir -ne "" -and (Test-Path -LiteralPath $StageDir)) {
    $checkDir = $StageDir
    Write-Host "Using stage dir: $checkDir"
} elseif ($BundleDir -ne "" -and (Test-Path -LiteralPath $BundleDir)) {
    $checkDir = $BundleDir
    Write-Host "Using bundle dir: $checkDir"
} else {
    $defaultBundle = Join-Path $repoRoot "src-tauri\target\release\bundle\nsis"
    if (Test-Path -LiteralPath $defaultBundle) {
        $checkDir = $defaultBundle
        Write-Host "Using default bundle dir: $checkDir"
    } else {
        # DryRun 且构建未发生时，允许只验证 release-notes 与 pi-runtime-manifest
        $checkDir = ""
        Write-Host "No bundle dir found; verifying release-notes and runtime manifest only." -ForegroundColor Yellow
    }
}

$failed = $false

function Test-RequiredFile {
    param(
        [string]$Description,
        [string]$Path,
        [switch]$IsRequired
    )
    if (Test-Path -LiteralPath $Path) {
        $size = (Get-Item -LiteralPath $Path).Length
        Write-Host ("  OK   {0,-30} {1} bytes" -f $Description, $size) -ForegroundColor Green
        return $true
    } elseif ($IsRequired) {
        Write-Host ("  FAIL {0,-30} missing: {1}" -f $Description, $Path) -ForegroundColor Red
        $script:failed = $true
        return $false
    } else {
        Write-Host ("  WARN {0,-30} not found: {1}" -f $Description, $Path) -ForegroundColor Yellow
        return $false
    }
}

# 1. NSIS 安装包
$installerFound = $false
$installerPath = ""
if ($checkDir -ne "") {
    $installer = Get-ChildItem -Path $checkDir -Filter "*-setup.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($installer) {
        $installerPath = $installer.FullName
        Write-Host ("  OK   {0,-30} {1} bytes" -f "NSIS installer", $installer.Length) -ForegroundColor Green
        $installerFound = $true
    } else {
        if ($DryRun) {
            Write-Host ("  WARN {0,-30} DryRun: not built yet" -f "NSIS installer") -ForegroundColor Yellow
        } else {
            Write-Host ("  FAIL {0,-30} not found in {1}" -f "NSIS installer", $checkDir) -ForegroundColor Red
            $failed = $true
        }
    }
} else {
    Write-Host "  SKIP NSIS installer (no bundle dir)" -ForegroundColor Yellow
}

# 2. 更新器签名 .sig
if ($installerPath -ne "") {
    $sigPath = "$installerPath.sig"
    $sigFound = Test-RequiredFile -Description "Updater signature (.sig)" -Path $sigPath -IsRequired:(-not $DryRun)
} else {
    # 退而搜索 .sig 文件
    if ($checkDir -ne "") {
        $sigFile = Get-ChildItem -Path $checkDir -Filter "*.sig" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($sigFile) {
            Write-Host ("  OK   {0,-30} {1}" -f "Updater signature (.sig)", $sigFile.Name) -ForegroundColor Green
        } else {
            if ($DryRun) {
                Write-Host ("  WARN {0,-30} DryRun: not built yet" -f "Updater signature (.sig)") -ForegroundColor Yellow
            } else {
                Write-Host ("  FAIL {0,-30} not found" -f "Updater signature (.sig)") -ForegroundColor Red
                $failed = $true
            }
        }
    } else {
        Write-Host "  SKIP Updater signature (.sig) (no bundle dir)" -ForegroundColor Yellow
    }
}

# 3. latest.json 更新器清单
$latestJsonPath = ""
if ($checkDir -ne "") {
    $latestJsonPath = Join-Path $checkDir "latest.json"
}
$latestJsonFound = $false
if ($latestJsonPath -ne "" -and (Test-Path -LiteralPath $latestJsonPath)) {
    Write-Host ("  OK   {0,-30} {1}" -f "latest.json", $latestJsonPath) -ForegroundColor Green
    $latestJsonFound = $true
} elseif (-not $DryRun -and $installerPath -ne "") {
    # 非 DryRun 时尝试生成
    $sigFile = "$installerPath.sig"
    if (Test-Path -LiteralPath $sigFile) {
        $signature = (Get-Content -LiteralPath $sigFile -Raw -Encoding UTF8).Trim()
        $pubDate = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssZ")
        $installerName = [System.IO.Path]::GetFileName($installerPath)
        $manifest = @{
            version = $version
            notes = "Lang Drill Agent $version experimental prerelease. See release notes."
            pub_date = $pubDate
            platforms = @{
                "windows-x86_64" = @{
                    signature = $signature
                    url = "https://github.com/q2955161835-debug/lang-drill-agent/releases/download/$tag/$installerName"
                }
            }
        }
        $manifest | ConvertTo-Json -Depth 6 | Out-File -FilePath $latestJsonPath -Encoding utf8
        Write-Host ("  GEN  {0,-30} {1}" -f "latest.json", $latestJsonPath) -ForegroundColor Cyan
        $latestJsonFound = $true
    } else {
        Write-Host ("  FAIL {0,-30} cannot generate without .sig" -f "latest.json") -ForegroundColor Red
        $failed = $true
    }
} elseif ($DryRun) {
    Write-Host ("  WARN {0,-30} DryRun: not generating" -f "latest.json") -ForegroundColor Yellow
} else {
    Write-Host ("  FAIL {0,-30} no bundle dir" -f "latest.json") -ForegroundColor Red
    $failed = $true
}

# 验证 latest.json 内容（如果存在）
if ($latestJsonFound -and (Test-Path -LiteralPath $latestJsonPath)) {
    try {
        $manifest = Get-Content -LiteralPath $latestJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($manifest.version -ne $version) {
            Write-Host ("  FAIL latest.json version mismatch: expected=$version actual=$($manifest.version)") -ForegroundColor Red
            $failed = $true
        } else {
            Write-Host ("  OK   latest.json version matches $version") -ForegroundColor Green
        }
        if (-not $manifest.platforms.'windows-x86_64'.signature) {
            Write-Host "  FAIL latest.json missing windows-x86_64.signature" -ForegroundColor Red
            $failed = $true
        }
        if (-not $manifest.platforms.'windows-x86_64'.url) {
            Write-Host "  FAIL latest.json missing windows-x86_64.url" -ForegroundColor Red
            $failed = $true
        }
    } catch {
        Write-Host ("  FAIL latest.json invalid JSON: $_") -ForegroundColor Red
        $failed = $true
    }
}

# 4. 校验和 checksums.sha256
$checksumsPath = ""
if ($checkDir -ne "") {
    $checksumsPath = Join-Path $checkDir "checksums.sha256"
}
if ($checksumsPath -ne "" -and (Test-Path -LiteralPath $checksumsPath)) {
    Write-Host ("  OK   {0,-30} {1}" -f "checksums.sha256", $checksumsPath) -ForegroundColor Green
} elseif (-not $DryRun -and $checkDir -ne "") {
    # 非 DryRun 时尝试生成
    $checksumLines = @()
    foreach ($f in (Get-ChildItem -Path $checkDir -File)) {
        $hash = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLower()
        $checksumLines += "$hash  $($f.Name)"
    }
    $checksumLines | Out-File -FilePath $checksumsPath -Encoding ascii
    Write-Host ("  GEN  {0,-30} {1}" -f "checksums.sha256", $checksumsPath) -ForegroundColor Cyan
} else {
    Write-Host ("  WARN {0,-30} not present (DryRun or no bundle dir)" -f "checksums.sha256") -ForegroundColor Yellow
}

# 5. Pi 运行时清单
$piManifestPath = Join-Path $repoRoot "runtime\pi-runtime-manifest.json"
Test-RequiredFile -Description "pi-runtime-manifest.json" -Path $piManifestPath -IsRequired | Out-Null

# 6. 发布说明
$releaseNotesPath = Join-Path $repoRoot "release-notes\$tag.md"
Test-RequiredFile -Description "release-notes/$tag.md" -Path $releaseNotesPath -IsRequired | Out-Null

# 7. 版本一致性（依赖 verify-version.ps1）
$verifyVersionScript = Join-Path $repoRoot "scripts\release\verify-version.ps1"
if (Test-Path -LiteralPath $verifyVersionScript) {
    Write-Host "Running verify-version.ps1..."
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyVersionScript
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  FAIL verify-version.ps1 returned $LASTEXITCODE" -ForegroundColor Red
        $failed = $true
    }
} else {
    Write-Host "  SKIP verify-version.ps1 not found" -ForegroundColor Yellow
}

# 总结
Write-Host ""
if ($failed) {
    Write-Host "verify-release-assets: FAILED" -ForegroundColor Red
    exit 1
} else {
    Write-Host "verify-release-assets: PASS (dryRun=$DryRun)" -ForegroundColor Green
    exit 0
}
