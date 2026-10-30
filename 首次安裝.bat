@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 --version >nul 2>&1
if errorlevel 1 goto missing
if not exist .venv\Scripts\python.exe py -3 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
.venv\Scripts\python.exe check_environment.py
if errorlevel 1 goto fail
echo 安裝完成，請雙擊「啟動系統.bat」。
pause
exit /b 0
:missing
echo 請先從 python.org 安裝 Python 3.10 以上版本，包含 Python Launcher。
goto fail
:fail
echo 安裝未完成，請保留此畫面的錯誤訊息供協助排查。
pause
exit /b 1
