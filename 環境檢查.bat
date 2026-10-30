@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe goto missing
.venv\Scripts\python.exe check_environment.py
pause
exit /b
:missing
echo 請先執行首次安裝。
pause
