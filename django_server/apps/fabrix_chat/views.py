"""
FabriX Chat Views
LLM 모델 기반 채팅 API
"""
import time
import httpx
import logging
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import ChatSession, ChatMessage, MemorySnapshot
from .serializers import (
    ChatSessionSerializer, ChatSessionDetailSerializer, ChatMessageSerializer,
    MemorySnapshotSerializer, MemorySnapshotDetailSerializer
)

logger = logging.getLogger(__name__)


def safe_log_info(message):
    """Windows 콘솔에서 cp949 인코딩 에러를 방지하기 위해 안전하게 로깅"""
    try:
        logger.info(message)
    except UnicodeEncodeError:
        safe_message = message.encode('ascii', errors='replace').decode('ascii')
        logger.info(safe_message)


class ModelListView(APIView):
    """
    FabriX Chat API에서 사용 가능한 Model 목록 조회
    
    Response 구조:
    {
        "items": [
            {
                "modelId": "uuid",
                "name": [{"languageCode": "ko", "content": "모델명"}, ...],
                "description": [{"languageCode": "ko", "content": "설명"}, ...]
            },
            ...
        ]
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def _normalize_models_data(self, models):
        """Model 목록 normalize"""
        if not models:
            return []
            
        for model in models:
            # modelId 필드 normalize
            if 'modelId' not in model:
                model['modelId'] = (
                    model.get('id') or
                    model.get('model_id') or
                    model.get('modelID') or
                    model.get('uuid') or
                    ''
                )
            # displayName 계산 (다국어 배열 처리)
            if 'displayName' not in model:
                name_list = model.get('name', [])
                if isinstance(name_list, list) and len(name_list) > 0:
                    # 한국어 우선, 없으면 영어, 없으면 첫 번째
                    ko_name = next((n.get('content') for n in name_list if n.get('languageCode') == 'ko'), None)
                    en_name = next((n.get('content') for n in name_list if n.get('languageCode') == 'en'), None)
                    model['displayName'] = ko_name or en_name or (name_list[0].get('content') if name_list else model['modelId'])
                elif isinstance(name_list, str):
                    model['displayName'] = name_list
                else:
                    model['displayName'] = model.get('modelId', 'Unknown Model')
        return models

    def get(self, request):
        fabrix_conf = getattr(settings, 'FABRIX_CHAT_API_CONFIG', {})
        
        logger.info(f"[ModelList] Loaded config keys: {fabrix_conf.keys()}")
        
        base_url = fabrix_conf.get('base_url', '').rstrip('/')
        if not base_url:
            logger.error("[ModelList] Missing 'base_url' in FABRIX_CHAT_API_CONFIG")
            return JsonResponse(
                {'error': 'FabriX Chat API configuration error: missing base_url. Check secrets.toml file.'},
                status=500
            )
        
        target_url = f"{base_url}/openapi/chat/v1/models"
        logger.info(f"[ModelList] Target URL: {target_url}")
        
        headers = {
            'Content-Type': 'application/json',
            'x-fabrix-client': fabrix_conf.get('client_key', ''),
            'x-openapi-token': fabrix_conf.get('openapi_token', ''),
            'x-generative-ai-user-email': fabrix_conf.get('user_email', ''),
        }
        headers = {k: v for k, v in headers.items() if v is not None and v != ''}
        
        logger.info(f"[ModelList] Request headers (keys only): {list(headers.keys())}")
        
        max_retries = 2
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                client = getattr(settings, 'SHARED_HTTP_CLIENT', None)
                
                if client is None:
                    with httpx.Client(timeout=15.0) as new_client:
                        response = new_client.get(target_url, headers=headers)
                else:
                    response = client.get(target_url, headers=headers)
                
                response.raise_for_status()
                data = response.json()
                
                # FabriX API가 배열을 직접 반환하는 경우 처리
                if isinstance(data, list):
                    models = data
                elif isinstance(data, dict) and 'items' in data:
                    models = data['items']
                else:
                    models = []
                
                models = self._normalize_models_data(models)
                
                # 일관된 응답 형식: { items: [...] }
                return JsonResponse({'items': models}, status=response.status_code)
                
            except httpx.TimeoutException:
                retry_count += 1
                logger.warning(f"Timeout fetching models (attempt {retry_count}/{max_retries + 1})")
                if retry_count > max_retries:
                    return JsonResponse(
                        {'error': 'Request timeout to FabriX Chat API after retries'},
                        status=504
                    )
                time.sleep(0.5)
                continue
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching models: {e.response.status_code}")
                return JsonResponse(
                    {'error': str(e), 'status_code': e.response.status_code},
                    status=e.response.status_code
                )
            except httpx.ConnectError as e:
                retry_count += 1
                logger.warning(f"Connection error fetching models (attempt {retry_count}/{max_retries + 1}): {e}")
                if retry_count > max_retries:
                    return JsonResponse(
                        {'error': f'Connection failed to FabriX Chat API: {str(e)}'},
                        status=503
                    )
                time.sleep(0.5)
                continue
            except Exception as e:
                logger.exception(f"Unexpected error fetching models: {e}")
                return JsonResponse(
                    {'error': f'Failed to fetch models: {str(e)}'},
                    status=500
                )


class ChatSessionViewSet(viewsets.ModelViewSet):
    """
    FabriX Chat 세션 ViewSet
    """
    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        """Override create to add logging for debugging 400 errors"""
        safe_log_info(f"[ChatSession CREATE] Request data: {request.data}")
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"[ChatSession CREATE] Validation errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        queryset = ChatSession.objects.filter(user=self.request.user)
        if self.action == 'retrieve':
            queryset = queryset.prefetch_related('messages')
        elif self.action == 'list':
            queryset = queryset.select_related('user')
        return queryset

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ChatSessionDetailSerializer
        return ChatSessionSerializer

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def messages(self, request, pk=None):
        """세션에 메시지 추가"""
        safe_log_info(f"[ChatMessage CREATE] Session ID: {pk}, Request data: {request.data}")
        
        role = request.data.get('role', '')
        content = request.data.get('content', '')
        
        # assistant 메시지의 경우 빈 내용은 저장하지 않음
        if role == 'assistant' and not content.strip():
            logger.warning(f"[ChatMessage CREATE] Skipping empty assistant message for session {pk}")
            return Response({'id': None, 'role': 'assistant', 'content': '', 'skipped': True}, status=status.HTTP_200_OK)
        
        data = request.data.copy()
        data['content'] = content
        
        session = self.get_object()
        serializer = ChatMessageSerializer(data=data)
        if serializer.is_valid():
            serializer.save(session=session)
            session.save()  # Update session's updated_at timestamp
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        logger.warning(f"[ChatMessage CREATE] Validation errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # ===== Memory Snapshot Actions =====

    @action(detail=True, methods=['get', 'post'], url_path='memory-snapshots')
    def memory_snapshots(self, request, pk=None):
        """
        GET: 세션의 스냅샷 목록 조회 (?name=xxx로 필터 가능)
        POST: 새 스냅샷 저장
        """
        session = self.get_object()

        if request.method == 'GET':
            snapshots = MemorySnapshot.objects.filter(
                chat_session=session,
                user=request.user
            )
            name_filter = request.query_params.get('name')
            if name_filter:
                snapshots = snapshots.filter(name__iexact=name_filter)
            serializer = MemorySnapshotSerializer(snapshots, many=True)
            return Response(serializer.data)

        # POST: 스냅샷 생성
        serializer = MemorySnapshotDetailSerializer(data=request.data)
        if serializer.is_valid():
            try:
                serializer.save(user=request.user, chat_session=session)
                safe_log_info(f"[MemorySnapshot] Created: {serializer.data.get('name')} for session {pk}")
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except Exception as e:
                logger.error(f"[MemorySnapshot] Failed to create: {e}")
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'], url_path='memory-snapshots/(?P<snapshot_id>[^/.]+)')
    def memory_snapshot_detail(self, request, pk=None, snapshot_id=None):
        """개별 스냅샷 상세 조회 (snapshot_data 포함)"""
        session = self.get_object()
        try:
            snapshot = MemorySnapshot.objects.get(
                id=snapshot_id,
                chat_session=session,
                user=request.user
            )
        except MemorySnapshot.DoesNotExist:
            return Response({'error': '스냅샷을 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = MemorySnapshotDetailSerializer(snapshot)
        return Response(serializer.data)

    @action(detail=True, methods=['delete'], url_path='memory-snapshots/clear')
    @transaction.atomic
    def clear_snapshots(self, request, pk=None):
        """/memory clear 명령용: 세션의 모든 스냅샷 삭제"""
        session = self.get_object()
        count, _ = MemorySnapshot.objects.filter(
            chat_session=session,
            user=request.user
        ).delete()
        safe_log_info(f"[MemorySnapshot] Cleared {count} snapshots for session {pk}")
        return Response({
            'deleted': count,
            'message': f'{count}개의 스냅샷이 삭제되었습니다.'
        })

    @action(detail=True, methods=['delete'], url_path='memory-snapshots/(?P<snapshot_id>[^/.]+)/delete')
    @transaction.atomic
    def delete_snapshot(self, request, pk=None, snapshot_id=None):
        """/memory delete 명령용: 개별 스냅샷 삭제"""
        session = self.get_object()
        try:
            snapshot = MemorySnapshot.objects.get(
                id=snapshot_id,
                chat_session=session,
                user=request.user
            )
            name = snapshot.name
            snapshot.delete()
            safe_log_info(f"[MemorySnapshot] Deleted '{name}' from session {pk}")
            return Response({
                'deleted': True,
                'name': name,
                'message': f'스냅샷 "{name}"이 삭제되었습니다.'
            })
        except MemorySnapshot.DoesNotExist:
            return Response({'error': '스냅샷을 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
