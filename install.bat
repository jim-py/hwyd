@echo off
setlocal EnableExtensions DisableDelayedExpansion

rem Place this file next to manage.py. The virtual environment lives one level up.
pushd "%~dp0"
if errorlevel 1 (
    echo [ERROR] Cannot open the project directory.
    exit /b 1
)

for %%I in ("%~dp0..\venv") do set "VENV_DIR=%%~fI"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

if not exist "manage.py" (
    echo [ERROR] manage.py was not found next to install.bat.
    goto :fail
)
if not exist "requirements.txt" (
    echo [ERROR] requirements.txt was not found next to install.bat.
    goto :fail
)

if exist "%VENV_PYTHON%" (
    echo [1/7] Using the existing virtual environment.
) else (
    echo [1/7] Creating the virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 goto :fail
)

echo [2/7] Upgrading pip...
"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo [3/7] Installing requirements...
"%VENV_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

if exist ".env" (
    echo [4/7] Keeping the existing .env file.
) else (
    echo [4/7] Generating .env...
    "%VENV_PYTHON%" -c "from pathlib import Path; from django.core.management.utils import get_random_secret_key; Path('.env').write_text('DJANGO_ENV=development\nDJANGO_SECRET_KEY=' + repr(get_random_secret_key()) + '\n', encoding='utf-8')"
    if errorlevel 1 goto :fail
)

echo [5/7] Creating migrations...
"%VENV_PYTHON%" manage.py makemigrations chat hwyd general_app notifications
if errorlevel 1 goto :fail

echo [6/7] Applying migrations...
"%VENV_PYTHON%" manage.py migrate
if errorlevel 1 goto :fail

echo [7/7] Collecting static files...
"%VENV_PYTHON%" manage.py collectstatic --noinput
if errorlevel 1 goto :fail

echo.
echo [OK] Installation complete. Start the site with run.bat.
popd
exit /b 0

:fail
echo.
echo [ERROR] Installation failed. See the message above.
popd
exit /b 1
