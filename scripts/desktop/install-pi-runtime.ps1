[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$StagingDir,
    [Parameter(Mandatory = $true)][string]$TargetRoot,
    [string]$Version,
    [string]$FailureReportDir
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

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
        throw "file is missing for sha256: $Path"
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

function Write-Failure-Report {
    param(
        [string]$ReportDir,
        [string]$ErrorCode,
        [string]$Message,
        [string]$Detail,
        [string]$StagingDir,
        [string]$TargetRoot
    )
    if (-not $ReportDir) {
        $ReportDir = Join-Path $env:TEMP "langdrill-pi-install-failures"
    }
    New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $report = @{
        ok = $false
        error_code = $ErrorCode
        message = $Message
        detail = $Detail
        staging_dir = $StagingDir
        target_root = $TargetRoot
        timestamp = $stamp
    }
    $path = Join-Path $ReportDir "pi-install-failure-$stamp.json"
    $report | ConvertTo-Json -Depth 5 | Out-File -LiteralPath $path -Encoding utf8 -NoNewline
    return $path
}

$StagingDir = (Resolve-Path $StagingDir).Path
$TargetRoot = (New-Item -ItemType Directory -Force -Path $TargetRoot).FullName

$stagingManifestPath = Join-Path $StagingDir "pi-runtime-staging.json"
if (-not (Test-Path -LiteralPath $stagingManifestPath -PathType Leaf)) {
    $report = Write-Failure-Report -ReportDir $FailureReportDir -ErrorCode "STAGING_MANIFEST_MISSING" `
        -Message "Staging manifest is missing." -Detail $stagingManifestPath -StagingDir $StagingDir -TargetRoot $TargetRoot
    Write-Progress-Line -Stage "error" -Message "Staging manifest is missing." -Detail $report
    throw "staging manifest missing: $stagingManifestPath"
}

$staging = Get-Content -LiteralPath $stagingManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $Version) {
    $Version = $staging.runtime_version
}
if (-not $Version) {
    $report = Write-Failure-Report -ReportDir $FailureReportDir -ErrorCode "VERSION_MISSING" `
        -Message "Runtime version could not be resolved." -Detail "" -StagingDir $StagingDir -TargetRoot $TargetRoot
    throw "runtime version could not be resolved"
}

Write-Progress-Line -Stage "verify" -Message "Verifying staging payload hashes..." -Percent 10 -Detail $StagingDir

$bridgeStaging = Join-Path $StagingDir "pi-bridge"
if (-not (Test-Path -LiteralPath $bridgeStaging -PathType Leaf)) {
    $report = Write-Failure-Report -ReportDir $FailureReportDir -ErrorCode "BRIDGE_MISSING" `
        -Message "Bridge staging directory is missing." -Detail $bridgeStaging -StagingDir $StagingDir -TargetRoot $TargetRoot
    throw "bridge staging missing: $bridgeStaging"
}
$bridgeEntrypoint = Join-Path $bridgeStaging "dist\src\index.js"
if (-not (Test-Path -LiteralPath $bridgeEntrypoint -PathType Leaf)) {
    $report = Write-Failure-Report -ReportDir $FailureReportDir -ErrorCode "BRIDGE_BUILD_MISSING" `
        -Message "Bridge build output is missing." -Detail $bridgeEntrypoint -StagingDir $StagingDir -TargetRoot $TargetRoot
    throw "bridge build output missing: $bridgeEntrypoint"
}

$skillsStaging = Join-Path $StagingDir "bundled-skills"
$bundleManifestPath = Join-Path $skillsStaging "manifest.json"
if (-not (Test-Path -LiteralPath $bundleManifestPath -PathType Leaf)) {
    $report = Write-Failure-Report -ReportDir $FailureReportDir -ErrorCode "BUNDLED_SKILLS_MISSING" `
        -Message "Bundled skills manifest is missing." -Detail $bundleManifestPath -StagingDir $StagingDir -TargetRoot $TargetRoot
    throw "bundled skills manifest missing: $bundleManifestPath"
}
$bundleManifest = Get-Content -LiteralPath $bundleManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($bundle in $bundleManifest.bundles) {
    $skillManifestPath = Join-Path $skillsStaging ($bundle.path.TrimEnd('/') + "/manifest.json")
    if (-not (Test-Path -LiteralPath $skillManifestPath -PathType Leaf)) {
        $report = Write-Failure-Report -ReportDir $FailureReportDir -ErrorCode "SKILL_MANIFEST_MISSING" `
            -Message "Skill manifest is missing." -Detail $skillManifestPath -StagingDir $StagingDir -TargetRoot $TargetRoot
        throw "skill manifest missing: $skillManifestPath"
    }
    $skillManifest = Get-Content -LiteralPath $skillManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $skillRoot = (Resolve-Path (Split-Path -Parent $skillManifestPath)).Path
    foreach ($entry in $skillManifest.files) {
        $target = Join-Path $skillRoot $entry.path
        $actual = Get-File-Sha256 -Path $target
        if ($actual -ne $entry.sha256) {
            $report = Write-Failure-Report -ReportDir $FailureReportDir -ErrorCode "SKILL_HASH_MISMATCH" `
                -Message "Skill file hash mismatch." -Detail "$($entry.path) expected=$($entry.sha256) actual=$actual" `
                -StagingDir $StagingDir -TargetRoot $TargetRoot
            throw "skill hash mismatch for $($entry.path)"
        }
    }
}
Write-Progress-Line -Stage "verify" -Message "Staging payload verified." -Percent 40

