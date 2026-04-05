from django.db import models
from django.contrib.auth.models import User


class EscProject(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='esc_projects')
    name = models.CharField(max_length=200)
    input_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.username} - {self.name}"


class KosisCache(models.Model):
    DATA_TYPE_PPI = 'ppi'
    DATA_TYPE_WAGE = 'wage'
    DATA_TYPE_CHOICES = [
        (DATA_TYPE_PPI, '생산자물가지수'),
        (DATA_TYPE_WAGE, '시중노임단가'),
    ]

    data_type = models.CharField(max_length=10, choices=DATA_TYPE_CHOICES)
    period_start = models.CharField(max_length=6)  # YYYYMM
    period_end = models.CharField(max_length=6)    # YYYYMM
    payload = models.JSONField()                   # 정규화된 데이터
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('data_type', 'period_start', 'period_end')

    def __str__(self):
        return f"{self.data_type} {self.period_start}~{self.period_end}"
