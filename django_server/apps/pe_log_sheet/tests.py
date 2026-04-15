"""Tests for PE log sheet behavior."""

# pyright: reportAttributeAccessIssue=false, reportOptionalSubscript=false

from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import PeLogSheetState
from .services.csv_loader import (
    DEFAULT_HEADERS,
    _SHEET_PASSTHROUGH_FIELDS,
    get_cell_payload,
    normalize_workbook_data,
)
from .services.conflict_detector import merge_ops_into_workbook
from .services.cell_lock import (
    CELL_LOCK_TTL_SECONDS,
    DEFAULT_DOCUMENT_ID as CELL_LOCK_DEFAULT_DOCUMENT_ID,
    get_cell_lock_registry,
)
from .services.presence import DEFAULT_DOCUMENT_ID, get_presence_registry


User = get_user_model()


def make_text_cell(value):
    return {"v": value, "m": value, "ct": {"fa": "@", "t": "inlineStr"}}


def build_runtime_snapshot_from_canonical(workbook_data):
    sheets = []
    for sheet in workbook_data:
        runtime_sheet = {
            "id": sheet.get("id"),
            "name": sheet.get("name"),
            "order": sheet.get("order", 0),
            "status": sheet.get("status", 1),
            "row": sheet.get("row", 10),
            "column": sheet.get("column", len(DEFAULT_HEADERS)),
            "showGridLines": sheet.get("showGridLines", 1),
            "defaultRowHeight": sheet.get("defaultRowHeight", 22),
            "defaultColWidth": sheet.get("defaultColWidth", 100),
            "config": deepcopy(sheet.get("config", {})),
            "data": [
                [None for _ in range(sheet.get("column", len(DEFAULT_HEADERS)))]
                for _ in range(sheet.get("row", 10))
            ],
        }
        if sheet.get("frozen"):
            runtime_sheet["frozen"] = deepcopy(sheet["frozen"])
        for item in sheet.get("celldata", []):
            runtime_sheet["data"][item["r"]][item["c"]] = deepcopy(item["v"])
        sheets.append(runtime_sheet)
    return sheets


class PeLogSheetNormalizationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="pe_log_tester", password="password123"
        )
        token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_normalize_runtime_snapshot_strips_session_fields_and_keeps_data(self):
        runtime_snapshot = [
            {
                "id": "pe-log-main",
                "name": "PE 로그",
                "order": 0,
                "status": 1,
                "row": 10,
                "column": len(DEFAULT_HEADERS),
                "showGridLines": 1,
                "defaultRowHeight": 22,
                "defaultColWidth": 100,
                "config": {"columnlen": {"0": 140}},
                "data": [
                    [make_text_cell(header) for header in DEFAULT_HEADERS],
                    [
                        make_text_cell("P4"),
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    ],
                ],
                "luckysheet_select_save": [{"row": [0, None], "column": [0, None]}],
                "scrollTop": 999,
                "scrollLeft": 888,
            }
        ]

        normalized = normalize_workbook_data(runtime_snapshot)

        self.assertEqual(len(normalized), 1)
        sheet = normalized[0]
        self.assertIn("celldata", sheet)
        self.assertNotIn("data", sheet)
        self.assertNotIn("luckysheet_select_save", sheet)
        self.assertNotIn("scrollTop", sheet)
        self.assertNotIn("scrollLeft", sheet)

        header_values = [item["v"]["m"] for item in sheet["celldata"] if item["r"] == 0]
        self.assertEqual(header_values, DEFAULT_HEADERS)

    def test_state_endpoint_normalizes_existing_runtime_snapshot(self):
        runtime_snapshot = [
            {
                "id": "pe-log-main",
                "name": "PE 로그",
                "order": 0,
                "status": 1,
                "row": 10,
                "column": len(DEFAULT_HEADERS),
                "showGridLines": 1,
                "defaultRowHeight": 22,
                "defaultColWidth": 100,
                "config": {"columnlen": {"0": 140}},
                "data": [
                    [make_text_cell(header) for header in DEFAULT_HEADERS],
                    [
                        make_text_cell("P4"),
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    ],
                ],
                "luckysheet_select_save": [{"row": [0, None], "column": [0, None]}],
            }
        ]
        PeLogSheetState.objects.create(
            singleton_key="main", workbook_data=runtime_snapshot, revision=7
        )

        response = self.client.get("/api/pe-log-sheet/state/")

        self.assertEqual(response.status_code, 200)
        sheet = response.data["workbook_data"][0]
        self.assertIn("celldata", sheet)
        self.assertNotIn("data", sheet)
        self.assertNotIn("luckysheet_select_save", sheet)

        persisted = PeLogSheetState.objects.get(singleton_key="main")
        self.assertNotIn("data", persisted.workbook_data[0])
        self.assertNotIn("luckysheet_select_save", persisted.workbook_data[0])

    def test_csv_upload_accepts_dynamic_headers(self):
        csv_bytes = "\ufeffA,B,C\r\n1,2,3\r\n".encode("utf-8")
        upload = SimpleUploadedFile("dynamic.csv", csv_bytes, content_type="text/csv")

        response = self.client.post("/api/pe-log-sheet/csv-upload/", {"file": upload})

        self.assertEqual(response.status_code, 200)
        state = PeLogSheetState.objects.get(singleton_key="main")
        header_values = [
            item["v"]["m"]
            for item in state.workbook_data[0]["celldata"]
            if item["r"] == 0
        ]
        self.assertEqual(header_values[:3], ["A", "B", "C"])
        self.assertEqual(state.workbook_data[0]["column"], 3)


