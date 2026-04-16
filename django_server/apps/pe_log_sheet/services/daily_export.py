"""Shared PE log sheet export service."""

# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import os
import tempfile
from pathlib import Path

from django.conf import settings

from ..models import PeLogSheetState
from .csv_loader import is_workbook_schema_valid, workbook_to_csv_bytes


def get_data_explorer_export_dir() -> Path:
    return settings.BASE_DIR.parent / "data" / "data_explorer"


def build_pe_log_sheet_filename() -> str:
    return "PE_LOG_SHEET.csv"


def build_pe_log_sheet_export_path() -> Path:
    return get_data_explorer_export_dir() / build_pe_log_sheet_filename()


def get_main_pe_log_sheet_state() -> PeLogSheetState:
    try:
        return PeLogSheetState.objects.get(singleton_key="main")
    except PeLogSheetState.DoesNotExist as exc:
        raise PeLogSheetState.DoesNotExist(
            "PE log sheet main state does not exist."
        ) from exc


def _write_bytes_atomically(target_path: Path, content: bytes) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=str(target_path.parent),
            prefix=f".{target_path.stem}.",
            suffix=".tmp",
        ) as temp_file:
            temp_file_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_file_path, target_path)
    except Exception:
        if temp_file_path is not None and temp_file_path.exists():
            temp_file_path.unlink(missing_ok=True)
        raise


def export_pe_log_sheet_to_data_explorer() -> Path:
    state = get_main_pe_log_sheet_state()
    workbook_data = state.workbook_data

    if not is_workbook_schema_valid(workbook_data):
        raise ValueError("PE log sheet workbook is missing, empty, or invalid.")

    csv_bytes = workbook_to_csv_bytes(workbook_data)
    export_path = build_pe_log_sheet_export_path()
    _write_bytes_atomically(export_path, csv_bytes)
    return export_path
