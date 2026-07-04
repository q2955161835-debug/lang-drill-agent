[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InstallerPath
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Write-Step {
    param([string]$Message)
    Write-Host "[desktop-vm-test] $Message"
}

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
}

function Stop-LangDrillProcesses {
    Get-Process -Name "lang-drill-agent-desktop" -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue

    $connections = Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        if ($connection.OwningProcess) {
            Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

function Run-ProcessCapture {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$WorkingDirectory = (Get-Location).Path,
        [int]$TimeoutSeconds = 900
    )
    Write-Step ("Running: {0} {1}" -f $FilePath, ($Arguments -join " "))
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -Wait -PassThru -WindowStyle Hidden
    return $process.ExitCode
}

function Run-ProcessChecked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$WorkingDirectory = (Get-Location).Path,
        [int]$TimeoutSeconds = 900
    )
    $exitCode = Run-ProcessCapture -FilePath $FilePath -Arguments $Arguments -WorkingDirectory $WorkingDirectory -TimeoutSeconds $TimeoutSeconds
    if ($exitCode -ne 0) {
        throw "$FilePath exited with code $exitCode."
    }
}

function Invoke-DesktopRuntime {
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$AppDataDir,
        [Parameter(Mandatory = $true)][string]$LocalAppDataDir
    )
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $ScriptPath,
        "-ProjectRoot",
        $ProjectRoot,
        "-AppDataDir",
        $AppDataDir,
        "-LocalAppDataDir",
        $LocalAppDataDir,
        "-Port",
        "18080"
    )
    Write-Step ("Running installed backend runtime: powershell.exe {0}" -f ($arguments -join " "))
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & powershell.exe @arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    $output | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) {
        throw "Installed backend runtime failed with exit code $exitCode."
    }
    $progressLines = @($output | Where-Object { "$_".Contains("[langdrill-progress]") })
    Assert-True ($progressLines.Count -gt 0) "Installed backend runtime did not emit structured progress events."
    $jsonLine = $output | Where-Object { "$_".TrimStart().StartsWith("{") } | Select-Object -Last 1
    Assert-True ([bool]$jsonLine) "Installed backend runtime did not return JSON status."
    return $jsonLine | ConvertFrom-Json
}

function Wait-ForHealth {
    param([int]$TimeoutSeconds = 900)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:18080/api/health" -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300 -and $response.Content -like "*langdrill-agent*") {
                return $response.Content
            }
        }
        catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    }
    throw "Desktop backend health check did not pass within $TimeoutSeconds seconds. Last error: $lastError"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if ([System.IO.Path]::IsPathRooted($InstallerPath)) {
    $installer = (Resolve-Path -LiteralPath $InstallerPath).Path
}
else {
    $installer = (Resolve-Path -LiteralPath (Join-Path $repoRoot $InstallerPath)).Path
}

$testRoot = if ($env:RUNNER_TEMP) {
    Join-Path $env:RUNNER_TEMP "langdrill-installer-vm-test"
}
else {
    Join-Path $repoRoot "try\.cache\desktop-installer-vm"
}

$badInstallDir = Join-Path $testRoot ("InstallTarget-" + [char]0x4E2D + [char]0x6587)
$installDir = Join-Path $testRoot "InstallTarget"
$appDataRoot = Join-Path $testRoot "appdata"
$localAppDataRoot = Join-Path $testRoot "localappdata"
$desktopDir = [Environment]::GetFolderPath("DesktopDirectory")
$desktopShortcut = Join-Path $desktopDir "Lang Drill Agent.lnk"
$mainExe = Join-Path $installDir "lang-drill-agent-desktop.exe"
$uninstaller = Join-Path $installDir "uninstall.exe"
$runtimeScript = Join-Path $installDir "desktop-runtime\start-backend.ps1"
$installedProjectRoot = Join-Path $installDir "app"
$nsiScript = Join-Path $repoRoot "src-tauri\target\release\nsis\x64\installer.nsi"
$installerHook = Join-Path $repoRoot "src-tauri\installer-hooks.nsh"
$appDataDir = Join-Path $appDataRoot "Lang Drill Agent"
$localRuntimeDir = Join-Path $localAppDataRoot "Lang Drill Agent"

Write-Step "Preparing isolated directories."
Stop-LangDrillProcesses
Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $desktopShortcut -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $testRoot, $appDataRoot, $localAppDataRoot | Out-Null

$oldAppData = $env:APPDATA
$oldLocalAppData = $env:LOCALAPPDATA
$env:APPDATA = $appDataRoot
$env:LOCALAPPDATA = $localAppDataRoot

