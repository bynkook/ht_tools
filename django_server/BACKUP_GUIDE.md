# SQLite Database Backup Guide

## 수동 백업 명령어

### 기본 사용법
```bash
# 최근 7개 백업 유지 (기본)
python manage.py backup_db

# 최근 30개 백업 유지
python manage.py backup_db --keep=30

# 자동 정리 없이 백업만
python manage.py backup_db --no-cleanup
```

## 백업 파일 위치
```
django_server/
├── db.sqlite3              # 현재 활성 DB
└── backups/                # 백업 저장 폴더
    ├── db_backup_20260202_143052.sqlite3
    ├── db_backup_20260202_120000.sqlite3
    └── ...
```

## 복구 방법

### 1단계: 백업 파일 확인
```bash
cd django_server/backups
dir db_backup_*.sqlite3
```

### 2단계: 현재 DB 백업 (안전장치)
```bash
cd ..
copy db.sqlite3 db.sqlite3.before_restore
```

### 3단계: 백업 파일로 복구
```bash
# 원하는 백업 파일을 db.sqlite3로 복사
copy backups\db_backup_20260202_143052.sqlite3 db.sqlite3
```

### 4단계: 서버 재시작
```bash
# Django 개발 서버 재시작
python manage.py runserver
```

## 백업 시나리오

### 중요 작업 전 백업
```bash
# 예: 대량 데이터 삭제 전
python manage.py backup_db
# 작업 수행
python manage.py shell
```

### 배포 전 백업
```bash
python manage.py backup_db --keep=30
git push origin main
```

### 마이그레이션 전 백업
```bash
python manage.py backup_db
python manage.py migrate
```

## 보안 정책

- **Image Inspector**: DB에 히스토리를 저장하지 않음 (보안상 안전)
- **Chat 앱**: ChatSession과 ChatMessage만 백업 대상
- **백업 파일**: 민감한 데이터 포함 가능, Git에서 제외됨

## 주의사항

1. 백업은 **수동**으로만 실행 (자동화 없음)
2. 중요한 작업 전에는 반드시 백업 실행
3. 백업 폴더는 Git에서 제외됨 (`.gitignore` 설정됨)
4. 정기적으로 오래된 백업 수동 삭제 권장
