[CmdletBinding()]
param(
    [switch]$VerifyOnly,
    [string]$StagingDir,
    [string]$ManifestPath
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

function Test-Sha256Format {
    param([string]$Value)
    return $Value -match '^sha256:[0-9a-f]{64}$'
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

if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    Write-Progress-Line -Stage "error" -Message "Pi runtime manifest is missing." -Detail $ManifestPath
    throw "Pi runtime manifest is missing at $ManifestPath"
}

Write-Progress-Line -Stage "manifest" -Message "Loading Pi runtime manifest..." -Percent 5
$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

if ($manifest.manifest_version -ne 1) {
    throw "unsupported manifest_version: $($manifest.manifest_version)"
}
if (-not $manifest.runtime_version) {
    throw "runtime_version is missing"
}
if (-not $manifest.node.version) {
    throw "node.version is missing"
}
if (-not $manifest.pi.version) {
    throw "pi.version is missing"
}

Write-Progress-Line -Stage "manifest" -Message "Manifest schema validated." -Percent 10 -Detail "runtime $($manifest.runtime_version), node $($manifest.node.version), pi $($manifest.pi.version)"

$bridgeEntrypoint = Join-Path $Root $manifest.bridge.entrypoint
$bridgePackage = Join-Path $Root $manifest.bridge.package
if (-not (Test-Path -LiteralPath $bridgeEntrypoint -PathType Leaf)) {
    throw "bridge entrypoint is missing: $bridgeEntrypoint"
}
if (-not (Test-Path -LiteralPath $bridgePackage -PathType Leaf)) {
    throw "bridge package.json is missing: $bridgePackage"
}
Write-Progress-Line -Stage "bridge" -Message "Bridge entrypoint verified." -Percent 20 -Detail $manifest.bridge.entrypoint

$piPackageJson = Get-Content -LiteralPath $bridgePackage -Raw -Encoding UTF8 | ConvertFrom-Json
$declaredPi = $piPackageJson.dependencies.'@earendil-works/pi-coding-agent'
if ($declaredPi -ne $manifest.pi.version) {
    throw "pi version mismatch: manifest=$($manifest.pi.version) package.json=$declaredPi"
}

Write-Progress-Line -Stage "skills" -Message "Verifying bundled skill hashes..." -Percent 35
foreach ($skill in $manifest.bundled_skills) {
    $skillManifestPath = Join-Path $Root $skill.manifest_path
    if (-not (Test-Path -LiteralPath $skillManifestPath -PathType Leaf)) {
        throw "bundled skill manifest is missing: $skillManifestPath"
    }
    $skillManifest = Get-Content -LiteralPath $skillManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($skillManifest.license -ne $skill.license) {
        throw "bundled skill license mismatch for $($skill.id)"
    }
    if ($skillManifest.origin_commit -ne $skill.origin_commit) {
        throw "bundled skill origin_commit mismatch for $($skill.id)"
    }
    $skillRoot = (Resolve-Path (Split-Path -Parent $skillManifestPath)).Path
    foreach ($entry in $skillManifest.files) {
        if (-not (Test-Sha256Format -Value $entry.sha256)) {
            throw "bundled skill file sha256 is malformed: $($entry.path)"
        }
        $target = Join-Path $skillRoot $entry.path
        $actual = Get-File-Sha256 -Path $target
        if ($actual -ne $entry.sha256) {
            throw "bundled skill file hash mismatch for $($entry.path): expected=$($entry.sha256) actual=$actual"
        }
    }
    Write-Progress-Line -Stage "skills" -Message "Verified skill: $($skill.id)" -Percent 45
}

if ($VerifyOnly) {
    Write-Progress-Line -Stage "done" -Message "Pi runtime manifest verified." -Percent 100 -Detail "VerifyOnly mode; no staging payload was downloaded."
    $result = @{
        ok = $true
        mode = "verify_only"
        runtime_version = $manifest.runtime_version
        node_version = $manifest.node.version
        pi_version = $manifest.pi.version
        bundled_skills = @($manifest.bundled_skills | ForEach-Object { $_.id })
    } | ConvertTo-Json -Compress
    Write-Host $result
    exit 0
}

if (-not $StagingDir) {
    $StagingDir = Join-Path $env:TEMP "langdrill-pi-runtime-staging"
}
$StagingDir = (New-Item -ItemType Directory -Force -Path $StagingDir).FullName
Write-Progress-Line -Stage "staging" -Message "Preparing staging directory..." -Percent 50 -Detail $StagingDir

$nodeDownload = $manifest.node.downloads.'x86_64-windows'
if (-not $nodeDownload) {
    throw "node download entry for x86_64-windows is missing"
}
$nodeArchiveName = Split-Path -Leaf $nodeDownload.url
$nodeArchivePath = Join-Path $StagingDir $nodeArchiveName
$archiveSha256 = $nodeDownload.sha256

if (-not $nodeDownload.sha256_verified) {
    Write-Progress-Line -Stage "node" -Message "Node archive sha256 is pending verification." -Percent 55 -Detail "manifest marks sha256_verified=false; prepare step will recompute after download."
} elseif (Test-Path -LiteralPath $nodeArchivePath -PathType Leaf) {
    $actualArchiveSha = Get-File-Sha256 -Path $nodeArchivePath
    if ($actualArchiveSha -ne $archiveSha256) {
        throw "node archive hash mismatch: expected=$archiveSha256 actual=$actualArchiveSha"
    }
    Write-Progress-Line -Stage "node" -Message "Node archive hash verified." -Percent 60
}

$bridgeStaging = Join-Path $StagingDir "pi-bridge"
if (Test-Path -LiteralPath $bridgeStaging) {
    Remove-Item -LiteralPath $bridgeStaging -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $bridgeStaging | Out-Null
Copy-Item -LiteralPath (Join-Path $Root "runtime\pi-bridge\package.json") -Destination $bridgeStaging -Force
Copy-Item -LiteralPath (Join-Path $Root "runtime\pi-bridge\package-lock.json") -Destination $bridgeStaging -Force
Copy-Item -LiteralPath (Join-Path $Root "runtime\pi-bridge\tsconfig.json") -Destination $bridgeStaging -Force
Copy-Item -LiteralPath (Join-Path $Root "runtime\pi-bridge\vitest.config.ts") -Destination $bridgeStaging -Force
Copy-Item -LiteralPath (Join-Path $Root "runtime\pi-bridge\src") -Destination $bridgeStaging -Recurse -Force
Copy-Item -LiteralPath (Join-Path $Root "runtime\pi-bridge\test") -Destination $bridgeStaging -Recurse -Force

$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) { $npm = Get-Command npm -ErrorAction SilentlyContinue }
if (-not $npm) {
    throw "npm was not found; cannot prepare pi bridge dependencies."
}
Write-Progress-Line -Stage "bridge" -Message "Installing pi-bridge production dependencies..." -Percent 70 -Detail $bridgeStaging
Push-Location $bridgeStaging
try {
    & $npm.Source ci --omit=dev --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) {
        throw "npm ci failed for pi-bridge staging."
    }
    & $npm.Source run build
    if ($LASTEXITCODE -ne 0) {
        throw "pi-bridge build failed."
    }
}
finally {
    Pop-Location
}