$versionedTarget = Join-Path $TargetRoot $Version
$tempTarget = Join-Path $TargetRoot ".$Version.installing-$(Get-Date -Format 'yyyyMMddHHmmss')"

if (Test-Path -LiteralPath $versionedTarget -PathType Container) {
    Write-Progress-Line -Stage "install" -Message "Version already installed; re-verifying." -Percent 60 -Detail $versionedTarget
} else {
    Write-Progress-Line -Stage "install" -Message "Extracting payload to temp directory..." -Percent 50 -Detail $tempTarget
    try {
        New-Item -ItemType Directory -Force -Path $tempTarget | Out-Null
        Copy-Item -LiteralPath $bridgeStaging -Destination (Join-Path $tempTarget "pi-bridge") -Recurse -Force
        Copy-Item -LiteralPath $skillsStaging -Destination (Join-Path $tempTarget "bundled-skills") -Recurse -Force

        $nodeArchive = Get-ChildItem -LiteralPath $StagingDir -Filter "node-*.zip" -File | Select-Object -First 1
        if ($nodeArchive) {
            $nodeExtract = Join-Path $tempTarget "node"
            New-Item -ItemType Directory -Force -Path $nodeExtract | Out-Null
            Expand-Archive -LiteralPath $nodeArchive.FullName -DestinationPath $nodeExtract -Force
        }

        $installedManifest = @{
            runtime_version = $Version
            installed_at = (Get-Date).ToUniversalTime().ToString("o")
            node_version = $staging.node_version
            pi_version = $staging.pi_version
            bridge_entrypoint = "pi-bridge/dist/src/index.js"
            bundled_skills = @($staging.bundled_skills | ForEach-Object { $_.id })
        }
        $installedManifest | ConvertTo-Json -Depth 5 | Out-File -LiteralPath (Join-Path $tempTarget "pi-runtime-installed.json") -Encoding utf8 -NoNewline

        Write-Progress-Line -Stage "install" -Message "Renaming temp directory to final version..." -Percent 80 -Detail $versionedTarget
        [System.IO.Directory]::Move($tempTarget, $versionedTarget)
    } catch {
        if (Test-Path -LiteralPath $tempTarget) {
            Remove-Item -LiteralPath $tempTarget -Recurse -Force -ErrorAction SilentlyContinue
        }
        $report = Write-Failure-Report -ReportDir $FailureReportDir -ErrorCode "INSTALL_FAILED" `
            -Message "Atomic install failed." -Detail $_.Exception.Message -StagingDir $StagingDir -TargetRoot $TargetRoot
        throw
    }
}

$currentMarker = Join-Path $TargetRoot "current"
if (Test-Path -LiteralPath $currentMarker) {
    Remove-Item -LiteralPath $currentMarker -Force
}
New-Item -ItemType Junction -Path $currentMarker -Target $versionedTarget | Out-Null

$statusDir = Join-Path $env:APPDATA "Lang Drill Agent\pi-runtime"
New-Item -ItemType Directory -Force -Path $statusDir | Out-Null
$status = @{
    state = "ready"
    version = $Version
    installed_at = (Get-Date).ToUniversalTime().ToString("o")
    target = $versionedTarget
    current = $currentMarker
}
$statusPath = Join-Path $statusDir "status.json"
$status | ConvertTo-Json -Depth 5 | Out-File -LiteralPath $statusPath -Encoding utf8 -NoNewline

Write-Progress-Line -Stage "done" -Message "Pi runtime installed." -Percent 100 -Detail $versionedTarget
$result = @{
    ok = $true
    version = $Version
    target = $versionedTarget
    current = $currentMarker
    status_path = $statusPath
} | ConvertTo-Json -Compress
Write-Host $result
