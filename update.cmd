@echo off

rem The script copies itself to TEMP and runs from there,
rem so it can safely overwrite everything, including update.cmd itself.
if /i not "%~dp0"=="%TEMP%\" (
    copy /y "%~f0" "%TEMP%\hh_dashboard_update.cmd" >nul
    "%TEMP%\hh_dashboard_update.cmd" "%~dp0"
    exit /b
)

cd /d "%~1"
echo ============================================
echo  HH Dashboard update
echo ============================================
echo.
echo [1/3] Downloading the latest version from GitHub...
powershell -NoProfile -Command "Invoke-WebRequest 'https://codeload.github.com/spacejackpro/hh-dashboard/zip/refs/heads/main' -OutFile (Join-Path $env:TEMP 'hhdash.zip')"
if errorlevel 1 (
    echo Download failed. Check your internet and try again.
    pause
    exit /b 1
)

powershell -NoProfile -Command "Remove-Item -Recurse -Force (Join-Path $env:TEMP 'hhdash') -ErrorAction SilentlyContinue; Expand-Archive -Force (Join-Path $env:TEMP 'hhdash.zip') (Join-Path $env:TEMP 'hhdash')"
xcopy /E /Y /Q "%TEMP%\hhdash\hh-dashboard-main\*" . >nul
echo        Code updated.

echo [2/3] Upgrading the hh-applicant-tool engine and libraries...
.venv\Scripts\pip.exe install -q -U -r requirements.txt

echo [3/3] Checking browser for hh.ru login...
.venv\Scripts\hh-applicant-tool.exe install

echo.
echo ============================================
echo  Done! Start dashboard.cmd
echo ============================================
pause
