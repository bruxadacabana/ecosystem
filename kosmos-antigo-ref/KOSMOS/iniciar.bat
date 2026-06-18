@echo off
cd /d "%~dp0"

set VENV_DIR=%~dp0..\.venv

if not exist "%VENV_DIR%" (
    echo [KOSMOS] Criando ambiente virtual em %VENV_DIR%...
    python -m venv "%VENV_DIR%"
    call "%VENV_DIR%\Scripts\activate.bat"
    echo [KOSMOS] Instalando dependencias...
    pip install --upgrade pip -q
    pip install -r requirements.txt
) else (
    call "%VENV_DIR%\Scripts\activate.bat"
)

python main.py
