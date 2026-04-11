@echo off
cd /d "%~dp0"
if exist "_portable\python\python.exe" (
    _portable\python\python.exe downloader.py
) else (
    python downloader.py
)
pause
