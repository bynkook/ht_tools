import json
import os
from queue import Empty

from django.conf import settings
from django.db import transaction
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PeLogSheetState, PeLogSheetRevision
from .serializers import PeLogSheetOpsSerializer
from .services.csv_loader import csv_to_workbook, compute_csv_checksum
from .services.stream_hub import get_hub


def _csv_path() -> str:
    path = os.path.join(settings.BASE_DIR, '..', 'data', 'pe_log', 'pe_log.csv')
    return os.path.normpath(path)


def _get_or_init_state() -> PeLogSheetState:
    """Return singleton state, auto-initialising from CSV on first access."""
    state, created = PeLogSheetState.objects.get_or_create(
        singleton_key='main',
        defaults={'workbook_data': [], 'revision': 0},
    )
    if created or not state.workbook_data:
        state.workbook_data = csv_to_workbook(_csv_path())
        state.source_checksum = compute_csv_checksum(_csv_path())
        state.save()
    return state


class SheetStateView(APIView):
    """GET — return the current workbook snapshot and revision."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        state = _get_or_init_state()
        return Response({
            'revision': state.revision,
            'workbook_data': state.workbook_data,
            'last_editor': state.last_editor.username if state.last_editor else None,
            'updated_at': state.updated_at.isoformat() if state.updated_at else None,
        })


class SheetOpsView(APIView):
    """POST — commit an op batch. Rejects stale writes with 409 Conflict."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PeLogSheetOpsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        base_revision = serializer.validated_data['base_revision']
        ops = serializer.validated_data['ops']
        snapshot = serializer.validated_data.get('snapshot')
        client_id = serializer.validated_data.get('client_id', '')

        with transaction.atomic():
            try:
                state = PeLogSheetState.objects.select_for_update().get(singleton_key='main')
            except PeLogSheetState.DoesNotExist:
                state = _get_or_init_state()
                state = PeLogSheetState.objects.select_for_update().get(singleton_key='main')

            if state.revision != base_revision:
                return Response(
                    {
                        'error': 'conflict',
                        'revision': state.revision,
                        'workbook_data': state.workbook_data,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            new_revision = state.revision + 1

            if snapshot:
                state.workbook_data = snapshot
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

        get_hub().broadcast({
            'type': 'op_committed',
            'revision': new_revision,
            'ops': ops,
            'client_id': client_id,
            'editor': request.user.username,
        })

        return Response({'new_revision': new_revision})


class SheetStreamView(APIView):
    """GET — SSE endpoint for real-time revision events."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        hub = get_hub()
        q = hub.subscribe()

        def event_generator():
            try:
                yield f"data: {json.dumps({'type': 'connected'})}\n\n"
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
            content_type='text/event-stream',
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


class SheetResetView(APIView):
    """POST — re-initialise the sheet from the canonical CSV source."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        csv_file = _csv_path()

        with transaction.atomic():
            state, _ = PeLogSheetState.objects.select_for_update().get_or_create(
                singleton_key='main',
            )
            state.workbook_data = csv_to_workbook(csv_file)
            state.revision = state.revision + 1
            state.source_checksum = compute_csv_checksum(csv_file)
            state.last_editor = request.user
            state.save()

        get_hub().broadcast({
            'type': 'reset',
            'revision': state.revision,
        })

        return Response({
            'revision': state.revision,
            'message': 'CSV 기준으로 시트가 재초기화되었습니다.',
        })
