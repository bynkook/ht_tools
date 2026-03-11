from rest_framework import serializers
from django.contrib.auth.models import User
from .models import ChatSession, ChatMessage, MemorySnapshot, DashboardLink


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'content', 'created_at']
        read_only_fields = ['id', 'created_at']


class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ['id', 'model_id', 'title', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ChatSessionDetailSerializer(ChatSessionSerializer):
    """상세 조회 시 메시지 내역 포함"""
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta(ChatSessionSerializer.Meta):
        fields = ChatSessionSerializer.Meta.fields + ['messages']


class MemorySnapshotSerializer(serializers.ModelSerializer):
    """목록 조회용 (snapshot_data 제외)"""
    class Meta:
        model = MemorySnapshot
        fields = ['id', 'name', 'created_at']
        read_only_fields = ['id', 'created_at']


class MemorySnapshotDetailSerializer(serializers.ModelSerializer):
    """상세 조회용 (snapshot_data 포함)"""
    class Meta:
        model = MemorySnapshot
        fields = ['id', 'name', 'snapshot_data', 'created_at']
        read_only_fields = ['id', 'created_at']


class DashboardLinkSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='display_order', read_only=True)

    class Meta:
        model = DashboardLink
        fields = ['id', 'dashboard_name', 'url', 'linkname', 'desc', 'updated_at']
        read_only_fields = ['id', 'updated_at']


class DashboardLinkBulkRowSerializer(serializers.Serializer):
    dashboard_name = serializers.CharField(max_length=255, trim_whitespace=True)
    url = serializers.URLField(max_length=1000)
    linkname = serializers.CharField(max_length=255, trim_whitespace=True)
    desc = serializers.CharField(trim_whitespace=True)

    def validate(self, attrs):
        normalized = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in attrs.items()
        }

        missing_fields = [key for key, value in normalized.items() if not value]
        if missing_fields:
            raise serializers.ValidationError(
                f"모든 컬럼 값이 필요합니다: {', '.join(missing_fields)}"
            )

        return normalized


class DashboardLinkBulkUpdateSerializer(serializers.Serializer):
    rows = DashboardLinkBulkRowSerializer(many=True)
