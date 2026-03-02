from django.urls import path
from .views import ImageInspectorStatusView

urlpatterns = [
    path('status/', ImageInspectorStatusView.as_view(), name='image-inspector-status'),
    # 향후 추가 가능: 'history/', 'save/' 등
]
