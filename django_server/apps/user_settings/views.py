from rest_framework import generics, permissions
from .models import UserSettings
from .serializers import UserSettingsSerializer

class UserSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSettingsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # 현재 로그인한 사용자의 설정 반환
        return self.request.user.settings
