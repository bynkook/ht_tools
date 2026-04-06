from django.conf import settings
from rest_framework.views import APIView
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import EscProject, KosisCache
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


class KosisCacheResetView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data_type = request.data.get('data_type', KosisCache.DATA_TYPE_WAGE)
        if data_type not in {KosisCache.DATA_TYPE_PPI, KosisCache.DATA_TYPE_WAGE, 'all'}:
            return Response(
                {'error': 'data_type 은 ppi, wage, all 중 하나여야 합니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = KosisCache.objects.all()
        if data_type != 'all':
            queryset = queryset.filter(data_type=data_type)

        deleted_count, _ = queryset.delete()
        return Response({'deleted': deleted_count, 'data_type': data_type})
