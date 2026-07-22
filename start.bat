@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0"
set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "LAUNCHER=%ROOT%scripts\dev\start-dev.ps1"

if not exist "%LAUNCHER%" (
  echo [错误] 未找到启动器：%LAUNCHER%
  pause
  exit /b 1
)

"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%"
set "EXIT_CODE=%errorlevel%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [错误] Lang Drill Agent 启动失败，请查看 logs 目录中的日志。
  pause
  exit /b %EXIT_CODE%
)

endlocal
