[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$SkipInstall,
    [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$FrontendDir = Join-Path $Root "frontend"
$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$LogsDir = Join-Path $Root "logs"
$BackendOutLog = Join-Path $LogsDir "langdrill-backend.out.log"
$BackendErrLog = Join-Path $LogsDir "langdrill-backend.err.log"
$FrontendOutLog = Join-Path $LogsDir "langdrill-frontend.out.log"
$FrontendErrLog = Join-Path $LogsDir "langdrill-frontend.err.log"

function Write-Step {
    param([string]$Message)
    Write-Host $Message
}

function Invoke-PythonLauncher {
    param([string[]]$Arguments)

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        & $pyLauncher.Source -3 @Arguments
        return $LASTEXITCODE
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        & $python.Source @Arguments
        return $LASTEXITCODE
    }

    throw "Python was not found. Install Python 3.11+ and enable Add Python to PATH."
}

function Assert-ExitCode {
    param(
        [int]$ExitCode,
        [string]$FailureMessage
    )

    if ($ExitCode -ne 0) {
        throw $FailureMessage
    }
}

function Stop-LangDrillPortListeners {
    param([int[]]$Ports)

    foreach ($port in $Ports) {
        $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique

        foreach ($processId in $listeners) {
            if ($processId -and $processId -gt 0) {
                Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

function Update-DevEnvFile {
    param([string]$EnvPath)

    $managedKeys = @(
        "LANGDRILL_DEFAULT_PROVIDER",
        "LANGDRILL_DEFAULT_MODEL",
        "LANGDRILL_PROVIDER_BASE_URL"
    )

    $existingLines = @()
    if (Test-Path $EnvPath) {
        $existingLines = Get-Content -Path $EnvPath -Encoding UTF8
    }

    $keptLines = foreach ($line in $existingLines) {
        $isManaged = $false
        foreach ($key in $managedKeys) {
            if ($line -like "$key=*") {
                $isManaged = $true
                break
            }
        }
        if (-not $isManaged) {
            $line
        }
    }

    $newLines = @(
        "LANGDRILL_DEFAULT_PROVIDER=mimo",
        "LANGDRILL_DEFAULT_MODEL=mimo-v2.5-pro",
        "LANGDRILL_PROVIDER_BASE_URL=https://api.xiaomimimo.com/v1"
    )

    [System.IO.File]::WriteAllLines($EnvPath, [string[]]($keptLines + $newLines), $utf8)

    $env:LANGDRILL_DEFAULT_PROVIDER = "mimo"
    $env:LANGDRILL_DEFAULT_MODEL = "mimo-v2.5-pro"
    $env:LANGDRILL_PROVIDER_BASE_URL = "https://api.xiaomimimo.com/v1"
}

function Read-LogTail {
    param([string[]]$Paths)

    foreach ($path in $Paths) {
        if (Test-Path $path) {
            Write-Host ""
            Write-Host "---- $path ----"
            Get-Content -Path $path -Tail 80 -ErrorAction SilentlyContinue
        }
    }
}

function Wait-LangDrillHttp {
    param(
        [string]$Name,
        [string]$Url,
        [System.Diagnostics.Process]$Process,
        [string[]]$LogPaths,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($Process.HasExited) {
            Write-Host ""
            Write-Host "[error] $Name process exited with code $($Process.ExitCode)."
            Read-LogTail -Paths $LogPaths
            throw "$Name failed to start."
        }

        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    Write-Host ""
    Write-Host "[error] $Name was not ready within $TimeoutSeconds seconds: $Url"
    Read-LogTail -Paths $LogPaths
    throw "$Name health check timed out."
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
Set-Location $Root

Write-Host "========================================"
Write-Host "Lang Drill Agent startup"
Write-Host "========================================"
Write-Host "Project root: $Root"
Write-Host ""

$backendProcess = $null
$frontendProcess = $null

try {
    if (-not (Test-Path $VenvPython)) {
        Write-Step "[prepare] .venv was not found. Creating Python virtual environment..."
        $exitCode = Invoke-PythonLauncher -Arguments @("-m", "venv", $VenvDir)
        Assert-ExitCode -ExitCode $exitCode -FailureMessage "Failed to create Python virtual environment."
    }

    if (-not $SkipInstall) {
        Write-Step "[prepare] Installing/updating backend dependencies..."
        & $VenvPython -m pip install -e "$Root[dev]"
        Assert-ExitCode -ExitCode $LASTEXITCODE -FailureMessage "Failed to install backend dependencies."

        if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
            Write-Step "[prepare] frontend node_modules was not found. Running npm install..."
            $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
            if (-not $npm) {
                $npm = Get-Command npm -ErrorAction SilentlyContinue
            }
            if (-not $npm) {
                throw "npm was not found. Install Node.js LTS first."
            }

            Push-Location $FrontendDir
            try {
                & $npm.Source install
                Assert-ExitCode -ExitCode $LASTEXITCODE -FailureMessage "Failed to install frontend dependencies."
            }
            finally {
                Pop-Location
            }
        }
    }

    Write-Step "[prepare] Stopping listeners on ports 5173 and 8000..."
    Stop-LangDrillPortListeners -Ports @(5173, 8000)

    Remove-Item -Path $BackendOutLog, $BackendErrLog, $FrontendOutLog, $FrontendErrLog -Force -ErrorAction SilentlyContinue

    Write-Step "[prepare] Writing default dev MiMo config to .env while keeping the existing API key..."
    Update-DevEnvFile -EnvPath (Join-Path $Root ".env")
    Write-Step "[prepare] Default dev MiMo config is ready. Add an API key in the web settings if needed."

    $env:PYTHONPATH = Join-Path $Root "backend"
    & $VenvPython -m langdrill_agent.cli init --display-name "boss" --exam-id "cet4"
    Assert-ExitCode -ExitCode $LASTEXITCODE -FailureMessage "Database initialization failed."

    Write-Step "[2/3] Starting backend API: http://127.0.0.1:8000"
    $backendProcess = Start-Process `
        -FilePath $VenvPython `
        -ArgumentList @("-m", "langdrill_agent.cli", "serve") `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $BackendOutLog `
        -RedirectStandardError $BackendErrLog `
        -PassThru

    Wait-LangDrillHttp `
        -Name "backend API" `
        -Url "http://127.0.0.1:8000/docs" `
        -Process $backendProcess `
        -LogPaths @($BackendOutLog, $BackendErrLog) `
        -TimeoutSeconds $TimeoutSeconds

    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npmCommand) {
        $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
    }
    if (-not $npmCommand) {
        throw "npm was not found. Install Node.js LTS first."
    }

    Write-Step "[3/3] Starting frontend web: http://127.0.0.1:5173"
    $frontendProcess = Start-Process `
        -FilePath $npmCommand.Source `
        -ArgumentList @("run", "dev") `
        -WorkingDirectory $FrontendDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $FrontendOutLog `
        -RedirectStandardError $FrontendErrLog `
        -PassThru

    Wait-LangDrillHttp `
        -Name "frontend web" `
        -Url "http://127.0.0.1:5173" `
        -Process $frontendProcess `
        -LogPaths @($FrontendOutLog, $FrontendErrLog) `
        -TimeoutSeconds $TimeoutSeconds

    if (-not $NoBrowser) {
        Write-Step "Opening browser..."
        Start-Process "http://127.0.0.1:5173"
    }

    Write-Host ""
    Write-Host "Lang Drill Agent is running in the background."
    Write-Host "Stop it with: stop.bat"
    Write-Host "Backend log: $BackendOutLog"
    Write-Host "Backend error log: $BackendErrLog"
    Write-Host "Frontend log: $FrontendOutLog"
    Write-Host "Frontend error log: $FrontendErrLog"
    Write-Host "URL: http://127.0.0.1:5173"
}
catch {
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontendProcess -and -not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }

    Write-Host ""
    Write-Host "[error] $($_.Exception.Message)"
    exit 1
}
