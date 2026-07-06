@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\uvicorn.exe" (
    echo Похоже, это первый запуск — сейчас всё установлю, подожди пару минут...
    echo.
    call setup.cmd
)
if not exist ".venv\Scripts\uvicorn.exe" (
    echo.
    echo Установка не удалась — смотри сообщения выше.
    pause
    exit /b 1
)

start "" http://127.0.0.1:8517

:run
if exist ".update-pending" (
    echo Довожу обновление: проверяю движок и библиотеки...
    .venv\Scripts\pip.exe install -q -U -r requirements.txt
    del ".update-pending"
)
.venv\Scripts\uvicorn.exe dashboard.app:app --host 127.0.0.1 --port 8517
if "%errorlevel%"=="42" goto run
