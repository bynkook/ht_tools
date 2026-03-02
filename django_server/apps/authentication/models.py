from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    recovery_pin = models.CharField(max_length=6, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username}'s profile"
