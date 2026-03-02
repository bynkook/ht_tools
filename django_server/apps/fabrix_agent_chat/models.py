from django.db import models
from django.contrib.auth.models import User

class ChatSession(models.Model):
    """
    하나의 대화방(주제)을 의미합니다.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    agent_id = models.CharField(max_length=100, help_text="FabriX Agent UUID", db_index=True)
    title = models.CharField(max_length=200, blank=True, default="New Chat")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ['-updated_at']  # 최신 대화가 위로 오게 정렬
        indexes = [
            models.Index(fields=['-updated_at', 'user']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.title} ({self.user.username})"

class ChatMessage(models.Model):
    """
    대화방 내의 개별 메시지를 의미합니다.
    """
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, db_index=True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['created_at']  # 시간순 정렬
        indexes = [
            models.Index(fields=['session', 'created_at']),
            models.Index(fields=['session', 'role']),
        ]

    def __str__(self):
        return f"[{self.role}] {self.content[:30]}..."


class MemorySnapshot(models.Model):
    """
    에이전트 채팅 세션의 대화 스냅샷
    특정 시점의 대화 내용을 저장합니다.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agent_memory_snapshots')
    chat_session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='memory_snapshots'
    )
    name = models.CharField(
        max_length=200,
        help_text="스냅샷의 고유 이름"
    )
    snapshot_data = models.JSONField(
        default=dict,
        help_text='{ "messages": [ChatMessage 객체 배열] }'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Agent Memory Snapshot"
        verbose_name_plural = "Agent Memory Snapshots"
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['chat_session', 'name']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['chat_session', 'name'],
                name='unique_agent_snapshot_name_per_session',
                violation_error_message='이미 존재하는 스냅샷 이름입니다.'
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.user.username})"