$skillsStaging = Join-Path $StagingDir "bundled-skills"
if (Test-Path -LiteralPath $skillsStaging) {
    Remove-Item -LiteralPath $skillsStaging -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $Root "runtime\bundled-skills") -Destination $skillsStaging -Recurse -Force

$stagingManifest = @{
    manifest_version = 1
    runtime_version = $manifest.runtime_version
    node_version = $manifest.node.version
    pi_version = $manifest.pi.version
    staging_dir = $StagingDir
    prepared_at = (Get-Date).ToUniversalTime().ToString("o")
    bridge_entrypoint = $manifest.bridge.entrypoint
    bundled_skills = @($manifest.bundled_skills | ForEach-Object {
        @{
            id = $_.id
            manifest_path = $_.manifest_path
            origin_commit = $_.origin_commit
            license = $_.license
        }
    })
    node_archive_sha256_verified = $nodeDownload.sha256_verified
}
$stagingManifestPath = Join-Path $StagingDir "pi-runtime-staging.json"
$stagingManifest | ConvertTo-Json -Depth 6 | Out-File -LiteralPath $stagingManifestPath -Encoding utf8 -NoNewline

Write-Progress-Line -Stage "done" -Message "Pi runtime staging prepared." -Percent 100 -Detail $StagingDir
$result = @{
    ok = $true
    mode = "staging"
    staging_dir = $StagingDir
    staging_manifest = $stagingManifestPath
    runtime_version = $manifest.runtime_version
} | ConvertTo-Json -Compress
Write-Host $result
