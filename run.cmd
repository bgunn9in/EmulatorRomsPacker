@echo off
setlocal

cd /d "%~dp0"
set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv ".venv"
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo Python was not found. Install Python 3 and make it available in PATH. 1>&2
            exit /b 1
        )
        python -m venv ".venv"
    )
)

"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 exit /b %errorlevel%

"%VENV_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 exit /b %errorlevel%

"%VENV_PYTHON%" main.py --config config.json %*
exit /b %errorlevel%
