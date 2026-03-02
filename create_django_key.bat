@echo off
chcp 65001 > nul
setlocal

echo ========================================================
echo   Django Secret Key 생성기
echo ========================================================
echo.

REM 1. 가상환경 확인
if not exist .venv (
    echo [Error] 가상환경이 없습니다. 'setup_project.bat'를 먼저 실행하세요.
    pause
    exit /b
)
call .venv\Scripts\activate

REM 2. 키 생성 및 출력
echo.
echo 아래 생성된 키를 복사하세요.
echo ------------------------------------------------------------
cd django_server
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
cd ..
echo ------------------------------------------------------------
echo.
echo [사용 방법]
echo 1. 위 문자열을 복사합니다.
echo 2. 프로젝트 폴더의 'secrets.toml' 파일을 엽니다.
echo 3. [django] 섹션의 secret_key = "..." 따옴표 안에 붙여넣고 저장하세요.
echo.
pause