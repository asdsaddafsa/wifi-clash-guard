@echo off
cd /d "%~dp0"
set "PYTHONW=%LocalAppData%\Python\pythoncore-3.14-64\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=pythonw.exe"
"%PYTHONW%" -X utf8 wifi_clash_guard.py
