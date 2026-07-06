@echo off
chcp 65001 >nul

rem Скрипт копирует сам себя во временную папку и работает оттуда,
rem чтобы можно было безопасно обновить в том числе и сам update.cmd.
if /i not "%~dp0"=="%TEMP%\" (
    copy /y "%~f0" "%TEMP%\hh_dashboard_update.cmd" >nul
    "%TEMP%\hh_dashboard_update.cmd" "%~dp0"
    exit /b
)

cd /d "%~1"
echo ============================================
echo  Обновление HH Dashboard
echo ============================================
echo.
echo [1/3] Скачиваю свежую версию с GitHub...
powershell -NoProfile -Command "Invoke-WebRequest 'https://codeload.github.com/OWNER/hh-dashboard/zip/refs/heads/main' -OutFile (Join-Path $env:TEMP 'hhdash.zip')"
if errorlevel 1 (
    echo Не удалось скачать. Проверь интернет и попробуй ещё раз.
    pause
    exit /b 1
)

powershell -NoProfile -Command "Remove-Item -Recurse -Force (Join-Path $env:TEMP 'hhdash') -ErrorAction SilentlyContinue; Expand-Archive -Force (Join-Path $env:TEMP 'hhdash.zip') (Join-Path $env:TEMP 'hhdash')"
xcopy /E /Y /Q "%TEMP%\hhdash\hh-dashboard-main\*" . >nul
echo       Код обновлён.

echo [2/3] Обновляю движок hh-applicant-tool и библиотеки...
.venv\Scripts\pip.exe install -q -U -r requirements.txt

echo [3/3] Проверяю браузер для авторизации...
.venv\Scripts\hh-applicant-tool.exe install

echo.
echo ============================================
echo  Готово! Запускай dashboard.cmd
echo ============================================
pause
