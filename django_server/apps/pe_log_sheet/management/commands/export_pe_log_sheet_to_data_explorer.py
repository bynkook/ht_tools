from django.core.management.base import BaseCommand, CommandError

from ...services.daily_export import export_pe_log_sheet_to_data_explorer


class Command(BaseCommand):
    help = "Export the PE log sheet workbook to the Data Explorer directory."

    def handle(self, *args, **options):
        try:
            export_path = export_pe_log_sheet_to_data_explorer()
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(str(export_path))
