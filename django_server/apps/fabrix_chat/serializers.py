from rest_framework import serializers
from django.contrib.auth.models import User

from .message_metadata import validate_chat_message_metadata
from .models import ChatSession, ChatMessage, MemorySnapshot
from .runtime_config import get_chat_runtime_config


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']


class ChatMessageSerializer(serializers.ModelSerializer):
    metadata = serializers.DictField(required=False, default=dict)

    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'content', 'metadata', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        attrs['metadata'] = validate_chat_message_metadata(
            attrs.get('role'),
            attrs.get('metadata', {}),
        )
        return attrs


class ChatMessageBulkSerializer(serializers.Serializer):
    messages = ChatMessageSerializer(many=True)


class ChatSessionSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        runtime_config = get_chat_runtime_config(request=self.context.get('request'))
        model_id = attrs.get('model_id', getattr(self.instance, 'model_id', None))
        if runtime_config['requires_model_selection'] and not model_id:
            raise serializers.ValidationError({'model_id': 'model_id is required in normal mode'})
        return attrs

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
