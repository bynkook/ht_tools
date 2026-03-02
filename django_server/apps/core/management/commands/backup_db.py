"""
Django Management Command: backup_db
SQLite 데이터베이스를 타임스탬프와 함께 백업하는 수동 명령어

사용법:
    python manage.py backup_db              # 최근 7개 백업 유지
    python manage.py backup_db --keep=14    # 최근 14개 백업 유지
    python manage.py backup_db --no-cleanup # 자동 정리 안 함

보안:
    - Image Inspector 앱은 DB에 히스토리를 저장하지 않음
    - Chat 세션 데이터만 백업 대상
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from pathlib import Path
from datetime import datetime
import shutil


class Command(BaseCommand):
    help = 'Backup SQLite database with timestamp (Manual backup only)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep',
            type=int,
            default=7,
            help='Number of backup files to keep (default: 7)'
        )
        parser.add_argument(
            '--no-cleanup',
            action='store_true',
            help='Skip cleanup of old backups'
        )

    def handle(self, *args, **options):
        # 데이터베이스 경로 확인
        db_settings = settings.DATABASES.get('default', {})
        db_engine = db_settings.get('ENGINE', '')
        
        if 'sqlite' not in db_engine:
            self.stdout.write(self.style.ERROR('❌ This command only works with SQLite databases'))
            return
        
        db_path = Path(db_settings.get('NAME'))
        if not db_path.exists():
            self.stdout.write(self.style.ERROR(f'❌ Database file not found: {db_path}'))
            return
        
        # 백업 디렉토리 생성
        backup_dir = Path(settings.BASE_DIR) / 'backups'
        backup_dir.mkdir(exist_ok=True)
        
        # 타임스탬프 생성
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'db_backup_{timestamp}.sqlite3'
        backup_path = backup_dir / backup_filename
        
        try:
            # 데이터베이스 복사
            self.stdout.write(f'📦 Creating backup: {backup_filename}')
            shutil.copy2(db_path, backup_path)
            
            # WAL 파일도 백업 (존재하는 경우)
            wal_path = Path(str(db_path) + '-wal')
            if wal_path.exists():
                wal_backup = backup_dir / f'db_backup_{timestamp}.sqlite3-wal'
                shutil.copy2(wal_path, wal_backup)
                self.stdout.write(f'   WAL file backed up')
            
            # SHM 파일도 백업 (존재하는 경우)
            shm_path = Path(str(db_path) + '-shm')
            if shm_path.exists():
                shm_backup = backup_dir / f'db_backup_{timestamp}.sqlite3-shm'
                shutil.copy2(shm_path, shm_backup)
                self.stdout.write(f'   SHM file backed up')
            
            backup_size = backup_path.stat().st_size / (1024 * 1024)
            self.stdout.write(self.style.SUCCESS(
                f'✅ Backup created: {backup_path}\n'
                f'   Size: {backup_size:.2f} MB'
            ))
            
            # 오래된 백업 정리 (--no-cleanup이 없는 경우)
            if not options['no_cleanup']:
                keep_count = options['keep']
                backups = sorted(backup_dir.glob('db_backup_*.sqlite3'))
                
                if len(backups) > keep_count:
                    self.stdout.write(f'\n🗑️  Cleaning up old backups (keeping recent {keep_count})...')
                    for old_backup in backups[:-keep_count]:
                        old_backup.unlink()
                        # WAL/SHM 파일도 삭제
                        for suffix in ['-wal', '-shm']:
                            old_extra = Path(str(old_backup) + suffix)
                            if old_extra.exists():
                                old_extra.unlink()
                        self.stdout.write(f'   Deleted: {old_backup.name}')
                    
                    remaining = len(list(backup_dir.glob('db_backup_*.sqlite3')))
                    self.stdout.write(self.style.SUCCESS(
                        f'✅ Cleanup complete. {remaining} backups remaining.'
                    ))
            
            self.stdout.write(self.style.SUCCESS('\n✅ Database backup completed successfully!'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Backup failed: {str(e)}'))
            raise
