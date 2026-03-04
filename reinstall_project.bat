@echo off
chcp 65001 > nul
setlocal

set SCRIPT_DIR=%~dp0
pushd "%SCRIPT_DIR%"

echo ========================================================
echo   의존성 재설치 및 프론트엔드 빌드
echo   (파일 업데이트 후 서버 배포 시 실행)
echo ========================================================
echo.

REM 가상환경 확인
if not exist ".venv\Scripts\activate.bat" goto :no_venv

REM 가상환경 활성화
echo [1/4] Activate venv...
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :activate_error

REM Backend 패키지 업데이트
REM requirements.txt 변경 여부와 무관하게 항상 실행하여 누락 패키지를 보완
echo.
echo [2/4] Backend 패키지 설치 (pip)...
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if errorlevel 1 goto :pip_error

REM Frontend 패키지 설치 및 빌드
REM package.json 변경 여부와 무관하게 npm install 을 항상 실행
REM (npm install 은 이미 설치된 패키지는 건너뛰므로 반복 실행에도 안전)
echo.
echo [3/4] Frontend 패키지 설치 및 빌드...
if not exist "frontend\package.json" goto :no_frontend

cd frontend

echo [4/4] npm install (누락 패키지 보완)...
call npm install
if errorlevel 1 goto :npm_install_error

cd ..

echo.
echo ========================================================
echo   재설치 및 빌드가 완료되었습니다!
echo.
echo   다음 단계:
echo     - DB 스키마 변경이 있는 경우: migrate_db.bat 실행
echo     - 변경 없는 경우            : run_project.bat 으로 서버 시작
echo ========================================================
goto :end

:no_venv
echo [오류] 가상환경 .venv 폴더가 존재하지 않습니다.
echo        먼저 setup_project.bat 을 실행하세요.
goto :error

:activate_error
echo [오류] 가상환경 활성화에 실패했습니다.
goto :error

:pip_error
echo [오류] Backend 패키지 설치에 실패했습니다.
goto :error

:no_frontend
echo [오류] frontend\package.json 을 찾을 수 없습니다.
echo        프로젝트 루트에서 스크립트를 실행했는지 확인하세요.
goto :error

:npm_install_error
echo [오류] npm install 에 실패했습니다.
goto :error

:npm_build_error
echo [오류] npm run build 에 실패했습니다.
goto :error

:error
echo.
echo ========================================================
echo   재설치 실패. 위의 오류 메시지를 확인하세요.
echo ========================================================

:end
popd
pause