class PeLogSheetCollaborationTests(APITestCase):
    def setUp(self):
        self.user_one = User.objects.create_user(
            username="user_one", password="password123"
        )
        self.user_two = User.objects.create_user(
            username="user_two", password="password123"
        )
        self.token_one, _ = Token.objects.get_or_create(user=self.user_one)
        self.token_two, _ = Token.objects.get_or_create(user=self.user_two)

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token_one.key}")
        state_response = self.client.get("/api/pe-log-sheet/state/")
        self.initial_state = state_response.data
        self.assertEqual(state_response.status_code, 200)

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def _make_snapshot(self):
        return build_runtime_snapshot_from_canonical(
            PeLogSheetState.objects.get(singleton_key="main").workbook_data
        )

    def _make_base_snapshot(self):
        return build_runtime_snapshot_from_canonical(
            self.initial_state["workbook_data"]
        )

    def test_different_cells_merge_across_revision_gap(self):
        snapshot_one = self._make_base_snapshot()
        snapshot_one[0]["data"][1][0] = make_text_cell("부서A")
        ops_one = [
            {
                "op": "replace",
                "id": "pe-log-main",
                "path": ["data", 1, 0],
                "value": make_text_cell("부서A"),
            }
        ]
        self._auth(self.token_one)
        response_one = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": self.initial_state["revision"],
                "ops": ops_one,
                "snapshot": snapshot_one,
                "client_id": "client-one",
            },
            format="json",
        )
        self.assertEqual(response_one.status_code, 200)

        snapshot_two = self._make_base_snapshot()
        snapshot_two[0]["data"][1][1] = make_text_cell("홍길동")
        ops_two = [
            {
                "op": "replace",
                "id": "pe-log-main",
                "path": ["data", 1, 1],
                "value": make_text_cell("홍길동"),
            }
        ]
        self._auth(self.token_two)
        response_two = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": self.initial_state["revision"],
                "ops": ops_two,
                "snapshot": snapshot_two,
                "client_id": "client-two",
            },
            format="json",
        )

        self.assertEqual(response_two.status_code, 200)
        state = PeLogSheetState.objects.get(singleton_key="main")
        self.assertEqual(
            get_cell_payload(state.workbook_data, "pe-log-main", 1, 0)["m"], "부서A"
        )
        self.assertEqual(
            get_cell_payload(state.workbook_data, "pe-log-main", 1, 1)["m"], "홍길동"
        )

    def test_same_cell_conflict_returns_structured_payload(self):
        snapshot_one = self._make_base_snapshot()
        snapshot_one[0]["data"][1][0] = make_text_cell("부서A")
        ops_one = [
            {
                "op": "replace",
                "id": "pe-log-main",
                "path": ["data", 1, 0],
                "value": make_text_cell("부서A"),
            }
        ]
        self._auth(self.token_one)
        response_one = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": self.initial_state["revision"],
                "ops": ops_one,
                "snapshot": snapshot_one,
                "client_id": "client-one",
            },
            format="json",
        )
        self.assertEqual(response_one.status_code, 200)

        snapshot_two = self._make_base_snapshot()
        snapshot_two[0]["data"][1][0] = make_text_cell("부서B")
        ops_two = [
            {
                "op": "replace",
                "id": "pe-log-main",
                "path": ["data", 1, 0],
                "value": make_text_cell("부서B"),
            }
        ]
        self._auth(self.token_two)
        response_two = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": self.initial_state["revision"],
                "ops": ops_two,
                "snapshot": snapshot_two,
                "client_id": "client-two",
            },
            format="json",
        )

        self.assertEqual(response_two.status_code, 409)
        self.assertEqual(response_two.data["error"], "conflict")
        self.assertEqual(len(response_two.data["conflicts"]), 1)
        conflict = response_two.data["conflicts"][0]
        self.assertEqual(conflict["conflict_type"], "cell-edit")
        self.assertEqual(conflict["cell_address"], "A2")
        self.assertEqual(conflict["server_value"], "부서A")
        self.assertEqual(conflict["client_value"], "부서B")
        self.assertEqual(conflict["server_editor"], "user_one")

    def test_same_revision_commit_uses_snapshot_as_final_authoritative_state(self):
        snapshot = self._make_base_snapshot()
        snapshot[0]["data"][309][8] = make_text_cell("__TEST__3")
        ops = [
            {
                "op": "replace",
                "id": "pe-log-main",
                "path": ["data", 309, 8, "ct"],
                "value": {"fa": "@", "t": "inlineStr"},
            },
            {
                "op": "replace",
                "id": "pe-log-main",
                "path": ["data", 309, 8, "m"],
                "value": "__TEST__3",
            },
            {
                "op": "replace",
                "id": "pe-log-main",
                "path": ["data", 309, 8, "v"],
                "value": "__TEST__3",
            },
            {"op": "remove", "id": "pe-log-main", "path": ["data", 309, 8, "m"]},
            {"op": "remove", "id": "pe-log-main", "path": ["data", 309, 8, "v"]},
        ]

        self._auth(self.token_one)
        response = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": self.initial_state["revision"],
                "ops": ops,
                "snapshot": snapshot,
                "client_id": "client-one",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        state = PeLogSheetState.objects.get(singleton_key="main")
        self.assertEqual(
            get_cell_payload(state.workbook_data, "pe-log-main", 309, 8)["m"],
            "__TEST__3",
        )

    def test_structural_row_insert_succeeds_on_same_revision(self):
        snapshot = self._make_base_snapshot()
        sheet = snapshot[0]
        original_row_count = sheet["row"]
        insert_index = 1
        original_value = get_cell_payload(
            self.initial_state["workbook_data"], "pe-log-main", insert_index, 0
        )
        sheet["data"].insert(insert_index, [None for _ in range(sheet["column"])])
        sheet["row"] += 1
        self._auth(self.token_one)
        response = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": self.initial_state["revision"],
                "ops": [
                    {
                        "op": "insertRowCol",
                        "id": "pe-log-main",
                        "value": {
                            "type": "row",
                            "index": insert_index,
                            "count": 1,
                            "direction": "rightbottom",
                            "id": "pe-log-main",
                        },
                    }
                ],
                "snapshot": snapshot,
                "client_id": "client-one",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        state = PeLogSheetState.objects.get(singleton_key="main")
        self.assertEqual(state.workbook_data[0]["row"], original_row_count + 1)
        self.assertIsNone(
            get_cell_payload(state.workbook_data, "pe-log-main", insert_index, 0)
        )
        self.assertEqual(
            get_cell_payload(state.workbook_data, "pe-log-main", insert_index + 1, 0),
            original_value,
        )

    def test_structural_row_delete_succeeds_on_same_revision(self):
        snapshot = self._make_base_snapshot()
        sheet = snapshot[0]
        deleted_value = get_cell_payload(
            self.initial_state["workbook_data"], "pe-log-main", 1, 0
        )
        next_value = get_cell_payload(
            self.initial_state["workbook_data"], "pe-log-main", 2, 0
        )
        del sheet["data"][1]
        sheet["row"] -= 1

        self._auth(self.token_one)
        response = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": self.initial_state["revision"],
                "ops": [
                    {
                        "op": "deleteRowCol",
                        "id": "pe-log-main",
                        "value": {
                            "type": "row",
                            "start": 1,
                            "end": 1,
                            "id": "pe-log-main",
                        },
                    }
                ],
                "snapshot": snapshot,
                "client_id": "client-one",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        state = PeLogSheetState.objects.get(singleton_key="main")
        self.assertNotEqual(
            get_cell_payload(state.workbook_data, "pe-log-main", 1, 0), deleted_value
        )
        self.assertEqual(
            get_cell_payload(state.workbook_data, "pe-log-main", 1, 0), next_value
        )

    def test_structural_column_delete_succeeds_on_same_revision(self):
        snapshot = self._make_base_snapshot()
        sheet = snapshot[0]
        original_headers = [
            sheet["data"][0][index]["m"] for index in range(sheet["column"])
        ]
        deleted_header = original_headers[1]
        expected_header = original_headers[2]
        for row in sheet["data"]:
            del row[1]
        sheet["column"] -= 1

        self._auth(self.token_one)
        response = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": self.initial_state["revision"],
                "ops": [
                    {
                        "op": "deleteRowCol",
                        "id": "pe-log-main",
                        "value": {
                            "type": "column",
                            "start": 1,
                            "end": 1,
                            "id": "pe-log-main",
                        },
                    }
                ],
                "snapshot": snapshot,
                "client_id": "client-one",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        state = PeLogSheetState.objects.get(singleton_key="main")
        headers = [
            item["v"]["m"]
            for item in state.workbook_data[0]["celldata"]
            if item["r"] == 0
        ]
        self.assertNotIn(deleted_header, headers)
        self.assertEqual(headers[1], expected_header)
        self.assertEqual(state.workbook_data[0]["column"], len(original_headers) - 1)

    def test_stale_structural_op_returns_structural_conflict(self):
        snapshot_one = self._make_base_snapshot()
        snapshot_one[0]["data"][1][0] = make_text_cell("부서A")
        ops_one = [
            {
                "op": "replace",
                "id": "pe-log-main",
                "path": ["data", 1, 0],
                "value": make_text_cell("부서A"),
            }
        ]
        self._auth(self.token_one)
        response_one = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": self.initial_state["revision"],
                "ops": ops_one,
                "snapshot": snapshot_one,
                "client_id": "client-one",
            },
            format="json",
        )
        self.assertEqual(response_one.status_code, 200)

        stale_snapshot = self._make_base_snapshot()
        stale_snapshot[0]["data"].insert(
            1, [None for _ in range(stale_snapshot[0]["column"])]
        )
        stale_snapshot[0]["row"] += 1

        self._auth(self.token_two)
        response_two = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": self.initial_state["revision"],
                "ops": [
                    {
                        "op": "insertRowCol",
                        "id": "pe-log-main",
                        "value": {
                            "type": "row",
                            "index": 1,
                            "count": 1,
                            "direction": "rightbottom",
                            "id": "pe-log-main",
                        },
                    }
                ],
                "snapshot": stale_snapshot,
                "client_id": "client-two",
            },
            format="json",
        )

        self.assertEqual(response_two.status_code, 409)
        self.assertEqual(
            response_two.data["conflicts"][0]["conflict_type"], "structural"
        )

    def test_same_revision_structural_ops_ignore_stale_snapshot_and_apply_ops(self):
        stale_snapshot = self._make_base_snapshot()

        self._auth(self.token_one)
        response = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": self.initial_state["revision"],
                "ops": [
                    {
                        "op": "deleteRowCol",
                        "id": "pe-log-main",
                        "value": {
                            "type": "row",
                            "start": 1,
                            "end": 1,
                            "id": "pe-log-main",
                        },
                    }
                ],
                "snapshot": stale_snapshot,
                "client_id": "client-one",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        state = PeLogSheetState.objects.get(singleton_key="main")
        self.assertEqual(state.revision, self.initial_state["revision"] + 1)
        self.assertEqual(
            state.workbook_data[0]["row"],
            self.initial_state["workbook_data"][0]["row"] - 1,
        )


