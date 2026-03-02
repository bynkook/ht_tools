from django.urls import path
from .views import UserSettingsView

urlpatterns = [
    path('', UserSettingsView.as_view(), name='user-settings'),
]
