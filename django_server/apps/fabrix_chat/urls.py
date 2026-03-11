from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChatSessionViewSet, ModelListView, DashboardLinkListView, DashboardLinkBulkUpdateView

router = DefaultRouter()
router.register(r'sessions', ChatSessionViewSet, basename='chat-session')

urlpatterns = [
    # Model List Proxy API
    path('models/', ModelListView.as_view(), name='model-list'),
    path('dashboard-links/', DashboardLinkListView.as_view(), name='dashboard-link-list'),
    path('dashboard-links/bulk/', DashboardLinkBulkUpdateView.as_view(), name='dashboard-link-bulk'),
    
    # Chat Session API
    path('', include(router.urls)),
]
