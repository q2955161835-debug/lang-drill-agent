[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$AppDataDir,
    [Parameter(Mandatory = $true)][string]$LocalAppDataDir,
    [int]$Port = 18080
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}
$utf8 = [System.Text.UTF8Encoding]::new($false)
$utf8Bom = [System.Text.UTF8Encoding]::new($true)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

function Normalize-WindowsPathForPowerShell {
    param([string]$PathValue)
    if ($PathValue.StartsWith("\\?\UNC\")) {
        return "\\" + $PathValue.Substring(8)
    }
    if ($PathValue.StartsWith("\\?\")) {
        return $PathValue.Substring(4)
    }
    return $PathValue
}

$ProjectRoot = Normalize-WindowsPathForPowerShell $ProjectRoot
$AppDataDir = Normalize-WindowsPathForPowerShell $AppDataDir
$LocalAppDataDir = Normalize-WindowsPathForPowerShell $LocalAppDataDir

$PythonVersion = "3.11.9"
$PythonInstallerUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
$RuntimeDir = Join-Path $LocalAppDataDir "runtime"
$DownloadDir = Join-Path $RuntimeDir "downloads"
$PythonDir = Join-Path $RuntimeDir "python-$PythonVersion"
$VenvDir = Join-Path $RuntimeDir "venv"
$SourceDir = Join-Path $RuntimeDir "app-source"
$LogDir = Join-Path $AppDataDir "logs"
$PapersDir = Join-Path $AppDataDir "papers"
$EnvPath = Join-Path $AppDataDir ".env"
$BackendOutLog = Join-Path $LogDir "langdrill-desktop-backend.out.log"
$BackendErrLog = Join-Path $LogDir "langdrill-desktop-backend.err.log"
$InstallLog = Join-Path $LogDir "langdrill-desktop-install.log"
$InstallErrLog = Join-Path $LogDir "langdrill-desktop-install.err.log"
$HealthUrl = "http://127.0.0.1:$Port/api/health"
$BootstrapUrl = "http://127.0.0.1:$Port/api/bootstrap"

function Write-Status {
    param([string]$Message)
    [Console]::Error.WriteLine("[desktop-runtime] $Message")
}

function ConvertTo-PowerShellLiteral {
    param([string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function ConvertTo-NativeArgument {
    param([string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Assert-ExitCode {
    param([int]$ExitCode, [string]$Message)
    if ($ExitCode -ne 0) {
        throw $Message
    }
}

function Invoke-NativeLogged {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $FilePath @Arguments 1>> $InstallLog 2>> $InstallErrLog
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    Assert-ExitCode -ExitCode $exitCode -Message $FailureMessage
}

function Resolve-PythonCandidate {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @()
    )
    $probe = "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}'); print(sys.executable)"
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $FilePath @Arguments "-c" $probe 2>$null
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($exitCode -ne 0 -or -not $output -or $output.Count -lt 2) {
        return $null
    }
    $versionText = ([string]$output[0]).Trim()
    $version = [version]$versionText
    $pythonExe = ([string]$output[1]).Trim()
    if ($version.Major -ne 3 -or $version.Minor -lt 11 -or -not (Test-Path $pythonExe)) {
        return $null
    }
    return $pythonExe
}

function Find-ExistingPython {
    $candidates = @(
        @{ FilePath = "py.exe"; Arguments = @("-3.13") },
        @{ FilePath = "py.exe"; Arguments = @("-3.12") },
        @{ FilePath = "py.exe"; Arguments = @("-3.11") },
        @{ FilePath = "python.exe"; Arguments = @() },
        @{ FilePath = "python3.exe"; Arguments = @() }
    )
    foreach ($candidate in $candidates) {
        $pythonExe = Resolve-PythonCandidate -FilePath $candidate.FilePath -Arguments $candidate.Arguments
        if ($pythonExe) {
            return $pythonExe
        }
    }
    return $null
}

function Get-PortOwner {
    param([int]$TargetPort)
    try {
        $connection = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($connection) {
            return [int]$connection.OwningProcess
        }
    }
    catch {
        return 0
    }
    return 0
}

function Test-LangDrillHealth {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 2
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300 -and $response.Content -like "*langdrill-agent*") {
            return $true
        }
    }
    catch {
        return $false
    }
    return $false
}

function Test-AnyHttpListener {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $BootstrapUrl -TimeoutSec 2
        return $response.StatusCode -gt 0
    }
    catch {
        return $false
    }
}

function Ensure-DesktopEnv {
    New-Item -ItemType Directory -Force -Path $AppDataDir, $LogDir, $PapersDir | Out-Null
    $defaults = [ordered]@{
        "LANGDRILL_USER_DATA_DIR" = $AppDataDir.Replace("\", "/")
        "LANGDRILL_DB_PATH" = (Join-Path $AppDataDir "data\langdrill_agent.db").Replace("\", "/")
        "LANGDRILL_MIGRATE_LEGACY_DB" = "0"
        "LANGDRILL_PAPER_ROOT" = $PapersDir.Replace("\", "/")
        "LANGDRILL_LOG_LEVEL" = "INFO"
        "LANGDRILL_USER_NAME" = "boss"
        "LANGDRILL_DEFAULT_PROVIDER" = "mimo"
        "LANGDRILL_DEFAULT_MODEL" = "mimo-v2.5-pro"
        "LANGDRILL_PROVIDER_BASE_URL" = "https://api.xiaomimimo.com/anthropic"
    }

    $values = [ordered]@{}
    if (Test-Path $EnvPath) {
        foreach ($line in Get-Content -LiteralPath $EnvPath -Encoding UTF8) {
            if (-not $line -or $line.TrimStart().StartsWith("#") -or $line -notlike "*=*") {
                continue
            }
            $parts = $line -split "=", 2
            $values[$parts[0].Trim()] = $parts[1].Trim()
        }
    }

    foreach ($key in $defaults.Keys) {
        if (-not $values.Contains($key) -or -not $values[$key]) {
            $values[$key] = $defaults[$key]
        }
    }

    $lines = foreach ($key in $values.Keys) {
        "$key=$($values[$key])"
    }
    [System.IO.File]::WriteAllLines($EnvPath, [string[]]$lines, $utf8)
}

function Sync-AppSource {
    New-Item -ItemType Directory -Force -Path $SourceDir | Out-Null
    $sourceBackend = Join-Path $ProjectRoot "backend\langdrill_agent"
    $targetBackendRoot = Join-Path $SourceDir "backend"
    $targetBackend = Join-Path $targetBackendRoot "langdrill_agent"
    $sourcePyproject = Join-Path $ProjectRoot "pyproject.toml"
    $targetPyproject = Join-Path $SourceDir "pyproject.toml"

    if (-not (Test-Path $sourceBackend)) {
        throw "Bundled backend package was not found: $sourceBackend"
    }
    if (-not (Test-Path $sourcePyproject)) {
        throw "Bundled pyproject.toml was not found: $sourcePyproject"
    }

    New-Item -ItemType Directory -Force -Path $targetBackendRoot | Out-Null
    if (Test-Path $targetBackend) {
        Remove-Item -LiteralPath $targetBackend -Recurse -Force
    }
    Copy-Item -LiteralPath $sourceBackend -Destination $targetBackendRoot -Recurse -Force
    Copy-Item -LiteralPath $sourcePyproject -Destination $targetPyproject -Force
}

function Ensure-Python {
    $existingPython = Find-ExistingPython
    if ($existingPython) {
        Write-Status "Using existing Python runtime: $existingPython"
        return $existingPython
    }

    $pythonExe = Join-Path $PythonDir "python.exe"
    if (Test-Path $pythonExe) {
        return $pythonExe
    }

    New-Item -ItemType Directory -Force -Path $DownloadDir, $PythonDir | Out-Null
    $installer = Join-Path $DownloadDir "python-$PythonVersion-amd64.exe"
    if (-not (Test-Path $installer)) {
        Write-Status "Downloading Python $PythonVersion runtime from python.org..."
        Invoke-WebRequest -UseBasicParsing -Uri $PythonInstallerUrl -OutFile $installer
    }

    Write-Status "Installing Python $PythonVersion runtime into user cache..."
    $installerLog = Join-Path $LogDir "python-installer.log"
    $arguments = @(
        "/quiet",
        "InstallAllUsers=0",
        ("TargetDir=" + (ConvertTo-NativeArgument $PythonDir)),
        "Include_pip=1",
        "Include_launcher=0",
        "PrependPath=0",
        "Include_test=0",
        "Shortcuts=0",
        "/log",
        (ConvertTo-NativeArgument $installerLog)
    )
    $process = Start-Process -FilePath $installer -ArgumentList ($arguments -join " ") -Wait -PassThru -WindowStyle Hidden
    Assert-ExitCode -ExitCode $process.ExitCode -Message "Python runtime installer failed with exit code $($process.ExitCode)."
    if (-not (Test-Path $pythonExe)) {
        throw "Python runtime installation finished but python.exe was not found: $pythonExe"
    }
    return $pythonExe
}

function Ensure-Venv {
    param([string]$PythonExe)
    $venvPython = Join-Path $VenvDir "Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Status "Creating desktop virtual environment..."
        Invoke-NativeLogged -FilePath $PythonExe -Arguments @("-m", "venv", $VenvDir) -FailureMessage "Failed to create desktop virtual environment."
    }
    Write-Status "Installing/updating backend dependencies..."
    Invoke-NativeLogged -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip") -FailureMessage "Failed to upgrade pip in desktop virtual environment."
    Invoke-NativeLogged -FilePath $venvPython -Arguments @("-m", "pip", "install", "$SourceDir[paper-parsing]") -FailureMessage "Failed to install Lang Drill Agent backend dependencies."
    return $venvPython
}

function Start-Backend {
    param([string]$PythonExe)
    Remove-Item -Path $BackendOutLog, $BackendErrLog -Force -ErrorAction SilentlyContinue

    $dbPath = Join-Path $AppDataDir "data\langdrill_agent.db"
    $backendPythonPath = Join-Path $SourceDir "backend"

    $env:LANGDRILL_ENV_FILE = $EnvPath
    $env:LANGDRILL_USER_DATA_DIR = $AppDataDir
    $env:LANGDRILL_DB_PATH = $dbPath
    $env:LANGDRILL_PAPER_ROOT = $PapersDir
    $env:PYTHONPATH = $backendPythonPath

    Invoke-NativeLogged -FilePath $PythonExe -Arguments @("-m", "langdrill_agent.cli", "init", "--display-name", "boss", "--exam-id", "cet4") -FailureMessage "Desktop database initialization failed."

    $runner = Join-Path $RuntimeDir "run-backend.ps1"
    $runnerLines = @(
        '$ErrorActionPreference = "Continue"',
        '$ProgressPreference = "SilentlyContinue"',
        'if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) { $PSNativeCommandUseErrorActionPreference = $false }',
        ('$env:LANGDRILL_ENV_FILE = ' + (ConvertTo-PowerShellLiteral $EnvPath)),
        ('$env:LANGDRILL_USER_DATA_DIR = ' + (ConvertTo-PowerShellLiteral $AppDataDir)),
        ('$env:LANGDRILL_DB_PATH = ' + (ConvertTo-PowerShellLiteral $dbPath)),
        ('$env:LANGDRILL_PAPER_ROOT = ' + (ConvertTo-PowerShellLiteral $PapersDir)),
        ('$env:PYTHONPATH = ' + (ConvertTo-PowerShellLiteral $backendPythonPath)),
        '$env:PYTHONUTF8 = "1"',
        '$env:PYTHONIOENCODING = "utf-8"',
        ('Set-Location ' + (ConvertTo-PowerShellLiteral $SourceDir)),
        ('& ' + (ConvertTo-PowerShellLiteral $PythonExe) + ' -m langdrill_agent.cli serve --host 127.0.0.1 --port ' + $Port + ' 1>> ' + (ConvertTo-PowerShellLiteral $BackendOutLog) + ' 2>> ' + (ConvertTo-PowerShellLiteral $BackendErrLog)),
        'exit $LASTEXITCODE'
    )
    [System.IO.File]::WriteAllLines($runner, [string[]]$runnerLines, $utf8Bom)

    $runnerArguments = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        (ConvertTo-NativeArgument $runner)
    ) -join " "

    $process = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $runnerArguments `
        -WorkingDirectory $SourceDir `
        -WindowStyle Hidden `
        -PassThru

    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        if ($process.HasExited) {
            $stderr = if (Test-Path $BackendErrLog) { (Get-Content -LiteralPath $BackendErrLog -Tail 80 -ErrorAction SilentlyContinue) -join "`n" } else { "" }
            throw "Desktop backend exited with code $($process.ExitCode). $stderr"
        }
        if (Test-LangDrillHealth) {
            return $process
        }
        Start-Sleep -Seconds 1
    }
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw "Desktop backend did not pass health check within 90 seconds. See $BackendErrLog"
}

New-Item -ItemType Directory -Force -Path $RuntimeDir, $LogDir | Out-Null

if (Test-LangDrillHealth) {
    $owner = Get-PortOwner -TargetPort $Port
    [Console]::Out.WriteLine((@{ ok = $true; owned = $false; pid = $owner; url = "http://127.0.0.1:$Port"; env = $EnvPath } | ConvertTo-Json -Compress))
    exit 0
}

$portOwner = Get-PortOwner -TargetPort $Port
if ($portOwner -ne 0 -or (Test-AnyHttpListener)) {
    throw "Port $Port is already in use by a non-Lang Drill Agent process. Close that process or change the desktop backend port."
}

Ensure-DesktopEnv
Sync-AppSource
$basePython = Ensure-Python
$venvPython = Ensure-Venv -PythonExe $basePython
$backendProcess = Start-Backend -PythonExe $venvPython

[Console]::Out.WriteLine((@{
    ok = $true
    owned = $true
    pid = $backendProcess.Id
    url = "http://127.0.0.1:$Port"
    env = $EnvPath
    python = $venvPython
    log_dir = $LogDir
} | ConvertTo-Json -Compress))
