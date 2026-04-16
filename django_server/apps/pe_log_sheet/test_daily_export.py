"""Tests for PE log sheet daily export behavior."""

# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUninitializedInstanceVariable=false, reportUnannotatedClassAttribute=false

from datetime import date, datetime
from importlib import import_module
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model

from .models import PeLogSheetState
from .services.csv_loader import workbook_to_csv_bytes
from .services.daily_export import (
    build_pe_log_sheet_export_path,
    build_pe_log_sheet_filename,
    export_pe_log_sheet_to_data_explorer,
)

_scheduler = import_module("apps.pe_log_sheet.scheduler")
is_daily_export_due = _scheduler.is_daily_export_due
should_start_pe_log_sheet_scheduler = _scheduler.should_start_pe_log_sheet_scheduler
start_pe_log_sheet_daily_export_scheduler = (
    _scheduler.start_pe_log_sheet_daily_export_scheduler
)


User = get_user_model()


class PeLogSheetDailySchedulerTests(TestCase):
    def test_scheduler_starts_only_in_runserver_context(self):
        with patch(
            "apps.pe_log_sheet.scheduler.should_start_pe_log_sheet_scheduler",
            return_value=False,
        ):
            with patch("threading.Thread") as mock_thread:
                _scheduler._scheduler_started = False
                start_pe_log_sheet_daily_export_scheduler()
                mock_thread.assert_not_called()

    def test_scheduler_starts_in_runserver_context(self):
        with patch(
            "apps.pe_log_sheet.scheduler.should_start_pe_log_sheet_scheduler",
            return_value=True,
        ):
            with patch("threading.Thread") as mock_thread:
                _scheduler._scheduler_started = False
                start_pe_log_sheet_daily_export_scheduler()
                mock_thread.assert_called_once()
                _scheduler._scheduler_started = False

    def test_scheduler_single_start_guard(self):
        with patch(
            "apps.pe_log_sheet.scheduler.should_start_pe_log_sheet_scheduler",
            return_value=True,
        ):
            with patch("threading.Thread") as mock_thread:
                _scheduler._scheduler_started = False
                start_pe_log_sheet_daily_export_scheduler()
                start_pe_log_sheet_daily_export_scheduler()
                mock_thread.assert_called_once()
                _scheduler._scheduler_started = False

    def test_failed_noon_attempt_is_not_retried_same_day(self):
        # 1. Noon attempt fails
        now1 = datetime(2026, 4, 16, 12, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        last_attempted_date = None

        with patch(
            "apps.pe_log_sheet.scheduler.export_pe_log_sheet_to_data_explorer",
            side_effect=Exception("Fail"),
        ):
            did_export, new_last_attempted_date = _scheduler._run_scheduler_iteration(
                now1, last_attempted_date
            )

        self.assertTrue(did_export)
        self.assertEqual(new_last_attempted_date, now1.date())

        # 2. 12:00:10 attempt should not export
        now2 = datetime(2026, 4, 16, 12, 0, 10, tzinfo=ZoneInfo("Asia/Seoul"))
        did_export2, new_last_attempted_date2 = _scheduler._run_scheduler_iteration(
            now2, new_last_attempted_date
        )

        self.assertFalse(did_export2)
        self.assertEqual(new_last_attempted_date2, now1.date())


class PeLogSheetDailyExportPathTests(TestCase):
    def test_build_pe_log_sheet_filename_returns_fixed_name(self):
        self.assertEqual(build_pe_log_sheet_filename(), "PE_LOG_SHEET.csv")

    def test_build_export_path_targets_data_explorer_directory(self):
        export_path = build_pe_log_sheet_export_path()

        self.assertIn("data/data_explorer", str(export_path).replace("\\", "/"))
        self.assertEqual(export_path.name, "PE_LOG_SHEET.csv")


class PeLogSheetDailySchedulerDecisionTests(TestCase):
    def test_should_start_pe_log_sheet_scheduler_allows_runserver(self):
        self.assertTrue(
            should_start_pe_log_sheet_scheduler(
                [
                    r"C:\\project\\django_server\\manage.py",
                    "runserver",
                    "--noreload",
                ]
            )
        )

    def test_should_start_pe_log_sheet_scheduler_allows_runserver_with_bind_address(
        self,
    ):
        self.assertTrue(
            should_start_pe_log_sheet_scheduler(
                [
                    r"C:\\project\\django_server\\manage.py",
                    "runserver",
                    "0.0.0.0:8000",
                    "--noreload",
                ]
            )
        )

    def test_should_start_pe_log_sheet_scheduler_denies_test_and_maintenance_commands(
        self,
    ):
        denied_argvs = [
            [r"C:\\project\\django_server\\manage.py", "test"],
            [r"C:\\project\\django_server\\manage.py", "migrate"],
            [r"C:\\project\\django_server\\manage.py", "makemigrations"],
            [r"C:\\project\\django_server\\manage.py", "shell"],
            [r"C:\\project\\django_server\\manage.py", "sync_pe_log_sheet_from_csv"],
            [
                r"C:\\project\\django_server\\manage.py",
                "export_pe_log_sheet_to_data_explorer",
            ],
        ]

        for argv in denied_argvs:
            with self.subTest(argv=argv):
                self.assertFalse(should_start_pe_log_sheet_scheduler(argv))

    def test_is_daily_export_due_returns_true_at_local_noon(self):
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))

        self.assertTrue(is_daily_export_due(now, None))

    def test_is_daily_export_due_returns_false_after_missed_noon_minute(self):
        now = datetime(2026, 4, 16, 12, 1, 0, tzinfo=ZoneInfo("Asia/Seoul"))

        self.assertFalse(is_daily_export_due(now, None))

    def test_is_daily_export_due_returns_false_at_twelve_o_five_without_catch_up(self):
        now = datetime(2026, 4, 16, 12, 5, 0, tzinfo=ZoneInfo("Asia/Seoul"))

        self.assertFalse(is_daily_export_due(now, None))

    def test_is_daily_export_due_returns_false_when_same_local_date_was_already_attempted(
        self,
    ):
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))

        self.assertFalse(is_daily_export_due(now, date(2026, 4, 16)))


