@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo Ejecuta primero instalar.bat desde la carpeta principal del repositorio.
    pause
    exit /b 1
)
set "PYTHONUTF8=1"
".venv\Scripts\python.exe" diagnostico_perfil\app.py
if errorlevel 1 pause
