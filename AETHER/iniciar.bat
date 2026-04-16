@echo off
cd /d "%~dp0"

set EXE=%~dp0src-tauri\target\release\aether.exe

if exist "%EXE%" (
    start "" "%EXE%"
) else (
    echo [AETHER] Binario de release nao encontrado. Compilando agora...
    echo [AETHER] Execute "cargo tauri build --no-bundle" para agilizar aberturas futuras.
    cargo tauri dev
)