class PeLogSheetDailyExportServiceTests(TestCase):
    def _make_state(self):
        return PeLogSheetState.objects.create(
            singleton_key="main",
            workbook_data=[
                {
                    "id": "pe-log-main",
                    "name": "PE 로그",
                    "row": 2,
                    "column": 2,
                    "data": [
                        ["요청부서_현장명", "요청자"],
                        ["현장A", "홍길동"],
                    ],
                }
            ],
        )

    def test_export_writes_exact_csv_bytes_from_workbook(self):
        state = self._make_state()
        export_path = build_pe_log_sheet_export_path()
        export_path.parent.mkdir(parents=True, exist_ok=True)

        exported_path = export_pe_log_sheet_to_data_explorer()

        self.assertEqual(exported_path, export_path)
        self.assertEqual(
            exported_path.read_bytes(), workbook_to_csv_bytes(state.workbook_data)
        )

    def test_same_day_rerun_overwrites_same_path_atomically(self):
        state = self._make_state()
        export_path = build_pe_log_sheet_export_path()
        export_path.parent.mkdir(parents=True, exist_ok=True)

        export_path.write_bytes(b"old-data")
        state.workbook_data = [
            {
                "id": "pe-log-main",
                "name": "PE 로그",
                "row": 2,
                "column": 2,
                "data": [
                    ["요청부서_현장명", "요청자"],
                    ["현장B", "김철수"],
                ],
            }
        ]
        state.save(update_fields=["workbook_data", "updated_at"])

        export_pe_log_sheet_to_data_explorer()

        self.assertTrue(export_path.exists())
        self.assertEqual(
            export_path.read_bytes(), workbook_to_csv_bytes(state.workbook_data)
        )
        self.assertNotEqual(export_path.read_bytes(), b"old-data")

    def test_invalid_workbook_preserves_existing_file_contents(self):
        state = self._make_state()
        export_path = build_pe_log_sheet_export_path()
        export_path.parent.mkdir(parents=True, exist_ok=True)

        original_bytes = b"existing-valid-csv"
        export_path.write_bytes(original_bytes)
        state.workbook_data = []
        state.save(update_fields=["workbook_data", "updated_at"])

        with self.assertRaises(ValueError):
            export_pe_log_sheet_to_data_explorer()

        self.assertEqual(export_path.read_bytes(), original_bytes)


