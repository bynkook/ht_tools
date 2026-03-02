@echo off
chcp 65001 > nul
setlocal

echo ========================================================
echo   통합 설치 마법사
echo ========================================================
echo.

REM 1. Python 가상환경 점검 및 생성
if not exist .venv (
    echo [1/3] Python 가상환경 생성 중...
    python -m venv .venv
) else (
    echo [1/3] 기존 가상환경을 감지했습니다.
)

REM 2. Backend 라이브러리 설치
echo.
echo [2/3] Backend 라이브러리 설치 (pip)...
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

REM 3. Frontend 라이브러리 설치 (package.json)
echo.
echo [3/3] Frontend 라이브러리 설치 (npm)...
cd frontend
if not exist node_modules (
    echo Installing React 19 and all dependencies...    
    call npm install
) else (
    echo node_modules가 이미 존재합니다. 추가 설치는 'npm install'을 직접 실행하세요.
)
cd ..

echo.
echo ========================================================
echo   설치가 완료되었습니다!
echo   다음 단계로 'reset_create_admin.bat'를 실행하여 DB를 초기화하세요.
echo ========================================================
pause