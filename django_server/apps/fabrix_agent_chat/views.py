import httpx
import logging
import re
import time
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, logout as auth_logout
from .models import ChatSession, ChatMessage, MemorySnapshot
from .serializers import (
    ChatSessionSerializer, ChatSessionDetailSerializer, ChatMessageSerializer,
    MemorySnapshotSerializer, MemorySnapshotDetailSerializer
)

logger = logging.getLogger(__name__)


# Windows cp949 인코딩 문제 해결을 위한 안전한 로깅 함수
def safe_log_info(message):
    """Windows 콘솔에서 cp949 인코딩 에러를 방지하기 위해 안전하게 로깅"""
    try:
        logger.info(message)
    except UnicodeEncodeError:
        # 유니코드 문자를 ASCII로 대체하여 로깅
        safe_message = message.encode('ascii', errors='replace').decode('ascii')
        logger.info(safe_message)


# [추가] Agent 목록 조회
class AgentListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _normalize_agents_data(self, data):
        logger.info(f"[AgentList] FabriX API Raw Response keys: {data.keys() if isinstance(data, dict) else type(data)}")
        if 'items' in data and isinstance(data['items'], list):
            if len(data['items']) > 0:
                logger.info(f"[AgentList] First agent object keys: {data['items'][0].keys()}")
            for agent in data['items']:
                # agentId 필드 normalize - 가능한 모든 ID 필드명 처리
                if 'agentId' not in agent:
                    agent['agentId'] = (
                        agent.get('id') or
                        agent.get('agent_id') or
                        agent.get('agentID') or
                        agent.get('uuid') or
                        ''
                    )
                # name 필드 normalize
                if 'name' not in agent:
                    agent['name'] = (
                        agent.get('label') or 
                        agent.get('agentName') or 
                        agent.get('displayName') or 
                        agent.get('agentId', 'Unknown Agent')
                    )
        return data

    def get(self, request):
        # settings.py의 SECRETS를 통해 로드된 설정 사용
        fabrix_conf = getattr(settings, 'FABRIX_AGENT_API_CONFIG', {})
        
        # 설정 값 로깅 (디버깅용)
        logger.info(f"[AgentList] Loaded config keys: {fabrix_conf.keys()}")
        
        # 필수 설정 검증
        base_url = fabrix_conf.get('base_url', '').rstrip('/')
        if not base_url:
            logger.error("[AgentList] Missing 'base_url' in FABRIX_AGENT_API_CONFIG")
            return JsonResponse(
                {'error': 'FabriX API configuration error: missing base_url. Check secrets.toml file.'},
                status=500
            )
        
        target_url = f"{base_url}/openapi/agent-chat/v1/agents"
        logger.info(f"[AgentList] Target URL: {target_url}")
        
        # 헤더 구성 (None 값 필터링)
        headers = {
            'Content-Type': 'application/json',
            'x-fabrix-client': fabrix_conf.get('client_key', ''),
            'x-openapi-token': fabrix_conf.get('openapi_token', ''),
            'x-generative-ai-user-email': fabrix_conf.get('user_email', ''),
        }
        # None 값 제거 (httpx는 None 값을 헤더로 받지 않음)
        headers = {k: v for k, v in headers.items() if v is not None and v != ''}
        
        logger.info(f"[AgentList] Request headers (keys only): {list(headers.keys())}")
        
        # Retry logic for better reliability
        max_retries = 2
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # settings에서 공유 HTTP 클라이언트 사용 (연결 재사용)
                http_client = getattr(settings, 'SHARED_HTTP_CLIENT', None)
                
                # Fetch parameters
                params = {'page': 1, 'limit': 100}
                
                if http_client is None:
                    with httpx.Client(timeout=15.0) as client:
                        response = client.get(target_url, headers=headers, params=params)
                else:
                    response = http_client.get(target_url, headers=headers, params=params)
                
                response.raise_for_status()
                
                # FabriX API 응답 normalize
                data = response.json()
                data = self._normalize_agents_data(data)
                
                return JsonResponse(data, status=response.status_code, safe=False)
                
            except httpx.TimeoutException:
                retry_count += 1
                logger.warning(f"Timeout fetching agents (attempt {retry_count}/{max_retries + 1})")
                if retry_count > max_retries:
                    return JsonResponse(
                        {'error': 'Request timeout to FabriX API after retries'},
                        status=504
                    )
                time.sleep(0.5)
                continue
            except httpx.HTTPStatusError as e:
                # Don't retry on HTTP errors (4xx, 5xx)
                logger.error(f"HTTP error fetching agents: {e.response.status_code}")
                return JsonResponse(
                    {'error': str(e), 'status_code': e.response.status_code},
                    status=e.response.status_code
                )
            except httpx.ConnectError as e:
                retry_count += 1
                logger.warning(f"Connection error fetching agents (attempt {retry_count}/{max_retries + 1}): {e}")
                if retry_count > max_retries:
                    return JsonResponse(
                        {'error': f'Connection failed to FabriX API: {str(e)}'},
                        status=503
                    )
                time.sleep(0.5)
                continue
            except Exception as e:
                logger.exception(f"Unexpected error fetching agents: {e}")
                return JsonResponse(
                    {'error': f'Failed to fetch agents: {str(e)}'},
                    status=500
                )

class ChatSessionViewSet(viewsets.ModelViewSet):
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
        # Optimize queries based on action
        if self.action == 'retrieve':
            # Prefetch messages for detail view to avoid N+1 queries
            queryset = queryset.prefetch_related('messages')
        elif self.action == 'list':
            # Only select related user for list view
            queryset = queryset.select_related('user')
        return queryset

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ChatSessionDetailSerializer
        return ChatSessionSerializer

    @action(detail=True, methods=['post'])
    @transaction.atomic  # Ensure atomicity for message creation and session update
    def messages(self, request, pk=None):
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