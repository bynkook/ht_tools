"""Tests for PE log sheet behavior."""

# pyright: reportAttributeAccessIssue=false, reportOptionalSubscript=false

from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import PeLogSheetState
from .services.csv_loader import (
    DEFAULT_HEADERS,
    get_cell_payload,
    normalize_workbook_data,
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
