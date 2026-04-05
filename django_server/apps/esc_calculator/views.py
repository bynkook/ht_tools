from django.conf import settings
from rest_framework.views import APIView
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import EscProject
from .serializers import EscProjectSerializer
from .services.kosis_service import KosisService


# ---------------------------------------------------------------------------
# ESC Project CRUD
# ---------------------------------------------------------------------------

class EscProjectListCreateView(ListCreateAPIView):
    serializer_class = EscProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return EscProject.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class EscProjectDetailView(RetrieveUpdateDestroyAPIView):
    serializer_class = EscProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return EscProject.objects.filter(user=self.request.user)


# ---------------------------------------------------------------------------
# KOSIS Data Proxy
# ---------------------------------------------------------------------------

class KosisPpiView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start = request.query_params.get('start', '')
        end = request.query_params.get('end', '')
        if not start or not end:
            return Response({'error': 'start, end 파라미터가 필요합니다 (YYYYMM)'}, status=status.HTTP_400_BAD_REQUEST)

        api_key = getattr(settings, 'KOSIS_API_KEY', '')
        service = KosisService(api_key)
        try:
            data = service.get_ppi(start, end)
            return Response(data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_502_BAD_GATEWAY)


class KosisWageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start = request.query_params.get('start', '')
        end = request.query_params.get('end', '')
        if not start or not end:
            return Response({'error': 'start, end 파라미터가 필요합니다 (YYYYMM)'}, status=status.HTTP_400_BAD_REQUEST)

        api_key = getattr(settings, 'KOSIS_API_KEY', '')
        service = KosisService(api_key)
        try:
            data = service.get_wage(start, end)
            return Response(data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_502_BAD_GATEWAY)
