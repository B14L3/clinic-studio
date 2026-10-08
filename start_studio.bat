@echo off
REM Clinic Studio runner: launches the FastAPI backend and Next.js frontend
REM each in their own non-blocking window.
setlocal
cd /d "%~dp0"

echo Starting Clinic Studio backend (FastAPI/uvicorn) on http://127.0.0.1:8000 ...
start "Clinic Studio - Backend" cmd /k "cd /d "%~dp0" && backend\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload"

echo Starting Clinic Studio frontend (Next.js) on http://localhost:3000 ...
start "Clinic Studio - Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo Both services are launching in separate windows. Close those windows to stop them.
endlocal
