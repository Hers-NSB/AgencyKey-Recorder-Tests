@echo off
cd /d "%~dp0"
py -3.12 -m venv .venv
if errorlevel 1 goto error
.venv\Scripts\python -m pip install -r requirements-build.txt
if errorlevel 1 goto error
.venv\Scripts\python -m PyInstaller --clean --noconfirm AgencyKeyRecorderTests.spec
if errorlevel 1 goto error
echo Ejecutable creado en dist\AgencyKeyRecorderTests.exe
pause
exit /b 0
:error
echo No se completo la compilacion.
pause
exit /b 1
