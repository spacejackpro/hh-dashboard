@echo off
cd /d "%~dp0"
echo ============================================
echo  HH Dashboard setup (internet required)
echo ============================================
echo.

python --version >nul 2>nul
if errorlevel 1 (
    echo [1/3] Python not found. Trying to install it automatically...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    echo.
    echo Python installed. CLOSE this window and run setup.cmd AGAIN.
    pause
    exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
    echo Installed Python is too old, need 3.11 or newer.
    echo Download it from https://www.python.org/downloads/
    echo and check "Add python.exe to PATH" during install.
    pause
    exit /b 1
)

echo [1/3] Python found, creating environment...
python -m venv .venv
if errorlevel 1 ( echo Failed to create environment. & pause & exit /b 1 )

echo [2/3] Downloading the tool and libraries (takes a few minutes)...
.venv\Scripts\pip.exe install -q -r requirements.txt
if errorlevel 1 ( echo Install error. Check your internet and try again. & pause & exit /b 1 )

echo [3/3] Downloading browser for hh.ru login (~150 MB)...
.venv\Scripts\hh-applicant-tool.exe install

echo.
echo ============================================
echo  Setup complete!
echo ============================================
