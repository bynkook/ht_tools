from django.urls import path
from .views import (
    DatasetInitView,
    DatasetQueryView,
    DatasetListView,
    DatasetUploadView,
    DatasetPreviewView,
    PresetListCreateView,
    PresetDetailView,
    CacheStatusView,
    RebuildStartView,
    RebuildStatusView,
)

urlpatterns = [
    # Dataset endpoints
    path('datasets/', DatasetListView.as_view(), name='dataset-list'),
    path('init-session/', DatasetInitView.as_view(), name='dataset-init'),
    path('query/', DatasetQueryView.as_view(), name='dataset-query'),
    path('upload/', DatasetUploadView.as_view(), name='dataset-upload'),
    path('preview/', DatasetPreviewView.as_view(), name='dataset-preview'),
    
    # Preset endpoints
    path('presets/', PresetListCreateView.as_view(), name='preset-list-create'),
    path('presets/<int:preset_id>/', PresetDetailView.as_view(), name='preset-detail'),
    
    # Cache rebuild endpoints
    path('cache-status/', CacheStatusView.as_view(), name='cache-status'),
    path('rebuild/start/', RebuildStartView.as_view(), name='rebuild-start'),
    path('rebuild/status/<str:task_id>/', RebuildStatusView.as_view(), name='rebuild-status'),
]
