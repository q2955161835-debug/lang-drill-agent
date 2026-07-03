[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$FrontendDir = Join-Path $Root "frontend"
$TauriConfig = Join-Path $Root "src-tauri\tauri.conf.json"
$TauriBin = Join-Path $FrontendDir "node_modules\.bin\tauri.cmd"

$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
}
if (-not $npm) {
    throw "npm was not found. Install Node.js LTS before running the desktop dev app."
}

if (-not $SkipInstall -or -not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Push-Location $FrontendDir
    try {
        & $npm.Source install
        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed."
        }
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path $TauriBin)) {
    throw "Tauri CLI was not found at $TauriBin. Run npm install in frontend first."
}

& $TauriBin dev --config $TauriConfig
exit $LASTEXITCODE
