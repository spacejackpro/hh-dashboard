@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  Установка HH Dashboard (нужен интернет)
echo ============================================
echo.

python --version >nul 2>nul
if errorlevel 1 (
    echo [1/3] Python не найден. Пробую установить автоматически...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    echo.
    echo Python установлен. ЗАКРОЙ это окно и запусти setup.cmd ЕЩЁ РАЗ.
    pause
    exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
    echo Установленный Python слишком старый, нужен 3.11 или новее.
    echo Скачай новый с https://www.python.org/downloads/
    echo и при установке поставь галочку "Add python.exe to PATH".
    pause
    exit /b 1
)

echo [1/3] Python найден, создаю окружение...
python -m venv .venv
if errorlevel 1 ( echo Не удалось создать окружение. & pause & exit /b 1 )

echo [2/3] Скачиваю утилиту и библиотеки (пара минут)...
.venv\Scripts\pip.exe install -q -r requirements.txt
if errorlevel 1 ( echo Ошибка установки. Проверь интернет и запусти ещё раз. & pause & exit /b 1 )

echo [3/3] Скачиваю браузер для авторизации (~150 МБ)...
.venv\Scripts\hh-applicant-tool.exe install

echo.
echo ============================================
echo  Установка завершена!
echo ============================================
