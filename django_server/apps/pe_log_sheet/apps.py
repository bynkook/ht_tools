from django.apps import AppConfig
from importlib import import_module
from typing import override


class PeLogSheetConfig(AppConfig):
    name = "apps.pe_log_sheet"
    verbose_name = "PE Log Sheet"

    @override
    def ready(self):
        scheduler_module = import_module("apps.pe_log_sheet.scheduler")
        scheduler_module.start_pe_log_sheet_daily_export_scheduler()
