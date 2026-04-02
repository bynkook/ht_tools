import re
import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ConversionJob
from .serializers import ConversionJobSerializer, ConversionJobCreateSerializer

logger = logging.getLogger(__name__)

MAX_JOBS = 100  # 보관할 최대 작업 건수

# Windows 파일명 불법 문자 및 예약어 검증
_WIN_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WIN_RESERVED = re.compile(
    r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$',
    re.IGNORECASE,
)


def _is_valid_windows_folder_name(name: str) -> bool:
    """Windows OS 표준 폴더명 규칙으로 검증"""
    if not name or not name.strip() or len(name) > 255:
        return False
    if _WIN_ILLEGAL.search(name):
        return False
    if _WIN_RESERVED.match(name):
        return False
    if name.endswith('.') or name.endswith(' '):
        return False
    return True


class JobListView(APIView):
    """
    GET /api/doc-uploader/jobs/
    최근 100건 변환 작업 목록 반환. 초과분은 오래된 completed/failed 부터 자동 삭제.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 자동 정리: 최근 MAX_JOBS 건 초과 시 오래된 완료/실패 job 삭제
        total = ConversionJob.objects.count()
        if total > MAX_JOBS:
            keep_ids = list(
                ConversionJob.objects.order_by('-created_at')
                .values_list('id', flat=True)[:MAX_JOBS]
            )
            ConversionJob.objects.exclude(id__in=keep_ids).filter(
                status__in=[ConversionJob.STATUS_COMPLETED, ConversionJob.STATUS_FAILED]
            ).delete()

        jobs = ConversionJob.objects.order_by('-created_at')[:MAX_JOBS]
        serializer = ConversionJobSerializer(jobs, many=True)
        return Response(serializer.data)


class CategoryListCreateView(APIView):
    """
    GET  /api/doc-uploader/categories/   — 카테고리(폴더) 목록 + .md 파일수 반환
    POST /api/doc-uploader/categories/   — 새 카테고리 폴더 생성
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        doc_data_dir = Path(settings.DOC_DATA_DIR)
        categories = []
        if doc_data_dir.exists():
            for item in sorted(doc_data_dir.iterdir()):
                if item.is_dir():
                    file_count = sum(1 for f in item.iterdir() if f.suffix == '.md')
                    categories.append({'name': item.name, 'file_count': file_count})
        return Response(categories)

    def post(self, request):
        name = request.data.get('name', '').strip()
        if not _is_valid_windows_folder_name(name):
            return Response(
                {'error': f"유효하지 않은 폴더명입니다: '{name}'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        doc_data_dir = Path(settings.DOC_DATA_DIR)
        new_dir = doc_data_dir / name
        if new_dir.exists():
            return Response(
                {'error': f"이미 존재하는 폴더입니다: '{name}'"},
                status=status.HTTP_409_CONFLICT,
            )

        new_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Category created: %s", new_dir)
        return Response({'name': name, 'file_count': 0}, status=status.HTTP_201_CREATED)


class CategoryRenameView(APIView):
    """
    PATCH /api/doc-uploader/categories/<name>/
    카테고리 폴더 이름 변경 (삭제 불가).
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, name):
        new_name = request.data.get('new_name', '').strip()
        if not _is_valid_windows_folder_name(new_name):
            return Response(
                {'error': f"유효하지 않은 새 폴더명입니다: '{new_name}'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        doc_data_dir = Path(settings.DOC_DATA_DIR)
        old_dir = doc_data_dir / name
        new_dir = doc_data_dir / new_name

        if not old_dir.exists():
            return Response({'error': '폴더를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
        if new_dir.exists():
            return Response(
                {'error': f"이미 존재하는 폴더명입니다: '{new_name}'"},
                status=status.HTTP_409_CONFLICT,
            )

        old_dir.rename(new_dir)
        file_count = sum(1 for f in new_dir.iterdir() if f.suffix == '.md')
        logger.info("Category renamed: %s → %s", name, new_name)
        return Response({'name': new_name, 'file_count': file_count})


class JobCallbackView(APIView):
    """
    PATCH /api/doc-uploader/jobs/callback/<uuid:token>/
    FastAPI 변환 완료 후 상태 업데이트. 일반 Auth 없음 — callback_token으로만 보안.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def patch(self, request, token):
        try:
            job = ConversionJob.objects.get(callback_token=token)
        except ConversionJob.DoesNotExist:
            return Response({'error': '유효하지 않은 토큰입니다.'}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('status')
        allowed = {ConversionJob.STATUS_WORKING, ConversionJob.STATUS_COMPLETED, ConversionJob.STATUS_FAILED}
        if new_status not in allowed:
            return Response({'error': '유효하지 않은 상태입니다.'}, status=status.HTTP_400_BAD_REQUEST)

        job.status = new_status
        job.error_message = request.data.get('error_message', '') or ''
        job.save(update_fields=['status', 'error_message'])
        return Response({'id': job.id, 'status': job.status})


class JobInternalCreateView(APIView):
    """
    POST /api/doc-uploader/jobs/internal/
    FastAPI가 내부적으로 변환 작업을 생성하는 전용 뷰.
    X-Internal-Secret 헤더로 인증 (일반 Auth 없음).
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        internal_secret = request.META.get('HTTP_X_INTERNAL_SECRET', '')
        expected = getattr(settings, 'DOC_CONVERTER_INTERNAL_SECRET', '')
        if not expected or internal_secret != expected:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ConversionJobCreateSerializer(
            data={
                'original_filename': request.data.get('original_filename', ''),
                'category_name': request.data.get('category_name', ''),
                'status': request.data.get('status', ConversionJob.STATUS_WAITING),
            }
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        job = serializer.save()
        return Response(
            {'id': job.id, 'callback_token': str(job.callback_token)},
            status=status.HTTP_201_CREATED,
        )


class JobStartupResetView(APIView):
    """
    POST /api/doc-uploader/jobs/startup-reset/
    FastAPI 시작 시 중단된 working job을 failed로 초기화.
    X-Internal-Secret 헤더 인증.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        internal_secret = request.META.get('HTTP_X_INTERNAL_SECRET', '')
        expected = getattr(settings, 'DOC_CONVERTER_INTERNAL_SECRET', '')
        if not expected or internal_secret != expected:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            count = ConversionJob.objects.filter(
                status=ConversionJob.STATUS_WORKING
            ).update(
                status=ConversionJob.STATUS_FAILED,
                error_message='서버 재시작으로 인해 변환이 중단되었습니다.',
            )

        logger.info("Startup reset: %d interrupted jobs marked as failed", count)
        return Response({'reset_count': count})