class PeLogSheetDataExplorerDatasetVisibilityTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="pe_log_dataset_visibility", password="password123"
        )
        token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.export_path = build_pe_log_sheet_export_path()
        self.export_path.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.export_path.exists():
            self.export_path.unlink()

    def _make_state(self):
        return PeLogSheetState.objects.create(
            singleton_key="main",
            workbook_data=[
                {
                    "id": "pe-log-main",
                    "name": "PE 로그",
                    "row": 2,
                    "column": 2,
                    "data": [
                        ["요청부서_현장명", "요청자"],
                        ["현장A", "홍길동"],
                    ],
                }
            ],
        )

    def test_exported_csv_appears_in_dataset_list_with_csv_extension(self):
        state = self._make_state()

        exported_path = export_pe_log_sheet_to_data_explorer()

        self.assertEqual(exported_path, self.export_path)
        self.assertEqual(
            exported_path.read_bytes(), workbook_to_csv_bytes(state.workbook_data)
        )

        response = self.client.get("/api/data-explorer/datasets/")

        self.assertEqual(response.status_code, 200)
        datasets = response.data["datasets"]
        matching_dataset = next(
            dataset for dataset in datasets if dataset["name"] == self.export_path.name
        )
        self.assertEqual(matching_dataset["extension"], "csv")


class PeLogSheetDailyExportCommandTests(TestCase):
    def _make_state(self):
        return PeLogSheetState.objects.create(
            singleton_key="main",
            workbook_data=[
                {
                    "id": "pe-log-main",
                    "name": "PE 로그",
                    "row": 2,
                    "column": 2,
                    "data": [
                        ["요청부서_현장명", "요청자"],
                        ["현장A", "홍길동"],
                    ],
                }
            ],
        )

    def test_command_prints_exact_destination_path_on_success(self):
        self._make_state()
        export_path = build_pe_log_sheet_export_path()

        stdout = StringIO()
        call_command(
            "export_pe_log_sheet_to_data_explorer",
            stdout=stdout,
            stderr=StringIO(),
        )

        self.assertEqual(stdout.getvalue().strip(), str(export_path))

    def test_command_overwrites_same_day_export_in_place(self):
        state = self._make_state()
        export_path = build_pe_log_sheet_export_path()
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_bytes(b"old-data")

        state.workbook_data = [
            {
                "id": "pe-log-main",
                "name": "PE 로그",
                "row": 2,
                "column": 2,
                "data": [
                    ["요청부서_현장명", "요청자"],
                    ["현장B", "김철수"],
                ],
            }
        ]
        state.save(update_fields=["workbook_data", "updated_at"])

        call_command("export_pe_log_sheet_to_data_explorer", stdout=StringIO())

        self.assertEqual(
            export_path.read_bytes(), workbook_to_csv_bytes(state.workbook_data)
        )
        self.assertNotEqual(export_path.read_bytes(), b"old-data")

    def test_command_fails_for_invalid_workbook_without_replacing_existing_file(self):
        state = self._make_state()
        export_path = build_pe_log_sheet_export_path()
        export_path.parent.mkdir(parents=True, exist_ok=True)
        original_bytes = b"existing-valid-csv"
        export_path.write_bytes(original_bytes)

        state.workbook_data = []
        state.save(update_fields=["workbook_data", "updated_at"])

        with self.assertRaises(CommandError):
            call_command(
                "export_pe_log_sheet_to_data_explorer",
                stdout=StringIO(),
                stderr=StringIO(),
            )

        self.assertEqual(export_path.read_bytes(), original_bytes)
