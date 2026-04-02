import uuid

from django.db import models


class ConversionJob(models.Model):
    STATUS_WAITING = 'waiting'
    STATUS_WORKING = 'working'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_WAITING, '대기 중'),
        (STATUS_WORKING, '변환 중'),
        (STATUS_COMPLETED, '완료'),
        (STATUS_FAILED, '실패'),
    ]

    original_filename = models.CharField(max_length=500)
    category_name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_WAITING,
    )
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    # FastAPI가 상태 업데이트 콜백으로 사용하는 UUID 토큰 — 인증 없이 해당 job만 수정 가능
    callback_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    class Meta:
        app_label = 'doc_uploader'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.get_status_display()})"
