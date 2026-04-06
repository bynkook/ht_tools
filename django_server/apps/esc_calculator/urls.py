from django.urls import path
from .views import (
    EscProjectListCreateView,
    EscProjectDetailView,
    KosisPpiView,
    KosisWageView,
    KosisCacheResetView,
)

urlpatterns = [
    path('projects/', EscProjectListCreateView.as_view(), name='esc-project-list-create'),
    path('projects/<int:pk>/', EscProjectDetailView.as_view(), name='esc-project-detail'),
    path('kosis/ppi/', KosisPpiView.as_view(), name='esc-kosis-ppi'),
    path('kosis/wage/', KosisWageView.as_view(), name='esc-kosis-wage'),
    path('kosis/cache/reset/', KosisCacheResetView.as_view(), name='esc-kosis-cache-reset'),
]
