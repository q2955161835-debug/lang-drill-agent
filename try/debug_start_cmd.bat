@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "ROOT=%~dp0..\"
for %%I in ("%ROOT%") do set "ROOT=%%~fI\"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
cd /d "%ROOT%"
echo ROOT=[%ROOT%]
echo VENV_PY=[%VENV_PY%]
echo CMD=["%VENV_PY%" -m langdrill_agent.cli init --display-name boss --target-language 英语 --exam-id cet4 --exam-name 大学英语四级]
"%VENV_PY%" -c "import sys; print(sys.executable); import langdrill_agent.cli; print('import-ok')"
echo PY_IMPORT_ERRORLEVEL=%errorlevel%
"%VENV_PY%" -m langdrill_agent.cli init --display-name boss --target-language 英语 --exam-id cet4 --exam-name 大学英语四级
echo INIT_ERRORLEVEL=%errorlevel%
endlocal
