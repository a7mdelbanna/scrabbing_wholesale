@echo off
REM Intercept app traffic with Frida SSL pinning bypass

SET SCRIPTS_PATH=C:\Users\ahmed\AppData\Roaming\Python\Python313\Scripts

if "%1"=="" (
    echo Usage: intercept_app.bat ^<package_name^>
    echo.
    echo Example package names:
    echo   - Tager elSaada: Find by running: frida-ps -Ua
    echo   - Ben Soliman: Find by running: frida-ps -Ua
    echo.
    echo First, list installed apps:
    echo   %SCRIPTS_PATH%\frida-ps.exe -Ua
    echo.
    pause
    exit /b 1
)

echo ========================================
echo Intercepting: %1
echo ========================================
echo.
echo Make sure:
echo   1. mitmproxy is running (run start_mitmproxy.bat)
echo   2. Emulator proxy is configured
echo   3. App is installed on emulator
echo.

echo Starting Frida with SSL bypass...
%SCRIPTS_PATH%\frida.exe -U -f %1 -l frida-ssl-bypass.js --no-pause

echo.
echo If the app crashed, try:
echo   frida -U %1 -l frida-ssl-bypass.js
echo   (attach to already running app)
