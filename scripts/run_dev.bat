@echo off
setlocal

REM Resolve repository root (parent directory of this script)
pushd "%~dp0\.." >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Unable to locate repository root from %~dp0
    pause
    exit /b 1
)
set "REPO_ROOT=%CD%"

echo ===============================
echo [INFO] Repository root: %REPO_ROOT%
echo ===============================

echo [INFO] Ensuring API auth token (.env + frontend/.env)...
python scripts\set_api_token.py || goto :error

echo [INFO] Preparing Python virtual environment...
if not exist "%REPO_ROOT%\.venv\Scripts\activate.bat" (
    echo [INFO] Creating .venv ...
    python -m venv .venv || goto :error
)

call "%REPO_ROOT%\.venv\Scripts\activate.bat" || goto :error

echo [INFO] Installing backend dependencies (pip install -r requirements.txt)
pip install -r requirements.txt || goto :error

echo [INFO] Starting backend server window...
start "RAG Backend" cmd /k "cd /d %REPO_ROOT% && call .venv\Scripts\activate.bat && python -m src.cli --config configs/dev.yaml serve --reload"

echo [INFO] Preparing frontend workspace...
if not exist "%REPO_ROOT%\frontend\node_modules" (
    pushd "%REPO_ROOT%\frontend" >nul && npm install || goto :error
    popd >nul
) else (
    echo [INFO] frontend/node_modules detected, skipping npm install.
)

echo [INFO] Starting frontend dev server window...
start "RAG Frontend" cmd /k "cd /d %REPO_ROOT%\frontend && npm run dev"

echo.
echo [INFO] Backend and frontend are launching in dedicated terminals.
echo       Close those windows to stop the services.
echo.
pause
popd >nul
exit /b 0

:error
echo.
echo [ERROR] Setup failed. Review the logs above for details.
pause
popd >nul
exit /b 1
