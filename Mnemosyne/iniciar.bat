@echo off
cd /d "%~dp0"

set VENV_DIR=%~dp0..\.venv

if not exist "%VENV_DIR%" (
    echo Ambiente virtual nao encontrado em %VENV_DIR%
    echo Execute o setup na raiz do ecossistema primeiro.
    pause
    exit /b 1
)

call "%VENV_DIR%\Scripts\activate.bat"
python main.py
