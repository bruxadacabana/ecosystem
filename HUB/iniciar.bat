@echo off
cd /d "%~dp0"

:: Sempre compila e executa via cargo tauri dev.
:: O cargo detecta o que mudou e recompila apenas o necessario --
:: se nada mudou, inicia em segundos. O binario de release (target\release\hub.exe)
:: e gerado separadamente com "cargo tauri build" e nao e usado aqui.
cargo tauri dev
