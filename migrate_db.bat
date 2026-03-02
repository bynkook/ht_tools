@echo off
chcp 65001 > nul
setlocal

set SCRIPT_DIR=%~dp0
pushd "%SCRIPT_DIR%"

echo ========================================================
echo   [Applications] 데이터베이스 마이그레이션
echo ========================================================
echo.

REM 가상환경 확인
if not exist ".venv\Scripts\activate.bat" goto :no_venv

REM 가상환경 활성화
echo [1/5] Activate venv...
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :activate_error

REM 프로젝트 구조 확인
if not exist "django_server\manage.py" goto :no_manage

REM Django 서버 디렉토리로 이동
cd /d django_server

REM SQLite 자동 백업 (기존 DB 보존)
echo.
echo [2/5] SQLite DB 자동 백업 중...
if exist "db.sqlite3" (
	python manage.py backup_db --no-cleanup
	if errorlevel 1 goto :backup_error
	echo        backup_db 명령으로 SQLite 백업을 완료했습니다.
) else (
	echo        db.sqlite3 파일이 없어 백업을 건너뜁니다. (최초 배포 가능)
)

REM 서버 안전 점검 (운영 서버에서는 migration 파일 생성 금지)
echo.
echo [3/5] 모델 변경-마이그레이션 정합성 확인 중...
python manage.py makemigrations --check --dry-run
if errorlevel 1 goto :pending_model_changes

REM 마이그레이션 적용 (기존 SQLite DB 유지)
echo.
echo [4/5] 데이터베이스 마이그레이션 적용 중...
python manage.py migrate --noinput
if errorlevel 1 goto :migrate_error

REM 시스템 체크
echo.
echo [5/5] Django 시스템 검증 중...
python manage.py check
if errorlevel 1 goto :check_error

echo.
echo ========================================================
echo   마이그레이션이 성공적으로 완료되었습니다!
echo   기존 SQLite DB 파일은 삭제하지 않고 유지됩니다.
echo   이제 run_project.bat 또는 service_project.bat으로
echo   서버를 시작할 수 있습니다.
echo ========================================================
goto :end

:no_manage
echo [오류] django_server\manage.py 파일을 찾을 수 없습니다.
echo        프로젝트 루트에서 스크립트를 실행했는지 확인하세요.
goto :error

:no_venv
echo [오류] 가상환경 .venv 폴더가 존재하지 않습니다.
echo        먼저 setup_project.bat을 실행하세요.
goto :error

:activate_error
echo [오류] 가상환경 활성화에 실패했습니다.
goto :error

:backup_error
echo [오류] SQLite 백업 파일 생성에 실패했습니다.
goto :error

:pending_model_changes
echo.
echo [오류] 모델 변경사항이 있으나 마이그레이션 파일이 없습니다.
echo        운영 서버에서는 makemigrations를 실행하지 않습니다.
echo        개발 환경에서 아래를 수행 후 다시 배포하세요.
echo          1) python manage.py makemigrations
echo          2) 생성된 migration 파일 커밋
echo          3) 서버에서 migrate_db.bat 재실행
goto :error

:migrate_error
echo.
echo [오류] 마이그레이션 중 오류가 발생했습니다.
goto :error

:check_error
echo.
echo [경고] 시스템 검증에서 문제가 발견되었습니다.
goto :error

:error
echo.
echo ========================================================
echo   마이그레이션 실패. 위의 오류 메시지를 확인하세요.
echo ========================================================

:end
popd
pause