class PeLogSheetPresenceTests(TestCase):
    def setUp(self):
        self.registry = get_presence_registry()
        self.registry.reset()
        self.user_one = User.objects.create_user(
            username="presence_one", password="password123"
        )
        self.user_two = User.objects.create_user(
            username="presence_two", password="password123"
        )

    def tearDown(self):
        self.registry.reset()

    def test_join_returns_current_active_users_and_second_join_includes_both(self):
        with patch(
            "apps.pe_log_sheet.services.presence.time.monotonic", side_effect=[0, 1]
        ):
            snapshot_one = self.registry.join(
                DEFAULT_DOCUMENT_ID, "client-one", self.user_one
            )
            snapshot_two = self.registry.join(
                DEFAULT_DOCUMENT_ID, "client-two", self.user_two
            )

        self.assertEqual(
            snapshot_one, [{"username": "presence_one", "display_name": "presence_one"}]
        )
        self.assertEqual(
            snapshot_two,
            [
                {"username": "presence_one", "display_name": "presence_one"},
                {"username": "presence_two", "display_name": "presence_two"},
            ],
        )

    def test_leave_removes_the_exact_user_immediately(self):
        with patch(
            "apps.pe_log_sheet.services.presence.time.monotonic", side_effect=[0, 1, 2]
        ):
            self.registry.join(DEFAULT_DOCUMENT_ID, "client-one", self.user_one)
            self.registry.join(DEFAULT_DOCUMENT_ID, "client-two", self.user_two)
            leave_snapshot = self.registry.leave(DEFAULT_DOCUMENT_ID, "client-one")

        self.assertEqual(
            leave_snapshot,
            [{"username": "presence_two", "display_name": "presence_two"}],
        )

    def test_heartbeat_refreshes_existing_entries_without_recreating_expired_users(
        self,
    ):
        with patch(
            "apps.pe_log_sheet.services.presence.time.monotonic",
            side_effect=[0, 9, 18.9],
        ):
            self.registry.join(DEFAULT_DOCUMENT_ID, "client-one", self.user_one)
            refreshed_snapshot, changed = self.registry.heartbeat(
                DEFAULT_DOCUMENT_ID,
                "client-one",
                self.user_one,
            )
            later_snapshot = self.registry.snapshot(DEFAULT_DOCUMENT_ID)

        self.assertFalse(changed)
        self.assertEqual(
            refreshed_snapshot,
            [{"username": "presence_one", "display_name": "presence_one"}],
        )
        self.assertEqual(
            later_snapshot,
            [{"username": "presence_one", "display_name": "presence_one"}],
        )

    def test_heartbeat_does_not_recreate_expired_or_missing_client_entries(self):
        with patch(
            "apps.pe_log_sheet.services.presence.time.monotonic", side_effect=[0, 11]
        ):
            self.registry.join(DEFAULT_DOCUMENT_ID, "client-one", self.user_one)
            snapshot, changed = self.registry.heartbeat(
                DEFAULT_DOCUMENT_ID, "client-one", self.user_one
            )

        self.assertEqual(snapshot, [])
        self.assertTrue(changed)

    def test_heartbeat_for_missing_client_does_not_create_presence(self):
        with patch(
            "apps.pe_log_sheet.services.presence.time.monotonic", return_value=0
        ):
            snapshot, changed = self.registry.heartbeat(
                DEFAULT_DOCUMENT_ID, "client-missing", self.user_one
            )

        self.assertEqual(snapshot, [])
        self.assertFalse(changed)

    def test_snapshot_prunes_stale_entries_after_ten_second_ttl(self):
        with patch(
            "apps.pe_log_sheet.services.presence.time.monotonic", side_effect=[0, 5, 11]
        ):
            self.registry.join(DEFAULT_DOCUMENT_ID, "client-one", self.user_one)
            self.registry.join(DEFAULT_DOCUMENT_ID, "client-two", self.user_two)
            snapshot = self.registry.snapshot(DEFAULT_DOCUMENT_ID)

        self.assertEqual(
            snapshot, [{"username": "presence_two", "display_name": "presence_two"}]
        )


