@echo off
setlocal EnableExtensions DisableDelayedExpansion

pushd "%~dp0"
if errorlevel 1 (
    echo [ERROR] Cannot open the project directory.
    exit /b 1
)

for %%I in ("%~dp0..\venv\Scripts\python.exe") do set "VENV_PYTHON=%%~fI"

if not exist "manage.py" (
    echo [ERROR] manage.py was not found next to run.bat.
    popd
    exit /b 1
)
if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment not found. Run install.bat first.
    popd
    exit /b 1
)

"%VENV_PYTHON%" manage.py collectstatic --noinput
if errorlevel 1 (
    echo [ERROR] Static files collection failed.
    popd
    exit /b 1
)

"%VENV_PYTHON%" manage.py runserver
set "RESULT=%ERRORLEVEL%"
popd
exit /b %RESULT%
