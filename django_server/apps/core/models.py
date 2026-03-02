from django.db import models
from django.contrib.auth.models import User


class AppUsageLog(models.Model):
    """Data Explorer 등 채팅 외 앱의 이용 횟수 로그"""
    APP_CHOICES = [
        ('data_explorer', 'Data Explorer'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='app_usage_logs')
    app = models.CharField(max_length=20, choices=APP_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'app', 'created_at'])
        ]

    def __str__(self):
        return f"{self.user.username} / {self.app} / {self.created_at:%Y-%m-%d %H:%M}"
