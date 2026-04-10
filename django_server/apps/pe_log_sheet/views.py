# pyright: reportAttributeAccessIssue=false, reportOptionalSubscript=false, reportGeneralTypeIssues=false, reportIndexIssue=false, reportOptionalMemberAccess=false, reportArgumentType=false
"""Views for PE log sheet collaboration APIs."""

import json
import logging
import os
from queue import Empty

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.views import View
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PeLogSheetState, PeLogSheetRevision
from .serializers import (
    PeLogSheetCellLockSerializer,
    PeLogSheetOpsSerializer,
    PeLogSheetPresenceSerializer,
)
from .services.cell_lock import DEFAULT_DOCUMENT_ID as CELL_LOCK_DOCUMENT_ID
from .services.cell_lock import get_cell_lock_registry
from .services.conflict_detector import (
    _cell_address,
    _extract_touched_cells,
    detect_conflicts,
    merge_ops_into_workbook,
)
from .services.csv_loader import (
    compute_csv_checksum,
    csv_to_workbook,
    csv_upload_to_workbook,
    has_structural_ops,
    is_workbook_schema_valid,
    normalize_workbook_data,
    workbook_to_csv_bytes,
)
from .services.presence import DEFAULT_DOCUMENT_ID, get_presence_registry
from .services.stream_hub import get_hub

logger = logging.getLogger(__name__)


def _csv_path() -> str:
    path = os.path.join(settings.BASE_DIR, "..", "data", "pe_log", "seed.csv")
    return os.path.normpath(path)


def _load_seed_workbook() -> list:
    return normalize_workbook_data(csv_to_workbook(_csv_path()))


def _seed_checksum() -> str:
    return compute_csv_checksum(_csv_path())


def _get_or_init_state() -> PeLogSheetState:
    """Return singleton state, auto-initialising from CSV on first access."""
    state, created = PeLogSheetState.objects.get_or_create(
        singleton_key="main",
        defaults={"workbook_data": [], "revision": 0},
    )
    if (
        created
        or not state.workbook_data
        or not is_workbook_schema_valid(state.workbook_data)
    ):
        if state.workbook_data and not is_workbook_schema_valid(state.workbook_data):
            logger.warning("Resetting stale PE Log Sheet state due to schema mismatch.")
            state.revision += 1
        state.workbook_data = _load_seed_workbook()
        state.source_checksum = _seed_checksum()
        state.save()
    else:
        normalized = normalize_workbook_data(state.workbook_data)
        if normalized != state.workbook_data:
            logger.info("Normalizing persisted PE Log Sheet workbook state.")
            state.workbook_data = normalized
            state.save(update_fields=["workbook_data", "updated_at"])
    return state