class PeLogSheetCellLockApiTests(TestCase):
    def setUp(self):
        self.registry = get_cell_lock_registry()
        self.registry.reset()
        self.user_one = User.objects.create_user(
            username="cell_lock_one", password="password123"
        )
        self.user_two = User.objects.create_user(
            username="cell_lock_two", password="password123"
        )
        self.client.force_login(self.user_one)

    def tearDown(self):
        self.registry.reset()

    def _post(self, name, payload):
        return self.client.post(reverse(name), payload)

    def test_acquire_new_cell_returns_200(self):
        response = self._post(
            "pe-log-cell-lock-acquire",
            {
                "client_id": "client-one",
                "sheet_id": "pe-log-main",
                "row": 1,
                "column": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_new"])
        self.assertEqual(response.json()["lock"]["client_id"], "client-one")

    def test_acquire_same_cell_same_client_idempotent(self):
        first = self._post(
            "pe-log-cell-lock-acquire",
            {
                "client_id": "client-one",
                "sheet_id": "pe-log-main",
                "row": 1,
                "column": 0,
            },
        )
        second = self._post(
            "pe-log-cell-lock-acquire",
            {
                "client_id": "client-one",
                "sheet_id": "pe-log-main",
                "row": 1,
                "column": 0,
            },
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(first.json()["is_new"])
        self.assertFalse(second.json()["is_new"])

    def test_acquire_locked_cell_returns_409(self):
        self._post(
            "pe-log-cell-lock-acquire",
            {
                "client_id": "client-one",
                "sheet_id": "pe-log-main",
                "row": 1,
                "column": 0,
            },
        )
        self.client.force_login(self.user_two)
        response = self._post(
            "pe-log-cell-lock-acquire",
            {
                "client_id": "client-two",
                "sheet_id": "pe-log-main",
                "row": 1,
                "column": 0,
            },
        )

        payload = response.json()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(payload["conflict_type"], "cell-lock")
        self.assertEqual(payload["lock_owner"]["client_id"], "client-one")
        self.assertEqual(payload["locked_cell"]["cell_address"], "A2")

    def test_heartbeat_refreshes_self_owned_lock(self):
        self._post(
            "pe-log-cell-lock-acquire",
            {
                "client_id": "client-one",
                "sheet_id": "pe-log-main",
                "row": 1,
                "column": 0,
            },
        )

        response = self._post(
            "pe-log-cell-lock-heartbeat",
            {
                "client_id": "client-one",
                "sheet_id": "pe-log-main",
                "row": 1,
                "column": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["refreshed"])
        self.assertEqual(response.json()["lock"]["client_id"], "client-one")

    def test_heartbeat_unowned_cell_returns_not_refreshed(self):
        response = self._post(
            "pe-log-cell-lock-heartbeat",
            {
                "client_id": "client-one",
                "sheet_id": "pe-log-main",
                "row": 1,
                "column": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["refreshed"])
        self.assertIsNone(response.json()["lock"])

    def test_release_removes_self_owned_lock(self):
        self._post(
            "pe-log-cell-lock-acquire",
            {
                "client_id": "client-one",
                "sheet_id": "pe-log-main",
                "row": 1,
                "column": 0,
            },
        )
        response = self._post(
            "pe-log-cell-lock-release",
            {
                "client_id": "client-one",
                "sheet_id": "pe-log-main",
                "row": 1,
                "column": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["released"])
        self.assertIsNone(
            self.registry.owner_for_cell(
                CELL_LOCK_DEFAULT_DOCUMENT_ID, "pe-log-main", 1, 0
            )
        )

    def test_presence_leave_releases_all_locks(self):
        self._post(
            "pe-log-cell-lock-acquire",
            {
                "client_id": "client-one",
                "sheet_id": "pe-log-main",
                "row": 1,
                "column": 0,
            },
        )
        response = self.client.post(
            reverse("pe-log-presence-leave"),
            {"client_id": "client-one"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(
            self.registry.owner_for_cell(
                CELL_LOCK_DEFAULT_DOCUMENT_ID, "pe-log-main", 1, 0
            )
        )


class PeLogSheetCellLockTests(TestCase):
    """Tests for CellLockRegistry — thread-safe, document-scoped cell soft-locks."""

    def setUp(self):
        self.registry = get_cell_lock_registry()
        self.registry.reset()
        self.user_one = User.objects.create_user(
            username="lock_user_one", password="password123"
        )
        self.user_two = User.objects.create_user(
            username="lock_user_two", password="password123"
        )

    def tearDown(self):
        self.registry.reset()

    def test_acquire_same_cell_same_client_idempotent(self):
        """Acquiring the same cell twice returns same lock info (idempotent)."""
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic",
            side_effect=[0, 5],
        ):
            lock_info_first, is_new_first = self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-one",
                self.user_one,
            )
            lock_info_second, is_new_second = self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-one",
                self.user_one,
            )

        self.assertTrue(is_new_first)
        self.assertFalse(is_new_second)
        self.assertEqual(lock_info_first["client_id"], "client-one")
        self.assertEqual(lock_info_first["row"], 1)
        self.assertEqual(lock_info_first["column"], 0)
        self.assertEqual(lock_info_second["row"], 1)
        self.assertEqual(lock_info_second["column"], 0)
        # last_seen should be refreshed on idempotent acquire
        self.assertGreaterEqual(
            lock_info_second["last_seen"], lock_info_first["last_seen"]
        )

    def test_acquire_different_cell_same_client_moves_ownership(self):
        """Client moves from cell A to cell B; cell A is released."""
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic",
            side_effect=[0, 1, 2, 3],
        ):
            lock_a, is_new_a = self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-one",
                self.user_one,
            )
            lock_b, is_new_b = self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                2,
                3,
                "client-one",
                self.user_one,
            )

            self.assertTrue(is_new_a)
            self.assertTrue(is_new_b)
            self.assertEqual(lock_b["row"], 2)
            self.assertEqual(lock_b["column"], 3)

            # Cell A should now be unlocked (no owner)
            owner_a = self.registry.owner_for_cell(
                CELL_LOCK_DEFAULT_DOCUMENT_ID, "pe-log-main", 1, 0
            )
            self.assertIsNone(owner_a)

            # Cell B should be owned by client-one
            owner_b = self.registry.owner_for_cell(
                CELL_LOCK_DEFAULT_DOCUMENT_ID, "pe-log-main", 2, 3
            )
            self.assertEqual(owner_b["client_id"], "client-one")

    def test_acquire_locked_cell_different_client_returns_locked_by(self):
        """Client B tries to lock a cell held by Client A; returns owner info."""
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic",
            side_effect=[0, 1, 2],
        ):
            lock_info_a, is_new_a = self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-one",
                self.user_one,
            )
            lock_info_b, is_new_b = self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-two",
                self.user_two,
            )

            self.assertTrue(is_new_a)
            self.assertFalse(is_new_b)
            # Should return the owner's info, not the challenger's
            self.assertEqual(lock_info_b["client_id"], "client-one")
            self.assertEqual(lock_info_b["username"], "lock_user_one")

            # Verify no mutation — client-one still owns the cell
            owner = self.registry.owner_for_cell(
                CELL_LOCK_DEFAULT_DOCUMENT_ID, "pe-log-main", 1, 0
            )
            self.assertEqual(owner["client_id"], "client-one")

    def test_heartbeat_refreshes_self_owned_lock(self):
        """Heartbeat on self-owned lock refreshes last_seen."""
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic",
            side_effect=[0, 30],
        ):
            self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-one",
                self.user_one,
            )
            lock_info, refreshed = self.registry.heartbeat(
                CELL_LOCK_DEFAULT_DOCUMENT_ID, "client-one", "pe-log-main", 1, 0
            )

        self.assertTrue(refreshed)
        self.assertEqual(lock_info["client_id"], "client-one")
        self.assertEqual(lock_info["last_seen"], 30)

    def test_heartbeat_does_not_refresh_other_client_lock(self):
        """Heartbeat on another client's lock returns None."""
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic",
            side_effect=[0, 1],
        ):
            self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-one",
                self.user_one,
            )
            # client-two tries to heartbeat client-one's cell
            lock_info, refreshed = self.registry.heartbeat(
                CELL_LOCK_DEFAULT_DOCUMENT_ID, "client-two", "pe-log-main", 1, 0
            )

        self.assertIsNone(lock_info)
        self.assertFalse(refreshed)

    def test_release_removes_self_owned_lock(self):
        """Release removes own lock."""
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic",
            side_effect=[0, 1],
        ):
            self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-one",
                self.user_one,
            )
            self.registry.release(
                CELL_LOCK_DEFAULT_DOCUMENT_ID, "client-one", "pe-log-main", 1, 0
            )

        owner = self.registry.owner_for_cell(
            CELL_LOCK_DEFAULT_DOCUMENT_ID, "pe-log-main", 1, 0
        )
        self.assertIsNone(owner)

    def test_release_is_harmless_for_other_client_lock(self):
        """Release on another client's lock is a no-op."""
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic",
            side_effect=[0, 1, 2, 3],
        ):
            self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-one",
                self.user_one,
            )
            # client-two tries to release client-one's lock — harmless
            self.registry.release(
                CELL_LOCK_DEFAULT_DOCUMENT_ID, "client-two", "pe-log-main", 1, 0
            )

            # client-one still owns the cell
            owner = self.registry.owner_for_cell(
                CELL_LOCK_DEFAULT_DOCUMENT_ID, "pe-log-main", 1, 0
            )
            self.assertEqual(owner["client_id"], "client-one")

    def test_release_all_removes_all_locks_for_client(self):
        """release_all removes every lock for a client in the document."""
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic",
            side_effect=[0, 1, 2, 3, 4, 5],
        ):
            # client-one acquires cell (1,0), then moves to (2,3)
            self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-one",
                self.user_one,
            )
            self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                2,
                3,
                "client-one",
                self.user_one,
            )
            # client-two acquires a different cell
            self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                5,
                1,
                "client-two",
                self.user_two,
            )

            # release_all for client-one
            self.registry.release_all(CELL_LOCK_DEFAULT_DOCUMENT_ID, "client-one")

            # client-one's current cell (2,3) should be gone
            owner = self.registry.owner_for_cell(
                CELL_LOCK_DEFAULT_DOCUMENT_ID, "pe-log-main", 2, 3
            )
            self.assertIsNone(owner)

            # client-two's cell should still be held
            owner_two = self.registry.owner_for_cell(
                CELL_LOCK_DEFAULT_DOCUMENT_ID, "pe-log-main", 5, 1
            )
            self.assertEqual(owner_two["client_id"], "client-two")

    def test_ttl_pruning_removes_expired_locks(self):
        """Locks older than 60 seconds are pruned on next access."""
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic",
            side_effect=[0, 1, 62],
        ):
            self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-one",
                self.user_one,
            )
            self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                2,
                3,
                "client-two",
                self.user_two,
            )
            # At t=62, client-one's lock (t=0) is expired (62-0=62 > 60),
            # client-two's lock (t=1) is also expired (62-1=61 > 60).
            # Both should be pruned.
            snapshot = self.registry.snapshot(CELL_LOCK_DEFAULT_DOCUMENT_ID)

        self.assertEqual(snapshot, [])

    def test_owner_for_cell_returns_owner_or_none(self):
        """Returns owner info for locked cell, None for unlocked."""
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic",
            side_effect=[0, 1],
        ):
            self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-one",
                self.user_one,
            )

        # Locked cell returns owner
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic", return_value=2
        ):
            owner = self.registry.owner_for_cell(
                CELL_LOCK_DEFAULT_DOCUMENT_ID, "pe-log-main", 1, 0
            )
        self.assertIsNotNone(owner)
        self.assertEqual(owner["client_id"], "client-one")

        # Unlocked cell returns None
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic", return_value=3
        ):
            no_owner = self.registry.owner_for_cell(
                CELL_LOCK_DEFAULT_DOCUMENT_ID, "pe-log-main", 5, 5
            )
        self.assertIsNone(no_owner)


