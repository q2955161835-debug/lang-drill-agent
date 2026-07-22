<#
.SYNOPSIS
  基于模板生成实验版发布说明 Markdown。

.DESCRIPTION
  generate-release-notes.ps1 把 release-notes/_template.md 中的占位符
  {{VERSION}} 替换为传入的 Version，输出到 release-notes/v<Version>.md。

  模板本身需要人工维护内容；脚本只做确定性替换，不调用模型。

.PARAMETER Version
  目标版本号，例如 1.0.0-experimental.1。

.EXAMPLE
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\release\generate-release-notes.ps1 -Version 1.0.0-experimental.1
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path (Join-Path $PSScriptRoot "..") "..")
$templatePath = Join-Path $repoRoot "release-notes\_template.md"
$outPath = Join-Path $repoRoot "release-notes\v$Version.md"

if (-not (Test-Path $templatePath)) {
    throw "Template not found: $templatePath"
}

$template = Get-Content $templatePath -Raw -Encoding UTF8
$content = $template -replace '\{\{VERSION\}\}', $Version

[System.IO.File]::WriteAllText($outPath, $content, (New-Object System.Text.UTF8Encoding $false))

Write-Host "generate-release-notes: wrote $outPath" -ForegroundColor Green
