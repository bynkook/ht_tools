from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings
import os

from apps.pe_log_sheet.models import PeLogSheetState
from apps.pe_log_sheet.services.csv_loader import csv_to_workbook, compute_csv_checksum


class Command(BaseCommand):
    help = 'Re-initialise PE Log Sheet from the canonical CSV source.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-initialise even if checksum has not changed.',
        )

    def handle(self, *args, **options):
        csv_path = os.path.normpath(
            os.path.join(settings.BASE_DIR, '..', 'data', 'pe_log', 'pe_log.csv')
        )

        if not os.path.exists(csv_path):
            self.stderr.write(self.style.ERROR(f'CSV not found: {csv_path}'))
            return

        new_checksum = compute_csv_checksum(csv_path)

        state, created = PeLogSheetState.objects.get_or_create(singleton_key='main')

        if not options['force'] and state.source_checksum == new_checksum and state.workbook_data:
            self.stdout.write(self.style.WARNING('Checksum unchanged. Use --force to re-initialise.'))
            return

        state.workbook_data = csv_to_workbook(csv_path)
        state.revision = state.revision + 1 if not created else 0
        state.source_checksum = new_checksum
        state.save()

        self.stdout.write(self.style.SUCCESS(
            f'PE Log Sheet initialised from {csv_path} (revision={state.revision})'
        ))
