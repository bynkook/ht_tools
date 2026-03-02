from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChatSessionViewSet, AgentListView

router = DefaultRouter()
router.register(r'sessions', ChatSessionViewSet, basename='session')

urlpatterns = [
    # Agent List Proxy API
    path('agents/', AgentListView.as_view(), name='agent-list'),
    
    # Chat API
    path('', include(router.urls)),
]