from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChatRuntimeConfigView, ChatSessionViewSet, ModelListView

router = DefaultRouter()
router.register(r'sessions', ChatSessionViewSet, basename='chat-session')

urlpatterns = [
    path('runtime-config/', ChatRuntimeConfigView.as_view(), name='chat-runtime-config'),
    # Model List Proxy API
    path('models/', ModelListView.as_view(), name='model-list'),
    
    # Chat Session API
    path('', include(router.urls)),
]
