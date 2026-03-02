from django.db import models
from django.contrib.auth.models import User

def default_preferences():
    return {
        "image_inspector": {
            "diff_file1": "#3B82F6",  # Blue
            "diff_file2": "#DC2626",  # Red
            "diff_common": "#000000", # Black
            "overlay_file1": "#F97316", # Orange
            "overlay_file2": "#22C55E"  # Green
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
