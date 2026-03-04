from django.db import models
from django.contrib.auth.models import User

def default_preferences():
    return {
        "image_inspector": {
            # 색상 설정
            "diff_file1": "#3B82F6",  # Blue
            "diff_file2": "#DC2626",  # Red
            "diff_common": "#000000", # Black
            "overlay_file1": "#F97316", # Orange
            "overlay_file2": "#22C55E",  # Green
            # 출력 품질 설정
            "output_quality": 85,       # JPEG 출력 품질 (50-100)
            "output_resolution": 2000,  # 화면 출력 최대 해상도 px (1000-4000)
            # 비교 연산 품질 설정 (고급)
            "processing_resolution": 6000,  # 비교 연산용 최대 해상도 px (4000-8000)
            "pdf_dpi": 200              # PDF 변환 DPI (100-300)
        }
    }

class UserSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='settings')
    preferences = models.JSONField(default=default_preferences)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Settings for {self.user.username}"

    class Meta:
        verbose_name = "User Settings"
        verbose_name_plural = "User Settings"