class PeLogSheetCellLockOpsTests(APITestCase):
    """Tests for cell-lock pre-check in SheetOpsView.post()."""

    def setUp(self):
        self.registry = get_cell_lock_registry()
        self.registry.reset()
        self.user_one = User.objects.create_user(
            username="lock_ops_one", password="password123"
        )
        self.user_two = User.objects.create_user(
            username="lock_ops_two", password="password123"
        )
        self.token_one, _ = Token.objects.get_or_create(user=self.user_one)
        self.token_two, _ = Token.objects.get_or_create(user=self.user_two)

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token_one.key}")
        state_response = self.client.get("/api/pe-log-sheet/state/")
        self.initial_state = state_response.data
        self.assertEqual(state_response.status_code, 200)

    def tearDown(self):
        self.registry.reset()

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def _make_base_snapshot(self):
        return build_runtime_snapshot_from_canonical(
            self.initial_state["workbook_data"]
        )

    def _make_single_cell_ops(self, row, column, value):
        """Build a single-cell replace op batch."""
        return [
            {
                "op": "replace",
                "id": "pe-log-main",
                "path": ["data", row, column],
                "value": make_text_cell(value),
            }
        ]

    def test_ops_locked_cell_returns_409_cell_lock(self):
        """Client B submits ops for a cell locked by Client A → 409 cell-lock."""
        # Patch time.monotonic throughout so the lock doesn't expire
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic",
            side_effect=[0, 1, 2],
        ):
            # Client A acquires lock on cell (1, 0)
            self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-one",
                self.user_one,
            )

            # Client B tries to save to the same cell
            snapshot = self._make_base_snapshot()
            snapshot[0]["data"][1][0] = make_text_cell("부서B")
            ops = self._make_single_cell_ops(1, 0, "부서B")

            self._auth(self.token_two)
            response = self.client.post(
                "/api/pe-log-sheet/ops/",
                {
                    "base_revision": self.initial_state["revision"],
                    "ops": ops,
                    "snapshot": snapshot,
                    "client_id": "client-two",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 409)
        data = response.data
        self.assertEqual(data["error"], "conflict")
        self.assertEqual(data["conflict_type"], "cell-lock")
        self.assertEqual(data["locked_cell"]["sheet_id"], "pe-log-main")
        self.assertEqual(data["locked_cell"]["row"], 1)
        self.assertEqual(data["locked_cell"]["column"], 0)
        self.assertEqual(data["locked_cell"]["cell_address"], "A2")
        self.assertEqual(data["lock_owner"]["client_id"], "client-one")
        self.assertEqual(data["lock_owner"]["username"], "lock_ops_one")
        self.assertEqual(data["revision"], self.initial_state["revision"])
        self.assertIsNotNone(data["workbook_data"])

    def test_ops_self_locked_cell_passes(self):
        """Client submits ops for a cell they themselves locked → commit succeeds."""
        # Patch time.monotonic throughout so the lock doesn't expire
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic",
            side_effect=[0, 1, 2],
        ):
            # Client A acquires lock on cell (1, 0)
            self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-one",
                self.user_one,
            )

            # Client A saves to the same cell — should succeed
            snapshot = self._make_base_snapshot()
            snapshot[0]["data"][1][0] = make_text_cell("부서A")
            ops = self._make_single_cell_ops(1, 0, "부서A")

            self._auth(self.token_one)
            response = self.client.post(
                "/api/pe-log-sheet/ops/",
                {
                    "base_revision": self.initial_state["revision"],
                    "ops": ops,
                    "snapshot": snapshot,
                    "client_id": "client-one",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["new_revision"], self.initial_state["revision"] + 1
        )

    def test_ops_unlocked_cell_passes(self):
        """Client submits ops for an unlocked cell → commit succeeds normally."""
        # No locks acquired — cell is free
        snapshot = self._make_base_snapshot()
        snapshot[0]["data"][1][0] = make_text_cell("부서A")
        ops = self._make_single_cell_ops(1, 0, "부서A")

        self._auth(self.token_one)
        response = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": self.initial_state["revision"],
                "ops": ops,
                "snapshot": snapshot,
                "client_id": "client-one",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["new_revision"], self.initial_state["revision"] + 1
        )

    def test_ops_multi_cell_skips_lock_check(self):
        """Multi-cell ops batch skips lock check and proceeds to normal flow."""
        # Patch time.monotonic throughout so the lock doesn't expire
        with patch(
            "apps.pe_log_sheet.services.cell_lock.time.monotonic",
            side_effect=[0, 1, 2],
        ):
            # Client A locks cell (1, 0)
            self.registry.acquire(
                CELL_LOCK_DEFAULT_DOCUMENT_ID,
                "pe-log-main",
                1,
                0,
                "client-one",
                self.user_one,
            )

            # Client B submits multi-cell ops that include the locked cell
            # Lock check is skipped for multi-cell batches
            snapshot = self._make_base_snapshot()
            snapshot[0]["data"][1][0] = make_text_cell("부서B")
            snapshot[0]["data"][1][1] = make_text_cell("홍길동")
            ops = [
                {
                    "op": "replace",
                    "id": "pe-log-main",
                    "path": ["data", 1, 0],
                    "value": make_text_cell("부서B"),
                },
                {
                    "op": "replace",
                    "id": "pe-log-main",
                    "path": ["data", 1, 1],
                    "value": make_text_cell("홍길동"),
                },
            ]

            self._auth(self.token_two)
            response = self.client.post(
                "/api/pe-log-sheet/ops/",
                {
                    "base_revision": self.initial_state["revision"],
                    "ops": ops,
                    "snapshot": snapshot,
                    "client_id": "client-two",
                },
                format="json",
            )

        # Should succeed (no revision gap, multi-cell skips lock check)
        self.assertEqual(response.status_code, 200)

    def test_existing_revision_conflict_still_works(self):
        """Existing revision-gap cell-edit conflict still returns cell-edit when lock check passes."""
        # Client A commits first
        snapshot_one = self._make_base_snapshot()
        snapshot_one[0]["data"][1][0] = make_text_cell("부서A")
        ops_one = self._make_single_cell_ops(1, 0, "부서A")

        self._auth(self.token_one)
        response_one = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": self.initial_state["revision"],
                "ops": ops_one,
                "snapshot": snapshot_one,
                "client_id": "client-one",
            },
            format="json",
        )
        self.assertEqual(response_one.status_code, 200)

        # Client B submits stale ops for the same cell (no lock held)
        # Should get revision-gap cell-edit conflict, NOT cell-lock
        snapshot_two = self._make_base_snapshot()
        snapshot_two[0]["data"][1][0] = make_text_cell("부서B")
        ops_two = self._make_single_cell_ops(1, 0, "부서B")

        self._auth(self.token_two)
        response_two = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": self.initial_state["revision"],
                "ops": ops_two,
                "snapshot": snapshot_two,
                "client_id": "client-two",
            },
            format="json",
        )

        self.assertEqual(response_two.status_code, 409)
        self.assertEqual(response_two.data["error"], "conflict")
        # Should be cell-edit conflict (revision gap), not cell-lock
        self.assertEqual(
            response_two.data["conflicts"][0]["conflict_type"], "cell-edit"
        )


