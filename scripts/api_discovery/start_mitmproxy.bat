@echo off
REM Start mitmproxy web interface for API interception

echo ========================================
echo Starting mitmproxy Web Interface
echo ========================================
echo.
echo Web UI will be available at: http://localhost:8081
echo Proxy listening on: 0.0.0.0:8080
echo.
echo Configure your Android emulator proxy:
echo   Settings > Network > Wi-Fi > (long press connected network)
echo   Modify network > Advanced > Proxy > Manual
echo   Hostname: 10.0.2.2 (or your PC's IP)
echo   Port: 8080
echo.
echo To install CA certificate on Android:
echo   1. Open browser on emulator
echo   2. Go to: http://mitm.it
echo   3. Download Android certificate
echo   4. Install from Settings > Security
echo.
echo Press Ctrl+C to stop
echo ========================================
echo.

python -m mitmproxy.tools.web --listen-port 8080 --web-port 8081
