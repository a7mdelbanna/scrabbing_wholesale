@echo off
REM Frida Server Setup Script for Android Emulator
REM This script pushes frida-server to the emulator and starts it

SET ADB="C:\Users\ahmed\AppData\Local\Android\Sdk\platform-tools\adb.exe"
SET FRIDA_SERVER=frida-server

echo ========================================
echo Frida Server Setup for Android Emulator
echo ========================================
echo.

REM Check if emulator is running
echo Checking for connected devices...
%ADB% devices
echo.

REM Wait for device
echo Waiting for device...
%ADB% wait-for-device
echo Device connected!
echo.

REM Push frida-server to device
echo Pushing frida-server to /data/local/tmp/...
%ADB% push %FRIDA_SERVER% /data/local/tmp/frida-server
echo.

REM Make it executable and start
echo Setting permissions and starting frida-server...
%ADB% shell "chmod 755 /data/local/tmp/frida-server"
echo.

echo Starting frida-server (will run in background)...
%ADB% shell "/data/local/tmp/frida-server &"
echo.

REM Verify it's running
timeout /t 2 >nul
echo Verifying frida-server is running...
%ADB% shell "ps | grep frida"
echo.

echo ========================================
echo Frida server setup complete!
echo.
echo Next steps:
echo 1. Install the target app on the emulator
echo 2. Run: frida-ps -U (to verify Frida connection)
echo 3. Run: mitmweb --listen-port 8080
echo 4. Configure emulator proxy to your_ip:8080
echo ========================================
pause
