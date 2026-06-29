@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0"
set "BACKEND_TITLE=LangDrill Backend"
set "FRONTEND_TITLE=LangDrill Frontend"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
set "TASKKILL=%SystemRoot%\System32\taskkill.exe"
set "PING=%SystemRoot%\System32\ping.exe"
set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "BACKEND_LOG=%ROOT%logs\langdrill-backend.out.log"
set "FRONTEND_LOG=%ROOT%logs\langdrill-frontend.out.log"

cd /d "%ROOT%"
if not exist "%ROOT%logs" mkdir "%ROOT%logs"

echo ========================================
echo Lang Drill Agent 一键启动
echo ========================================
echo 项目目录：%ROOT%
echo.

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY_LAUNCHER=py"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PY_LAUNCHER=python"
  ) else (
    echo [错误] 未找到 Python。请先安装 Python 3.11+，并勾选 Add Python to PATH。
    pause
    exit /b 1
  )
)

if not exist "%VENV_PY%" (
  echo [准备] 未找到 .venv，正在创建 Python 虚拟环境...
  %PY_LAUNCHER% -m venv "%ROOT%.venv"
  if errorlevel 1 (
    echo [错误] 创建虚拟环境失败。
    pause
    exit /b 1
  )
)

echo [准备] 安装/更新后端依赖...
call "%VENV_PY%" -m pip install -e "%ROOT%[dev]"
if errorlevel 1 (
  echo [错误] 后端依赖安装失败。
  pause
  exit /b 1
)

if not exist "%ROOT%frontend\node_modules" (
  echo [准备] 未找到前端依赖，正在执行 npm install...
  pushd "%ROOT%frontend"
  call npm install
  if errorlevel 1 (
    popd
    echo [错误] 前端依赖安装失败。请确认已安装 Node.js LTS。
    pause
    exit /b 1
  )
  popd
)

echo [准备] 清理可能占用的端口 5173 / 8000...
"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -Command "$ports = 5173,8000; foreach ($port in $ports) { Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }"

echo [准备] 写入开发期默认 MiMo 配置到 .env，并保留已有 API Key...
if not exist ".env" type nul > ".env"
findstr /v /b /c:"LANGDRILL_DEFAULT_PROVIDER=" /c:"LANGDRILL_DEFAULT_MODEL=" /c:"LANGDRILL_PROVIDER_BASE_URL=" ".env" > ".env.tmp" 2>nul
type ".env.tmp" > ".env"
del ".env.tmp" >nul 2>&1
echo LANGDRILL_DEFAULT_PROVIDER=mimo>> ".env"
echo LANGDRILL_DEFAULT_MODEL=mimo-v2.5-pro>> ".env"
echo LANGDRILL_PROVIDER_BASE_URL=https://api.xiaomimimo.com/v1>> ".env"
echo 已写入开发期默认 MiMo 配置。若尚未配置 API Key，请在网页设置中填写。
set "PYTHONPATH=%ROOT%backend"
call "%VENV_PY%" -m langdrill_agent.cli init --display-name boss --target-language 英语 --exam-id cet4 --exam-name 大学英语四级
if errorlevel 1 (
  echo [错误] 数据库初始化失败。
  pause
  exit /b 1
)

echo [2/3] 后台启动后端 API：http://127.0.0.1:8000
"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath $env:ComSpec -WindowStyle Hidden -WorkingDirectory '%ROOT%' -ArgumentList '/c','set PYTHONPATH=%ROOT%backend&& ""%VENV_PY%"" -m langdrill_agent.cli serve > ""%BACKEND_LOG%"" 2>&1'"

echo [3/3] 后台启动前端 Web：http://127.0.0.1:5173
"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath $env:ComSpec -WindowStyle Hidden -WorkingDirectory '%ROOT%frontend' -ArgumentList '/c','npm run dev > ""%FRONTEND_LOG%"" 2>&1'"

echo 等待服务初始化...
"%PING%" 127.0.0.1 -n 7 >nul

echo 正在打开浏览器...
start "" "http://127.0.0.1:5173"

echo.
echo 已在后台启动。关闭服务请运行 stop.bat。
echo 后端日志：%BACKEND_LOG%
echo 前端日志：%FRONTEND_LOG%
echo 如果浏览器暂时打不开，请等待几秒后手动访问：http://127.0.0.1:5173
echo.
endlocal
