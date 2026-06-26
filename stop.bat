@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "TASKKILL=%SystemRoot%\System32\taskkill.exe"
set "PING=%SystemRoot%\System32\ping.exe"
set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

echo ========================================
echo Lang Drill Agent 一键停止
echo ========================================

echo [1/2] 关闭服务窗口...
"%TASKKILL%" /fi "WINDOWTITLE eq LangDrill Backend*" /t /f >nul 2>&1
"%TASKKILL%" /fi "WINDOWTITLE eq LangDrill Frontend*" /t /f >nul 2>&1

echo [2/2] 清理占用端口 5173 / 8000...
"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -Command "$ports = 5173,8000; foreach ($port in $ports) { Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }"

echo 服务已停止。如仍有窗口残留，可手动关闭标题为 LangDrill 的命令行窗口。
"%PING%" 127.0.0.1 -n 3 >nul
endlocal
