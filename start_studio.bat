@echo off
REM Clinic Studio runner: launches the FastAPI backend and Next.js frontend
REM each in their own non-blocking window, bound to 0.0.0.0 for LAN/mobile access.
setlocal
cd /d "%~dp0"

echo Starting Clinic Studio backend (FastAPI/uvicorn) on http://0.0.0.0:8000 ...
start "Clinic Studio - Backend" cmd /k "cd /d "%~dp0" && backend\venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

echo Starting Clinic Studio frontend (Next.js) on http://0.0.0.0:3000 ...
start "Clinic Studio - Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev -- -H 0.0.0.0 -p 3000"

echo.
echo Detecting local network IP for mobile access...
powershell -NoProfile -Command "$candidates = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.PrefixOrigin -eq 'Dhcp' -and $_.IPAddress -notlike '169.254.*' }; $ip = ($candidates | Where-Object { $_.InterfaceAlias -match 'Wi-?Fi' } | Select-Object -First 1 -ExpandProperty IPAddress); if (-not $ip) { $ip = ($candidates | Select-Object -First 1 -ExpandProperty IPAddress) }; if (-not $ip) { $ip = 'YOUR-PC-IP' }; Write-Host ''; Write-Host ('On your iPhone (same Wi-Fi), open Safari and go to: http://' + $ip + ':3000') -ForegroundColor Cyan"

echo.
echo Both services are launching in separate windows. Close those windows to stop them.
endlocal
