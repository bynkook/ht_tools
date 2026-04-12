@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%~f0"
set "DJANGO_DIR=%SCRIPT_DIR%django_server"
set "FRONTEND_DIR=%SCRIPT_DIR%frontend"
set "FASTMCP_DIR=%SCRIPT_DIR%..\fastmcp"
set "LEXGUARD_DIR=%SCRIPT_DIR%..\lexguard-mcp"
set "LAUNCHER_TITLE=FabriX Service Launcher"
set "WT_WINDOW_NAME=FabriXService"
set "USE_WINDOWS_TERMINAL=0"

cd /d "%SCRIPT_DIR%"

if /I "%~1"=="--role" goto role
if /I "%~1"=="--wt-child" goto launcher

REM 1. 새 Windows Terminal 윈도우로 재실행 (명명된 창)
where wt.exe >nul 2>&1
if not errorlevel 1 (
    wt.exe -w %WT_WINDOW_NAME% new-tab --title "%LAUNCHER_TITLE%" cmd.exe /k call "%SCRIPT_PATH%" --wt-child
    exit /b %errorlevel%
)

goto launcher

:launcher

where wt.exe >nul 2>&1
if not errorlevel 1 (
    set "USE_WINDOWS_TERMINAL=1"
)

echo ========================================================
echo   [FabriX Agent Chat] 사내망 서비스 모드 실행 (0.0.0.0)
echo   주의: 방화벽 경고 시 '액세스 허용'을 반드시 눌러주세요.
echo ========================================================
echo.

REM 2. 가상환경 확인
if not exist ".venv" (
    echo [Error] 가상환경이 없습니다. 'setup_project.bat'를 먼저 실행하세요.
    pause
    exit /b 1
)

REM 3. 데이터베이스 확인
if not exist "django_server\db.sqlite3" (
    echo [Warning] 데이터베이스가 없습니다!
    echo           'reset_create_admin.bat'를 먼저 실행하여 DB를 생성하세요.
    echo           이 단계를 건너뛰면 브라우저에 흰 화면만 표시됩니다.
    echo.
    pause
    exit /b 1
)

REM 4. Django Server (Port 8000 - Public)
echo [1/5] Django 서버 개방 (0.0.0.0:8000)...
call :launch_role "Django Service" django

REM 5. FastAPI Gateway (Port 8001 - Public)
echo [2/5] AI 게이트웨이 개방 (0.0.0.0:8001)...
call :launch_role "FastAPI Service" fastapi

REM 6. React Frontend (Port 5173 - Public)
echo [3/5] React 클라이언트 개방 (0.0.0.0:5173)...
call :launch_role "React Service" react

REM 7. FastMCP Doc Server (Port 8002 - Localhost only)
echo [4/5] FastMCP Doc 서버 시작 (127.0.0.1:8002)...
call :launch_role "FastMCP Doc Server" fastmcp

REM 8. LexGuard MCP Server (Port 9099 - Localhost only)
echo [5/5] LexGuard MCP 서버 시작 (127.0.0.1:9099)...
call :launch_role "LexGuard MCP" lexguard

echo.
echo ========================================================
echo   서비스가 시작되었습니다!
echo.
echo   [접속 방법]
echo   1. 본인 PC에서 확인: http://localhost:5173
echo   2. 동료에게 공유 시: http://내IP주소:5173 공유
echo.
echo   [앱 접속 주소]
echo   * Chat 앱:            http://localhost:5173/chat
echo   * Image Inspector:    http://localhost:5173/image-compare
echo   * Data Explorer 앱:   http://localhost:5173/data-explorer
echo   * 앱 선택화면:         http://localhost:5173
echo.
echo   [MCP 서버]
echo   * FastMCP Doc:        http://127.0.0.1:8002/mcp
echo   * LexGuard MCP:       http://127.0.0.1:9099/mcp
echo ========================================================
pause
exit /b 0

:launch_role
set "TAB_TITLE=%~1"
set "SERVICE_ROLE=%~2"
if "%USE_WINDOWS_TERMINAL%"=="1" (
    wt.exe -w %WT_WINDOW_NAME% new-tab --title "%TAB_TITLE%" cmd.exe /k call "%SCRIPT_PATH%" --role %SERVICE_ROLE%
) else (
    start "%TAB_TITLE%" cmd.exe /k call "%SCRIPT_PATH%" --role %SERVICE_ROLE%
)
exit /b %errorlevel%

:role
set "SERVICE_ROLE=%~2"
if /I "%SERVICE_ROLE%"=="django"   goto run_django
if /I "%SERVICE_ROLE%"=="fastapi"  goto run_fastapi
if /I "%SERVICE_ROLE%"=="react"    goto run_react
if /I "%SERVICE_ROLE%"=="fastmcp"  goto run_fastmcp
if /I "%SERVICE_ROLE%"=="lexguard" goto run_lexguard
echo [Error] 알 수 없는 서비스 역할입니다: %SERVICE_ROLE%
exit /b 1

:run_django
call ".venv\Scripts\activate.bat"
pushd "%DJANGO_DIR%"
python manage.py runserver 0.0.0.0:8000 --noreload
popd
exit /b %errorlevel%

:run_fastapi
call ".venv\Scripts\activate.bat"
cd /d "%SCRIPT_DIR%"
uvicorn ai_gateway.main:app --host 0.0.0.0 --port 8001
exit /b %errorlevel%

:run_react
if not exist "%FRONTEND_DIR%\package.json" (
    echo [Error] frontend 경로에서 package.json 을 찾을 수 없습니다: %FRONTEND_DIR%
    exit /b 1
)
pushd "%FRONTEND_DIR%"
call npm.cmd run dev -- --host 0.0.0.0
popd
exit /b %errorlevel%

:run_fastmcp
if not exist "%FASTMCP_DIR%\run_server.bat" (
    echo [Error] FastMCP 서버 스크립트를 찾을 수 없습니다: %FASTMCP_DIR%\run_server.bat
    exit /b 1
)
call "%FASTMCP_DIR%\run_server.bat" --serve
exit /b %errorlevel%

:run_lexguard
if not exist "%LEXGUARD_DIR%\run_lexguard.bat" (
    echo [Error] LexGuard 서버 스크립트를 찾을 수 없습니다: %LEXGUARD_DIR%\run_lexguard.bat
    exit /b 1
)
call "%LEXGUARD_DIR%\run_lexguard.bat"
exit /b %errorlevel%
