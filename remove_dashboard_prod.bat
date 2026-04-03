@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set SCRIPT_DIR=%~dp0
pushd "%SCRIPT_DIR%"

echo ========================================================
echo   [PROD] Dashboard 기능 제거 - 운영 서버
echo   - npm uninstall MUI/Emotion
echo   - migrate_db.bat 호출 (DB 백업 + 0005 마이그레이션 적용)
echo ========================================================
echo.
echo   주의: 코드 배포 (git pull 등) 완료 후 실행하세요.
echo         0005_remove_dashboardlink 마이그레이션 파일이
echo         반드시 코드에 포함되어 있어야 합니다.
echo.

REM 마이그레이션 파일 존재 확인
set MIGRATION_FILE=django_server\apps\fabrix_chat\migrations\0005_remove_dashboardlink_fabrix_chat_display_1f8c7d_idx_and_more.py
if not exist "%MIGRATION_FILE%" (
    echo [오류] 마이그레이션 파일을 찾을 수 없습니다:
    echo        %MIGRATION_FILE%
    echo        개발 환경에서 remove_dashboard_dev.bat 실행 후 커밋했는지 확인하세요.
    goto :error
)

REM --- Step 1: npm uninstall ---
echo [1/2] npm uninstall @mui/material @emotion/react @emotion/styled ...
if not exist "frontend\package.json" (
    echo [경고] frontend\package.json 을 찾을 수 없습니다. npm 단계를 건너뜁니다.
    goto :migrate
)
cd frontend
npm uninstall @mui/material @emotion/react @emotion/styled --legacy-peer-deps
if errorlevel 1 (
    echo [오류] npm uninstall 실패
    cd ..
    goto :error
)
cd ..

:migrate
REM --- Step 2: migrate_db.bat (DB 백업 + migrate 적용) ---
echo.
echo [2/2] migrate_db.bat 실행 (운영 DB 백업 + 0005 마이그레이션 적용) ...
if not exist "migrate_db.bat" (
    echo [오류] migrate_db.bat 을 찾을 수 없습니다.
    goto :error
)
call migrate_db.bat
if errorlevel 1 (
    echo [오류] migrate_db.bat 실패
    goto :error
)

echo.
echo ========================================================
echo   완료! 운영 서버 DB 의 fabrix_chat_dashboardlink
echo   테이블이 제거되었습니다.
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
