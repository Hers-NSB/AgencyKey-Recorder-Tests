@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Verificar Mi perfil
pushd "%~dp0"
if errorlevel 1 goto folder_error

if not exist "verificar_perfil_web.py" goto missing_files
if not exist "requirements.txt" goto missing_files

set "VENV=.venv-verificar-perfil"
set "VERIFY_PYTHON=%VENV%\Scripts\python.exe"
set "INSTALLED_REQUIREMENTS=%VENV%\requirements-instalados.txt"

if exist "%VERIFY_PYTHON%" goto check_dependencies
py -3.12 -c "import sys" >nul 2>&1
if errorlevel 1 goto python_missing
echo Preparando el entorno de Python...
py -3.12 -m venv "%VENV%"
if errorlevel 1 goto setup_error
goto install_dependencies

:check_dependencies
if not exist "%INSTALLED_REQUIREMENTS%" goto install_dependencies
fc /b "requirements.txt" "%INSTALLED_REQUIREMENTS%" >nul 2>&1
if not errorlevel 1 goto run_verifier

:install_dependencies
if exist "%INSTALLED_REQUIREMENTS%" del /q "%INSTALLED_REQUIREMENTS%"
if exist "%INSTALLED_REQUIREMENTS%" goto setup_error
echo Instalando las dependencias del verificador...
"%VERIFY_PYTHON%" -m pip install -r "requirements.txt"
if errorlevel 1 goto setup_error
copy /y "requirements.txt" "%INSTALLED_REQUIREMENTS%" >nul
if errorlevel 1 goto setup_error

:run_verifier
echo Cierra la app de Windows antes de pulsar Verificar Mi perfil en el panel.
"%VERIFY_PYTHON%" "verificar_perfil_web.py"
set "VERIFY_EXIT=%ERRORLEVEL%"
if "%VERIFY_EXIT%"=="0" goto finish
echo El verificador termino con el codigo %VERIFY_EXIT%. Revisa el mensaje anterior.
goto finish

:python_missing
echo Instala Python 3.12 con el lanzador py y vuelve a abrir este archivo.
goto failed

:missing_files
echo Extrae todo el ZIP de la rama antes de abrir este archivo.
goto failed

:setup_error
echo No se pudo preparar el entorno. Revisa el mensaje anterior y vuelve a intentarlo.

:failed
set "VERIFY_EXIT=1"

:finish
popd
echo(
pause
exit /b %VERIFY_EXIT%

:folder_error
echo No se pudo abrir la carpeta del verificador.
pause
exit /b 1
