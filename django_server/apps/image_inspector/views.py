import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions

logger = logging.getLogger(__name__)


class ImageInspectorStatusView(APIView):
    """
    Image Inspector 앱 상태 확인 및 권한 검증 API
    (FastAPI로 직접 호출되므로, Django는 메타데이터 관리만 담당)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({
            "status": "active",
            "service": "Image Inspector",
            "user": request.user.username,
            "fastapi_endpoint": "http://localhost:8001/image-compare/process"
        })
