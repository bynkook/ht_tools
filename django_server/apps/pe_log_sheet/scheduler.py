from datetime import date, datetime
import threading
import time
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from django.utils import timezone
from .services.daily_export import export_pe_log_sheet_to_data_explorer
import logging

logger = logging.getLogger(__name__)

_FORBIDDEN_COMMANDS = {"test", "migrate", "makemigrations", "shell"}
_MANUAL_EXPORT_COMMANDS = {
    "sync_pe_log_sheet_from_csv",
    "export_pe_log_sheet_to_data_explorer",
}

_scheduler_started = False
_scheduler_lock = threading.Lock()
_last_attempted_date: date | None = None


def _normalize_argv(argv: Sequence[object]) -> list[str]:
    normalized: list[str] = []

    for arg in argv:
        if arg is None:
            continue

        token = str(arg).strip()
        if not token:
            continue

        normalized.append(Path(token).name.lower())

    return normalized


def should_start_pe_log_sheet_scheduler(argv: Sequence[object]) -> bool:
    """Return True only for explicit manage.py runserver startup contexts."""

    tokens = _normalize_argv(argv)
    if not tokens:
        return False

    if "manage.py" not in tokens:
        return False

    if "runserver" not in tokens:
        return False

    if any(token in _FORBIDDEN_COMMANDS for token in tokens):
        return False

    if any(token in _MANUAL_EXPORT_COMMANDS for token in tokens):
        return False

    return True


def is_daily_export_due(now: datetime, last_attempted_date: date | None) -> bool:
    """Return True only during the local 12:00 minute and once per local date."""

    local_now = cast(datetime, timezone.localtime(now))
    current_date = local_now.date()

    if last_attempted_date == current_date:
        return False

    return local_now.hour == 12 and local_now.minute == 0


def _run_scheduler_iteration(
    now: datetime, last_attempted_date: date | None
) -> tuple[bool, date | None]:
    """Run one iteration of the scheduler, returning (did_export, new_last_attempted_date)."""
    if is_daily_export_due(now, last_attempted_date):
        new_last_attempted_date = now.date()
        logger.info(f"Starting daily export for {now.date()}")
        try:
            _ = export_pe_log_sheet_to_data_explorer()
            logger.info("Daily export completed successfully.")
        except Exception as e:
            logger.error(f"Daily export failed: {e}")
        return True, new_last_attempted_date
    return False, last_attempted_date


def _scheduler_loop():
    global _last_attempted_date
    logger.info("PE Log Sheet daily export scheduler started.")
    while True:
        try:
            now = timezone.localtime(timezone.now())
            did_export, new_last_attempted_date = _run_scheduler_iteration(
                now, _last_attempted_date
            )
            _last_attempted_date = new_last_attempted_date
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")
        time.sleep(10)


def start_pe_log_sheet_daily_export_scheduler():
    global _scheduler_started
    if not should_start_pe_log_sheet_scheduler(sys.argv):
        return

    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
        thread = threading.Thread(target=_scheduler_loop, daemon=True)
        thread.start()
        logger.info("PE Log Sheet daily export scheduler thread launched.")