class SheetStateView(APIView):
    """GET — return the current workbook snapshot and revision."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        state = _get_or_init_state()
        return Response(
            {
                "revision": state.revision,
                "workbook_data": state.workbook_data,
                "last_editor": state.last_editor.username
                if state.last_editor
                else None,
                "updated_at": state.updated_at.isoformat()
                if state.updated_at
                else None,
            }
        )


class SheetOpsView(APIView):
    """POST — commit an op batch. Rejects stale writes with 409 Conflict."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PeLogSheetOpsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        base_revision = serializer.validated_data["base_revision"]
        ops = serializer.validated_data["ops"]
        snapshot = serializer.validated_data.get("snapshot")
        client_id = serializer.validated_data.get("client_id", "")

        with transaction.atomic():
            try:
                state = PeLogSheetState.objects.select_for_update().get(
                    singleton_key="main"
                )
            except PeLogSheetState.DoesNotExist:
                state = _get_or_init_state()
                state = PeLogSheetState.objects.select_for_update().get(
                    singleton_key="main"
                )

            # Cell-lock pre-check: if the ops resolve to exactly one cell-edit
            # target (no structural ops, batch_size == 1), check whether that
            # cell is locked by another client. If so, return 409 immediately
            # with conflict_type "cell-lock" so the frontend can restore
            # authoritative state. detect_conflicts() remains the second-line
            # guard for revision-gap conflicts after this check passes.
            touched = _extract_touched_cells(ops)
            if not touched["structural_ops"] and touched["batch_size"] == 1:
                (sheet_id, row, column), cell_info = next(
                    iter(touched["cells"].items())
                )
                owner = get_cell_lock_registry().owner_for_cell(
                    CELL_LOCK_DOCUMENT_ID, sheet_id, row, column
                )
                if owner is not None and owner["client_id"] != client_id:
                    logger.info(
                        "[SheetOpsView] cell-lock conflict: cell %s locked by %s, rejected %s",
                        _cell_address(row, column),
                        owner["client_id"],
                        client_id,
                    )
                    return Response(
                        {
                            "error": "conflict",
                            "conflict_type": "cell-lock",
                            "locked_cell": {
                                "sheet_id": sheet_id,
                                "row": row,
                                "column": column,
                                "cell_address": _cell_address(row, column),
                            },
                            "lock_owner": {
                                "username": owner["username"],
                                "display_name": owner["display_name"],
                                "client_id": owner["client_id"],
                            },
                            "revision": state.revision,
                            "workbook_data": state.workbook_data,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

            conflict_payload = detect_conflicts(state, base_revision, ops, snapshot)
            logger.info(
                "[SheetOpsView] base_revision=%s, state.revision=%s, ops_count=%s, has_structural=%s, conflict=%s",
                base_revision,
                state.revision,
                len(ops) if ops else 0,
                has_structural_ops(ops),
                "yes" if conflict_payload else "no",
            )
            if conflict_payload:
                return Response(
                    {
                        "error": "conflict",
                        **conflict_payload,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            new_revision = state.revision + 1

            if (
                state.revision == base_revision
                and snapshot
                and not has_structural_ops(ops)
            ):
                state.workbook_data = normalize_workbook_data(snapshot)
            elif ops:
                state.workbook_data = merge_ops_into_workbook(state.workbook_data, ops)
            state.revision = new_revision
            state.last_editor = request.user
            state.save()

            PeLogSheetRevision.objects.create(
                document=state,
                base_revision=base_revision,
                new_revision=new_revision,
                ops=ops,
                editor=request.user,
            )

        get_hub().broadcast(
            {
                "type": "op_committed",
                "revision": new_revision,
                "ops": ops,
                "client_id": client_id,
                "editor": request.user.username,
            }
        )

        return Response({"new_revision": new_revision})


def _presence_payload(event_type: str, active_users: list[dict]) -> dict:
    return {
        "type": event_type,
        "document_id": DEFAULT_DOCUMENT_ID,
        "active_users": active_users,
    }


class SheetPresenceJoinView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PeLogSheetPresenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Join is the primary visibility trigger. The request response applies the
        # authoritative local presence result immediately, and SSE snapshots fan
        # that state out to other subscribers.
        active_users = get_presence_registry().join(
            DEFAULT_DOCUMENT_ID,
            serializer.validated_data["client_id"],
            request.user,
        )
        get_hub().broadcast(_presence_payload("presence_snapshot", active_users))
        return Response(
            {
                "active_users": active_users,
                "joined_user": {
                    "username": request.user.username,
                    "display_name": request.user.username,
                },
            }
        )


class SheetPresenceHeartbeatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PeLogSheetPresenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Heartbeat is TTL refresh only. It does not recreate missing presence
        # entries after an abrupt disconnect expiry; a fresh join is required.
        active_users, changed = get_presence_registry().heartbeat(
            DEFAULT_DOCUMENT_ID,
            serializer.validated_data["client_id"],
            request.user,
        )
        if changed:
            get_hub().broadcast(_presence_payload("presence_snapshot", active_users))
        return Response({"active_users": active_users})


class SheetPresenceLeaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PeLogSheetPresenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Disconnect cleanup boundary for the upcoming cell-lock registry:
        # `SheetPresenceLeaveView` must also call
        # `release_all(DEFAULT_DOCUMENT_ID, client_id)` so abrupt exits clear any
        # active text-edit lock held by that client before presence is broadcast.
        get_cell_lock_registry().release_all(
            CELL_LOCK_DOCUMENT_ID,
            serializer.validated_data["client_id"],
        )
        active_users = get_presence_registry().leave(
            DEFAULT_DOCUMENT_ID,
            serializer.validated_data["client_id"],
        )
        get_hub().broadcast(_presence_payload("presence_snapshot", active_users))
        return Response({"active_users": active_users})


class SheetCellLockAcquireView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PeLogSheetCellLockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client_id = serializer.validated_data["client_id"]
        sheet_id = serializer.validated_data["sheet_id"]
        row = serializer.validated_data["row"]
        column = serializer.validated_data["column"]

        lock_info, is_new = get_cell_lock_registry().acquire(
            CELL_LOCK_DOCUMENT_ID,
            sheet_id,
            row,
            column,
            client_id,
            request.user,
        )

        if is_new or lock_info.get("client_id") == client_id:
            return Response({"lock": lock_info, "is_new": is_new})

        state = _get_or_init_state()
        return Response(
            {
                "error": "conflict",
                "conflict_type": "cell-lock",
                "locked_cell": {
                    "sheet_id": sheet_id,
                    "row": row,
                    "column": column,
                    "cell_address": _cell_address(row, column),
                },
                "lock_owner": {
                    "username": lock_info.get("username"),
                    "display_name": lock_info.get("display_name"),
                    "client_id": lock_info.get("client_id"),
                },
                "revision": state.revision,
                "workbook_data": state.workbook_data,
            },
            status=status.HTTP_409_CONFLICT,
        )


class SheetCellLockHeartbeatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PeLogSheetCellLockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        lock_info, refreshed = get_cell_lock_registry().heartbeat(
            CELL_LOCK_DOCUMENT_ID,
            serializer.validated_data["client_id"],
            serializer.validated_data["sheet_id"],
            serializer.validated_data["row"],
            serializer.validated_data["column"],
        )
        return Response({"lock": lock_info, "refreshed": refreshed})


class SheetCellLockReleaseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PeLogSheetCellLockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        get_cell_lock_registry().release(
            CELL_LOCK_DOCUMENT_ID,
            serializer.validated_data["client_id"],
            serializer.validated_data["sheet_id"],
            serializer.validated_data["row"],
            serializer.validated_data["column"],
        )
        return Response({"released": True})


def _authenticate_stream_request(request):
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Token "):
        return None

    token_key = auth_header.split(" ", 1)[1].strip()
    if not token_key:
        return None

    try:
        user, token = TokenAuthentication().authenticate_credentials(token_key)
    except AuthenticationFailed:
        return None

    request.user = user
    request.auth = token
    return user


class SheetStreamSseView(View):
    """GET — token-authenticated SSE endpoint without DRF content negotiation."""

    http_method_names = ["get"]

    def dispatch(self, request, *args, **kwargs):
        if _authenticate_stream_request(request) is None:
            return JsonResponse(
                {"detail": "Authentication credentials were not provided."}, status=401
            )
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        hub = get_hub()
        q = hub.subscribe()

        def event_generator():
            try:
                active_users = get_presence_registry().snapshot(DEFAULT_DOCUMENT_ID)
                yield f"data: {json.dumps({'type': 'connected'})}\n\n"
                yield f"data: {json.dumps(_presence_payload('presence_snapshot', active_users))}\n\n"
                while True:
                    try:
                        data = q.get(timeout=30)
                        yield f"data: {json.dumps(data)}\n\n"
                    except Empty:
                        yield ": heartbeat\n\n"
            except GeneratorExit:
                pass
            finally:
                hub.unsubscribe(q)

        response = StreamingHttpResponse(
            event_generator(),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class SheetResetView(APIView):
    """POST — re-initialise the sheet from the canonical CSV source."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        csv_file = _csv_path()

        with transaction.atomic():
            state, _ = PeLogSheetState.objects.select_for_update().get_or_create(
                singleton_key="main",
            )
            state.workbook_data = normalize_workbook_data(csv_to_workbook(csv_file))
            state.revision = state.revision + 1
            state.source_checksum = compute_csv_checksum(csv_file)
            state.last_editor = request.user
            state.save()

        get_hub().broadcast(
            {
                "type": "reset",
                "revision": state.revision,
            }
        )

        return Response(
            {
                "revision": state.revision,
                "message": "CSV 기준으로 시트가 재초기화되었습니다.",
            }
        )


class SheetCsvUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response(
                {"error": "CSV 파일이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST
            )
        if not uploaded_file.name.lower().endswith(".csv"):
            return Response(
                {"error": "CSV 파일만 업로드할 수 있습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            workbook_data = csv_upload_to_workbook(uploaded_file)
        except (UnicodeDecodeError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            state, _ = PeLogSheetState.objects.select_for_update().get_or_create(
                singleton_key="main",
            )
            state.workbook_data = normalize_workbook_data(workbook_data)
            state.revision = state.revision + 1
            state.source_checksum = ""
            state.last_editor = request.user
            state.save()

        get_hub().broadcast(
            {
                "type": "reset",
                "revision": state.revision,
            }
        )

        return Response(
            {
                "revision": state.revision,
                "workbook_data": state.workbook_data,
                "message": "CSV 업로드가 완료되었습니다.",
            }
        )


class SheetCsvDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        state = _get_or_init_state()
        csv_bytes = workbook_to_csv_bytes(state.workbook_data)
        response = HttpResponse(csv_bytes, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="pe_log_sheet.csv"'
        return response
