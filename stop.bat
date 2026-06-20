@echo off
chcp 65001 >nul
echo 正在停止 Lang Drill Agent 服务...

echo [1/2] 关闭服务窗口...
taskkill /fi "WINDOWTITLE eq LangDrill Backend*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq LangDrill Frontend*" /t /f >nul 2>&1

echo [2/2] 清理占用端口...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173 " ^| find "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| find "LISTENING"') do taskkill /f /pid %%a >nul 2>&1

echo 服务已成功停止。
timeout /t 2 >nul