class DataVerificationPreservationTests(APITestCase):
    """Regression tests: normalize_workbook_data must not drop FortuneSheet passthrough fields."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="dv_tester", password="password123"
        )
        token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def _minimal_sheet(self, **extra):
        sheet = {
            "id": "pe-log-main",
            "name": "Sheet1",
            "order": 0,
            "status": 1,
            "row": 5,
            "column": 3,
            "celldata": [],
            "showGridLines": 1,
            "defaultRowHeight": 22,
            "defaultColWidth": 73,
            "config": {},
        }
        sheet.update(extra)
        return sheet

    def test_normalize_preserves_dataVerification(self):
        """normalize_workbook_data must keep dataVerification on the sheet."""
        dv = {
            "0": {
                "type": "dropdown",
                "value1": "A,B,C",
                "prohibitInput": True,
                "hintShow": False,
                "hintText": "",
                "remote": False,
            }
        }
        workbook = [self._minimal_sheet(dataVerification=dv)]
        result = normalize_workbook_data(workbook)
        self.assertEqual(result[0].get("dataVerification"), dv)

    def test_normalize_preserves_all_passthrough_fields(self):
        """Every field in _SHEET_PASSTHROUGH_FIELDS must survive normalize round-trip."""
        sample_values = {field: {"__test__": field} for field in _SHEET_PASSTHROUGH_FIELDS}
        workbook = [self._minimal_sheet(**sample_values)]
        result = normalize_workbook_data(workbook)
        for field in _SHEET_PASSTHROUGH_FIELDS:
            self.assertEqual(
                result[0].get(field),
                {"__test__": field},
                msg=f"Field '{field}' was dropped by normalize_workbook_data",
            )

    def test_merge_ops_preserves_existing_dataVerification(self):
        """merge_ops_into_workbook must not erase pre-existing dataVerification."""
        dv = {"0": {"type": "dropdown", "value1": "X,Y,Z"}}
        workbook = [self._minimal_sheet(dataVerification=dv)]
        # A simple cell-value op — unrelated to dataVerification
        ops = [
            {
                "op": "replace",
                "path": ["0", "0", "v"],
                "value": {"v": "hello", "m": "hello", "ct": {"fa": "General", "t": "g"}},
                "id": "pe-log-main",
            }
        ]
        result = merge_ops_into_workbook(workbook, ops)
        self.assertEqual(
            result[0].get("dataVerification"),
            dv,
            msg="merge_ops_into_workbook dropped dataVerification",
        )

    def test_snapshot_save_get_roundtrip_preserves_dataVerification(self):
        """POST /ops/ with snapshot containing dataVerification → GET /state/ must return it."""
        # Bootstrap state
        PeLogSheetState.objects.all().delete()
        with patch(
            "apps.pe_log_sheet.views._load_seed_workbook",
            return_value=[self._minimal_sheet()],
        ), patch(
            "apps.pe_log_sheet.views._seed_checksum",
            return_value="test-checksum",
        ):
            init_resp = self.client.get("/api/pe-log-sheet/state/")
        self.assertEqual(init_resp.status_code, 200)
        revision = init_resp.data["revision"]

        # Build snapshot with dataVerification
        dv = {"1": {"type": "dropdown", "value1": "옵션1,옵션2"}}
        snapshot = [self._minimal_sheet(dataVerification=dv)]

        ops = [{"op": "replace", "path": ["dataVerification"], "value": dv, "id": "pe-log-main"}]
        save_resp = self.client.post(
            "/api/pe-log-sheet/ops/",
            {
                "base_revision": revision,
                "ops": ops,
                "snapshot": snapshot,
                "client_id": "test-client",
            },
            format="json",
        )
        self.assertEqual(save_resp.status_code, 200)

        # Reload and verify
        get_resp = self.client.get("/api/pe-log-sheet/state/")
        self.assertEqual(get_resp.status_code, 200)
        sheets = get_resp.data["workbook_data"]
        self.assertTrue(len(sheets) > 0, "workbook_data must not be empty")
        self.assertEqual(
            sheets[0].get("dataVerification"),
            dv,
            msg="GET /state/ returned workbook_data without dataVerification",
        )
