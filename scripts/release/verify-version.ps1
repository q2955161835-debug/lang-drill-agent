<#
.SYNOPSIS
  校验所有发布清单版本号一致，且与 VERSION 文件匹配。

.DESCRIPTION
  verify-version.ps1 读取 VERSION 文件，比对：
  - pyproject.toml
  - frontend/package.json
  - src-tauri/Cargo.toml
  - src-tauri/Cargo.lock
  - src-tauri/tauri.conf.json
  - 演示web2/src/demoVersion.ts

  任何不一致立即抛错退出，便于 CI 阻断不一致的发布。

.EXAMPLE
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\release\verify-version.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path (Join-Path $PSScriptRoot "..") "..")

$versionFile = Join-Path $repoRoot "VERSION"
if (-not (Test-Path $versionFile)) {
    throw "VERSION file missing"
}
$expected = (Get-Content $versionFile -Raw -Encoding UTF8).Trim()

$semverRe = '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9a-zA-Z.-]+))?(?:\+([0-9a-zA-Z.-]+))?$'
if ($expected -cnotmatch $semverRe) {
    throw "VERSION is not valid SemVer: $expected"
}

function Get-PyprojectVersion {
    param([string]$Path)
    $content = Get-Content $Path -Raw -Encoding UTF8
    if ($content -match '(?m)^version\s*=\s*"([^"]+)"') {
        return $Matches[1]
    }
    return $null
}

function Get-CargoTomlVersion {
    param([string]$Path)
    $content = Get-Content $Path -Raw -Encoding UTF8
    if ($content -match '(?ms)\[package\][^\[]*?version\s*=\s*"([^"]+)"') {
        return $Matches[1]
    }
    return $null
}

function Get-CargoLockVersion {
    param([string]$Path, [string]$PackageName)
    $content = Get-Content $Path -Raw -Encoding UTF8
    $pattern = 'name = "' + [regex]::Escape($PackageName) + '"[^\n]*\nversion = "([^"]+)"'
    if ($content -match $pattern) {
        return $Matches[1]
    }
    return $null
}

function Get-JsonVersion {
    param([string]$Path)
    $data = Get-Content $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    return $data.version
}

function Get-DemoVersion {
    param([string]$Path)
    $content = Get-Content $Path -Raw -Encoding UTF8
    if ($content -match 'version\s*:\s*"([^"]+)"') {
        return $Matches[1]
    }
    return $null
}

$checks = @(
    @{ Name = "pyproject.toml";       Path = (Join-Path $repoRoot "pyproject.toml");                          Value = (Get-PyprojectVersion (Join-Path $repoRoot "pyproject.toml")) },
    @{ Name = "frontend/package.json"; Path = (Join-Path $repoRoot "frontend\package.json");                   Value = (Get-JsonVersion (Join-Path $repoRoot "frontend\package.json")) },
    @{ Name = "Cargo.toml";            Path = (Join-Path $repoRoot "src-tauri\Cargo.toml");                    Value = (Get-CargoTomlVersion (Join-Path $repoRoot "src-tauri\Cargo.toml")) },
    @{ Name = "Cargo.lock";            Path = (Join-Path $repoRoot "src-tauri\Cargo.lock");                    Value = (Get-CargoLockVersion (Join-Path $repoRoot "src-tauri\Cargo.lock") "lang-drill-agent-desktop") },
    @{ Name = "tauri.conf.json";       Path = (Join-Path $repoRoot "src-tauri\tauri.conf.json");               Value = (Get-JsonVersion (Join-Path $repoRoot "src-tauri\tauri.conf.json")) },
    @{ Name = "demoVersion.ts";        Path = (Join-Path $repoRoot "演示web2\src\demoVersion.ts");             Value = (Get-DemoVersion (Join-Path $repoRoot "演示web2\src\demoVersion.ts")) }
)

$failed = $false
foreach ($check in $checks) {
    if ($check.Value -ne $expected) {
        Write-Host ("MISMATCH  {0,-25} expected={1} actual={2}" -f $check.Name, $expected, $check.Value) -ForegroundColor Red
        $failed = $true
    } else {
        Write-Host ("OK        {0,-25} {1}" -f $check.Name, $expected) -ForegroundColor Green
    }
}

if ($failed) {
    throw "Version consistency check failed"
}

Write-Host "verify-version: all manifests at $expected" -ForegroundColor Green
