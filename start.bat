@echo off
chcp 65001 >nul 2>&1

echo.
echo ========================================
echo   AI Presentation Agent - Docker Start
echo ========================================
echo.

cd /d "%~dp0"

REM Check if .env file exists
if not exist .env (
    echo [INFO] Creating .env file from template...
    copy .env.example .env >nul
    echo.
    echo [NOTICE] Please edit .env file and add your OPENAI_API_KEY
    echo          Then run this script again.
    echo.
    pause
    exit /b 1
)

REM Simple docker check - just try to run a command
echo [INFO] Checking Docker...
docker ps >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Cannot connect to Docker. Please make sure Docker Desktop is running.
    echo.
    pause
    exit /b 1
)
echo [OK] Docker is available
echo.

REM Build images
echo [INFO] Building Docker images...
echo        This may take several minutes on first run...
echo.
docker compose build
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo [INFO] Starting services...
docker compose up -d
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start services!
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Services started successfully!
echo ========================================
echo.
echo Access points:
echo   Frontend:    http://localhost:3000
echo   Backend API: http://localhost:8000
echo   API Docs:    http://localhost:8000/docs
echo.
echo Commands:
echo   View logs: docker compose logs -f
echo   Stop:      docker compose down
echo   Restart:   docker compose restart
echo.

pause