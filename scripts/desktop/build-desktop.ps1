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
    throw "npm was not found. Install Node.js LTS before building the desktop app."
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

& $TauriBin build --config $TauriConfig
if ($LASTEXITCODE -ne 0) {
    throw "Tauri desktop build failed."
}

$NsisDir = Join-Path $Root "src-tauri\target\release\nsis\x64"
$NsisScript = Join-Path $NsisDir "installer.nsi"
if (Test-Path -LiteralPath $NsisScript) {
    $nsi = Get-Content -LiteralPath $NsisScript -Raw
    if ($nsi -notmatch "(?m)^Function PageReinstall\r?\n  Call LangDrillCleanStaleInstallRegistry") {
        $patched = $nsi -replace "(?m)^Function PageReinstall\r?$", "Function PageReinstall`r`n  Call LangDrillCleanStaleInstallRegistry"
        $utf8Bom = [System.Text.UTF8Encoding]::new($true)
        [System.IO.File]::WriteAllText($NsisScript, $patched, $utf8Bom)
    }

    $makensis = Join-Path $env:LOCALAPPDATA "tauri\NSIS\Bin\makensis.exe"
    if (-not (Test-Path -LiteralPath $makensis)) {
        $makensis = Join-Path $env:LOCALAPPDATA "tauri\NSIS\makensis.exe"
    }
    if (-not (Test-Path -LiteralPath $makensis)) {
        throw "makensis.exe was not found under $env:LOCALAPPDATA\tauri\NSIS."
    }

    Push-Location $NsisDir
    try {
        & $makensis $NsisScript
        if ($LASTEXITCODE -ne 0) {
            throw "NSIS installer rebuild failed after stale install patch."
        }
    }
    finally {
        Pop-Location
    }

    $tauri = Get-Content -LiteralPath $TauriConfig -Raw | ConvertFrom-Json
    $patchedInstaller = Join-Path $NsisDir "nsis-output.exe"
    $bundleInstaller = Join-Path $Root ("src-tauri\target\release\bundle\nsis\{0}_{1}_x64-setup.exe" -f $tauri.productName, $tauri.version)
    if (-not (Test-Path -LiteralPath $patchedInstaller)) {
        throw "Patched NSIS installer output was not found: $patchedInstaller"
    }
    Copy-Item -LiteralPath $patchedInstaller -Destination $bundleInstaller -Force
}
