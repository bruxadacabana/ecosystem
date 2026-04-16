@echo off
cd /d "%~dp0"

set EXE=%~dp0src-tauri\target\release\hub.exe

if exist "%EXE%" (
    start "" "%EXE%"
) else (
    echo [HUB] Binario de release nao encontrado. Compilando agora...
    echo [HUB] Execute "cargo tauri build --no-bundle" para agilizar aperturas futuras.
    cargo tauri dev
)
