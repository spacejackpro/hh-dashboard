@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\uvicorn.exe" (
    echo First run: installing everything, this may take a few minutes...
    echo.
    call setup.cmd
)
if not exist ".venv\Scripts\uvicorn.exe" (
    echo.
    echo Setup failed - see messages above.
    pause
    exit /b 1
)

rem Already running (e.g. launcher clicked twice)? Just open the browser.
netstat -ano | findstr ":8517" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    start "" http://127.0.0.1:8517
    exit /b 0
)

start "" http://127.0.0.1:8517

:run
if exist ".update-pending" (
    echo Finishing update: upgrading engine and libraries...
    .venv\Scripts\pip.exe install -q -U -r requirements.txt
    del ".update-pending"
)
.venv\Scripts\uvicorn.exe dashboard.app:app --host 127.0.0.1 --port 8517
if "%errorlevel%"=="42" goto run
