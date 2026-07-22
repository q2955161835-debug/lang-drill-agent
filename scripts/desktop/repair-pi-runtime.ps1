[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$TargetRoot,
    [string]$BundledPayload,
    [string]$ManifestPath,
    [string]$ReleaseAssetUrl,
    [string]$ReleaseAssetSha256
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $ManifestPath) {
    $ManifestPath = Join-Path $Root "runtime\pi-runtime-manifest.json"
}

function Write-Progress-Line {
    param([string]$Stage, [string]$Message, [int]$Percent = -1, [string]$Detail = "")
    $payload = @{
        stage = $Stage
        message = $Message
        percent = $Percent
        detail = $Detail
    } | ConvertTo-Json -Compress -Depth 4
    Write-Host "[langdrill-progress] $payload"
}

function Get-File-Sha256 {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        $digest = $hasher.ComputeHash($bytes)
        return "sha256:" + ([System.BitConverter]::ToString($digest).Replace("-", "").ToLower())
    }
    finally {
        $hasher.Dispose()
    }
}

function Get-Pi-Status-Path {
    return Join-Path $env:APPDATA "Lang Drill Agent\pi-runtime\status.json"
}

function Read-Current-Status {
    $path = Get-Pi-Status-Path
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Write-Status {
    param([string]$State, [string]$Version = "", [string]$Detail = "", [string]$Target = "")
    $statusDir = Join-Path $env:APPDATA "Lang Drill Agent\pi-runtime"
    New-Item -ItemType Directory -Force -Path $statusDir | Out-Null
    $status = @{
        state = $State
        version = $Version
        updated_at = (Get-Date).ToUniversalTime().ToString("o")
        detail = $Detail
        target = $Target
    }
    $status | ConvertTo-Json -Depth 5 | Out-File -LiteralPath (Get-Pi-Status-Path) -Encoding utf8 -NoNewline
}

Write-Progress-Line -Stage "inspect" -Message "Inspecting current Pi runtime state..." -Percent 5
$current = Read-Current-Status
if ($current) {
    Write-Progress-Line -Stage "inspect" -Message "Current state: $($current.state) v$($current.version)" -Percent 10 -Detail ($current.target || "")
} else {
    Write-Progress-Line -Stage "inspect" -Message "No prior status found." -Percent 10
}

if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    Write-Status -State "install_failed" -Detail "manifest missing: $ManifestPath"
    throw "manifest missing: $ManifestPath"
}
$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

$bundledStaging = $null
if ($BundledPayload -and (Test-Path -LiteralPath $BundledPayload -PathType Container)) {
    Write-Progress-Line -Stage "payload" -Message "Using bundled payload for repair." -Percent 25 -Detail $BundledPayload
    $bundledStaging = $BundledPayload
} else {
    Write-Progress-Line -Stage "payload" -Message "Bundled payload not available; checking current target..." -Percent 25
    $currentTarget = $null
    if ($current -and $current.target) {
        $currentTarget = $current.target
    } elseif (Test-Path -LiteralPath (Join-Path $TargetRoot "current")) {
        $currentTarget = (Resolve-Path (Join-Path $TargetRoot "current")).Path
    }
    if ($currentTarget -and (Test-Path -LiteralPath $currentTarget -PathType Container)) {
        Write-Progress-Line -Stage "payload" -Message "Reusing existing versioned payload." -Percent 35 -Detail $currentTarget
        $bundledStaging = $currentTarget
    }
}

if (-not $bundledStaging) {
    if (-not $ReleaseAssetUrl) {
        Write-Status -State "repair_required" -Detail "No bundled payload or release asset URL provided."
        Write-Progress-Line -Stage "error" -Message "Repair requires a bundled payload or signed release asset URL." -Percent 100
        throw "no repair payload source available"
    }
    Write-Progress-Line -Stage "download" -Message "Downloading signed release asset..." -Percent 40 -Detail $ReleaseAssetUrl
    $downloadDir = Join-Path $env:TEMP "langdrill-pi-repair"
    New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
    $archiveName = Split-Path -Leaf $ReleaseAssetUrl
    $archivePath = Join-Path $downloadDir $archiveName
    Invoke-WebRequest -Uri $ReleaseAssetUrl -OutFile $archivePath -UseBasicParsing
    if ($ReleaseAssetSha256) {
        $actual = Get-File-Sha256 -Path $archivePath
        if ($actual -ne $ReleaseAssetSha256) {
            Write-Status -State "install_failed" -Detail "release asset hash mismatch: expected=$ReleaseAssetSha256 actual=$actual"
            throw "release asset hash mismatch"
        }
    }
    Write-Progress-Line -Stage "download" -Message "Extracting release asset..." -Percent 60
    $extractDir = Join-Path $downloadDir "extracted"
    if (Test-Path -LiteralPath $extractDir) {
        Remove-Item -LiteralPath $extractDir -Recurse -Force
    }
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractDir -Force
    $bundledStaging = $extractDir
}

Write-Progress-Line -Stage "install" -Message "Re-installing Pi runtime atomically..." -Percent 70 -Detail $bundledStaging
$installScript = Join-Path $PSScriptRoot "install-pi-runtime.ps1"
$installArgs = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $installScript,
    "-StagingDir", $bundledStaging,
    "-TargetRoot", $TargetRoot
)
$installLogDir = Join-Path $env:APPDATA "Lang Drill Agent\logs"
New-Item -ItemType Directory -Force -Path $installLogDir | Out-Null
$installLog = Join-Path $installLogDir "pi-runtime-repair.log"
$installErrLog = Join-Path $installLogDir "pi-runtime-repair.err.log"

& powershell.exe @installArgs *>&1 | Tee-Object -FilePath $installLog
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Status -State "repair_failed" -Detail "install script exited with $exitCode; see $installErrLog"
    Write-Progress-Line -Stage "error" -Message "Repair install failed." -Percent 100 -Detail $installErrLog
    throw "repair install failed with exit code $exitCode"
}

Write-Progress-Line -Stage "done" -Message "Pi runtime repair completed." -Percent 100 -Detail $TargetRoot
$result = @{
    ok = $true
    target_root = $TargetRoot
    staging_source = $bundledStaging
    log_path = $installLog
} | ConvertTo-Json -Compress
Write-Host $result