$passed = $false
try {
    Write-Step "Checking installer, generated NSIS script, and installer hook."
    Assert-True (Test-Path -LiteralPath $installer) "Installer was not found: $installer"
    Assert-True ((Get-Item -LiteralPath $installer).Length -gt 1000000) "Installer file is unexpectedly small."
    Assert-True (Test-Path -LiteralPath $nsiScript) "Generated NSIS script was not found: $nsiScript"
    Assert-True (Test-Path -LiteralPath $installerHook) "Installer hook was not found: $installerHook"
    $nsi = Get-Content -LiteralPath $nsiScript -Raw
    $hook = Get-Content -LiteralPath $installerHook -Raw
    Assert-True ($nsi -like "*MUI_PAGE_DIRECTORY*") "Installer does not include an install directory selection page."
    Assert-True ($nsi -like "*installer-hooks.nsh*") "Generated NSIS script does not include the installer hook."
    Assert-True ($hook -like "*LangDrillValidateAsciiInstallDir*") "Installer hook does not validate install paths."
    Assert-True ($hook -like "*English/ASCII*") "Installer hook does not explain the English/ASCII path requirement."
    Assert-True ($nsi -like '*INSTALLMODE "currentUser"*') "Installer is not configured for current-user install mode."

    Write-Step "Verifying non-ASCII install path is rejected."
    $badExitCode = Run-ProcessCapture -FilePath $installer -Arguments @("/S", "/D=$badInstallDir") -TimeoutSeconds 300
    Assert-True ($badExitCode -ne 0) "Installer unexpectedly accepted a non-ASCII install path."
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $badInstallDir "lang-drill-agent-desktop.exe"))) "Installer copied files into a non-ASCII install path."
    Remove-Item -LiteralPath $badInstallDir -Recurse -Force -ErrorAction SilentlyContinue

    Write-Step "Installing to custom ASCII directory."
    Run-ProcessChecked -FilePath $installer -Arguments @("/S", "/D=$installDir") -TimeoutSeconds 900
    Assert-True (Test-Path -LiteralPath $mainExe) "Main executable was not installed at custom directory: $mainExe"
    Assert-True (Test-Path -LiteralPath $uninstaller) "Uninstaller was not installed."
    Assert-True (Test-Path -LiteralPath $runtimeScript) "Desktop runtime script was not installed."
    Assert-True (Test-Path -LiteralPath (Join-Path $installedProjectRoot "pyproject.toml")) "Bundled backend project root was not installed."
    Assert-True (Test-Path -LiteralPath $desktopShortcut) "Desktop shortcut was not created: $desktopShortcut"

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($desktopShortcut)
    Assert-True ($shortcut.TargetPath -eq $mainExe) "Desktop shortcut target is '$($shortcut.TargetPath)', expected '$mainExe'."

    Write-Step "Starting installed backend runtime and waiting for health."
    $runtime = Invoke-DesktopRuntime -ScriptPath $runtimeScript -ProjectRoot $installedProjectRoot -AppDataDir $appDataDir -LocalAppDataDir $localRuntimeDir
    Assert-True ($runtime.ok -eq $true) "Installed backend runtime returned ok=false."
    $health = Wait-ForHealth -TimeoutSeconds 900
    Write-Step "Health response: $health"
    Assert-True (Test-Path -LiteralPath (Join-Path $appDataDir ".env")) "Desktop .env was not created under isolated APPDATA."
    Assert-True (Test-Path -LiteralPath (Join-Path $appDataDir "data\langdrill_agent.db")) "Desktop database was not created under isolated APPDATA."
    Assert-True (Test-Path -LiteralPath (Join-Path $localRuntimeDir "runtime\venv\Scripts\python.exe")) "Desktop Python virtual environment was not created under isolated LOCALAPPDATA."
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $installDir ".env"))) "Sensitive .env was written to the install directory."
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $installDir "data"))) "User data directory was written to the install directory."

    Write-Step "Stopping installed backend runtime."
    Stop-LangDrillProcesses

    Write-Step "Uninstalling."
    Run-ProcessChecked -FilePath $uninstaller -Arguments @("/S") -WorkingDirectory $installDir -TimeoutSeconds 300
    Assert-True (-not (Test-Path -LiteralPath $mainExe)) "Main executable still exists after uninstall."
    Assert-True (-not (Test-Path -LiteralPath $desktopShortcut)) "Desktop shortcut still exists after uninstall."

    $passed = $true
    Write-Step "Installer VM acceptance passed."
}
finally {
    Write-Step "Cleaning test VM state."
    Stop-LangDrillProcesses
    if (Test-Path -LiteralPath $desktopShortcut) {
        Remove-Item -LiteralPath $desktopShortcut -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $uninstaller) {
        Start-Process -FilePath $uninstaller -ArgumentList @("/S") -Wait -PassThru -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
    }
    if ($passed) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    else {
        Write-Step "Preserving test root for artifact upload: $testRoot"
    }
    $env:APPDATA = $oldAppData
    $env:LOCALAPPDATA = $oldLocalAppData
}

if (-not $passed) {
    exit 1
}
