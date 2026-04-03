@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set SCRIPT_DIR=%~dp0
pushd "%SCRIPT_DIR%"

echo ========================================================
echo   [DEV] Dashboard 기능 제거 - 개발 환경
echo   - makemigrations (0005 생성)
echo   - migrate (DB 테이블 DROP)
echo   - npm uninstall MUI/Emotion
echo ========================================================
echo.

REM 가상환경 확인
if not exist ".venv\Scripts\python.exe" (
    echo [오류] 가상환경 .venv 가 없습니다. setup_project.bat 을 먼저 실행하세요.
    goto :error
)

REM Django manage.py 확인
if not exist "django_server\manage.py" (
    echo [오류] django_server\manage.py 파일을 찾을 수 없습니다.
    goto :error
)

REM --- Step 1: makemigrations ---
echo [1/4] makemigrations fabrix_chat ...
.venv\Scripts\python.exe django_server\manage.py makemigrations fabrix_chat
if errorlevel 1 (
    echo [오류] makemigrations 실패
    goto :error
)

REM --- Step 2: migrate ---
echo.
echo [2/4] migrate (fabrix_chat_dashboardlink 테이블 DROP) ...
.venv\Scripts\python.exe django_server\manage.py migrate
if errorlevel 1 (
    echo [오류] migrate 실패
    goto :error
)

REM --- Step 3: Django check ---
echo.
echo [3/4] Django 시스템 검증 ...
.venv\Scripts\python.exe django_server\manage.py check
if errorlevel 1 (
    echo [경고] 시스템 검증에서 문제가 발견되었습니다.
    goto :error
)

REM --- Step 4: npm uninstall ---
echo.
echo [4/4] npm uninstall @mui/material @emotion/react @emotion/styled ...
if not exist "frontend\package.json" (
    echo [경고] frontend\package.json 을 찾을 수 없습니다. npm 단계를 건너뜁니다.
    goto :done
)
cd frontend
npm uninstall @mui/material @emotion/react @emotion/styled --legacy-peer-deps
if errorlevel 1 (
    echo [오류] npm uninstall 실패
    cd ..
    goto :error
)
cd ..

:done
echo.
echo ========================================================
echo   완료!
echo   생성된 마이그레이션 파일을 git commit 에 반드시 포함하세요.
echo   운영 서버 배포 후 remove_dashboard_prod.bat 을 실행하세요.
echo ========================================================
goto :end

:error
echo.
echo ========================================================
echo   작업 실패. 위의 오류 메시지를 확인하세요.
echo ========================================================

:end
popd
pause
